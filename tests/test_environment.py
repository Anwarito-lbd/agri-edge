"""Environmental sensing tests.

The derived values are pinned against **published reference figures**, not against
whatever the implementation happens to return. Dew point and VPD are standard
psychrometrics with known answers, so a test that only checks self-consistency
would pass on a wrong formula.

Reference points used:
  24 C / 55% RH  -> dew point 14.4 C, SVP 2.985 kPa, VPD 1.34 kPa
  20 C / 100% RH -> dew point == air temperature, VPD == 0
"""

import time

import pytest

from agri_edge.config import CaptureConfig
from agri_edge.sensors.environment import (
    EnvironmentReading,
    NullEnvironmentSensor,
    SimulatedEnvironmentSensor,
    build_environment_sensor,
)


class TestDewPoint:
    def test_reference_point_24c_55pct(self):
        """Published value for 24 C / 55% RH is 14.4 C."""
        r = EnvironmentReading(temperature_c=24.0, humidity_pct=55.0)
        assert r.dew_point_c == pytest.approx(14.4, abs=0.1)

    def test_saturated_air_dew_point_equals_temperature(self):
        """At 100% RH the air is already at its dew point, by definition."""
        r = EnvironmentReading(temperature_c=20.0, humidity_pct=100.0)
        assert r.dew_point_c == pytest.approx(20.0, abs=0.05)

    def test_dew_point_never_exceeds_temperature(self):
        for t in (0.0, 10.0, 25.0, 40.0):
            for rh in (10.0, 50.0, 90.0, 100.0):
                r = EnvironmentReading(temperature_c=t, humidity_pct=rh)
                assert r.dew_point_c <= t + 1e-6, f"{t} C {rh}%"

    def test_drier_air_gives_lower_dew_point(self):
        wet = EnvironmentReading(temperature_c=25.0, humidity_pct=80.0).dew_point_c
        dry = EnvironmentReading(temperature_c=25.0, humidity_pct=30.0).dew_point_c
        assert dry < wet

    def test_zero_humidity_does_not_blow_up(self):
        """log(0) is -inf; the implementation clamps rather than crashing."""
        r = EnvironmentReading(temperature_c=25.0, humidity_pct=0.0)
        assert r.dew_point_c is not None
        assert r.dew_point_c < 0

    def test_none_without_a_reading(self):
        assert EnvironmentReading().dew_point_c is None


class TestVapourPressureDeficit:
    def test_reference_point_24c_55pct(self):
        """SVP at 24 C is ~2.985 kPa, so VPD at 55% RH is ~1.34 kPa."""
        r = EnvironmentReading(temperature_c=24.0, humidity_pct=55.0)
        assert r.vapour_pressure_deficit_kpa == pytest.approx(1.343, abs=0.01)

    def test_saturated_air_has_zero_deficit(self):
        r = EnvironmentReading(temperature_c=20.0, humidity_pct=100.0)
        assert r.vapour_pressure_deficit_kpa == pytest.approx(0.0, abs=1e-6)

    def test_hotter_air_has_greater_deficit_at_same_humidity(self):
        """Warm air holds more water, so the same RH is a bigger deficit."""
        cool = EnvironmentReading(temperature_c=15.0, humidity_pct=50.0)
        warm = EnvironmentReading(temperature_c=30.0, humidity_pct=50.0)
        assert warm.vapour_pressure_deficit_kpa > cool.vapour_pressure_deficit_kpa

    def test_never_negative(self):
        for t in (0.0, 15.0, 35.0):
            for rh in (0.0, 50.0, 100.0):
                v = EnvironmentReading(temperature_c=t, humidity_pct=rh).vapour_pressure_deficit_kpa
                assert v >= 0.0, f"{t} C {rh}%"

    def test_none_without_a_reading(self):
        assert EnvironmentReading().vapour_pressure_deficit_kpa is None


class TestSprayAdvisory:
    def test_good_conditions(self):
        level, _ = EnvironmentReading(temperature_c=20.0, humidity_pct=65.0).spray_advisory()
        assert level == "ok"

    def test_hot_is_poor(self):
        level, reason = EnvironmentReading(temperature_c=34.0, humidity_pct=60.0).spray_advisory()
        assert level == "poor"
        assert "temperature" in reason

    def test_dry_air_is_poor(self):
        level, reason = EnvironmentReading(temperature_c=22.0, humidity_pct=25.0).spray_advisory()
        assert level == "poor"
        assert "RH" in reason

    def test_very_humid_is_caution(self):
        level, reason = EnvironmentReading(temperature_c=12.0, humidity_pct=98.0).spray_advisory()
        assert level == "caution"
        assert "humid" in reason or "VPD" in reason

    def test_cold_is_caution(self):
        level, _ = EnvironmentReading(temperature_c=3.0, humidity_pct=70.0).spray_advisory()
        assert level == "caution"

    def test_unknown_without_a_reading(self):
        level, reason = EnvironmentReading().spray_advisory()
        assert level == "unknown"
        assert "no environmental reading" in reason

    def test_advisory_is_advisory_not_authorisation(self):
        """The label is authoritative; this only flags conditions worth a look."""
        from agri_edge.sensors import environment

        assert "authoritative" in environment.EnvironmentReading.spray_advisory.__doc__


class TestReading:
    def test_valid_requires_temp_and_humidity(self):
        assert not EnvironmentReading().valid
        assert not EnvironmentReading(temperature_c=20.0).valid
        assert EnvironmentReading(temperature_c=20.0, humidity_pct=50.0).valid

    def test_is_immutable(self):
        """It becomes part of a frame's permanent record."""
        r = EnvironmentReading(temperature_c=20.0, humidity_pct=50.0)
        with pytest.raises(Exception):
            r.temperature_c = 99.0

    def test_age(self):
        r = EnvironmentReading(timestamp=time.time() - 10)
        assert 9 < r.age_s() < 12

    def test_dict_states_it_is_air_not_soil(self):
        """Guards against anyone later reading this as soil moisture."""
        d = EnvironmentReading(temperature_c=20.0, humidity_pct=50.0).to_dict()
        assert "NOT soil moisture" in d["measures"]

    def test_dict_has_the_derived_fields(self):
        d = EnvironmentReading(temperature_c=24.0, humidity_pct=55.0).to_dict()
        for k in ("temperature_c", "humidity_pct", "dew_point_c",
                  "vapour_pressure_deficit_kpa", "spray_advisory"):
            assert k in d

    def test_dict_survives_an_empty_reading(self):
        d = EnvironmentReading().to_dict()
        assert d["spray_advisory"] == "unknown"
        assert d["dew_point_c"] is None


class TestSensors:
    def test_null_sensor_returns_invalid_not_an_error(self):
        """No sensor fitted must never stop a capture run."""
        r = NullEnvironmentSensor().read()
        assert not r.valid
        assert r.sensor == "none"

    def test_simulated_sensor_is_valid(self):
        r = SimulatedEnvironmentSensor().read()
        assert r.valid
        assert r.sensor == "simulated"

    def test_simulated_drift(self):
        s = SimulatedEnvironmentSensor(temperature_c=20.0, drift=1.0)
        assert s.read().temperature_c == pytest.approx(21.0)
        assert s.read().temperature_c == pytest.approx(22.0)

    def test_humidity_stays_in_range_under_drift(self):
        s = SimulatedEnvironmentSensor(humidity_pct=5.0, drift=10.0)
        for _ in range(5):
            assert 0.0 <= s.read().humidity_pct <= 100.0


class TestBuild:
    def test_default_is_null(self):
        assert isinstance(build_environment_sensor(CaptureConfig()), NullEnvironmentSensor)

    def test_simulated_flag(self):
        s = build_environment_sensor(CaptureConfig(), simulated=True)
        assert isinstance(s, SimulatedEnvironmentSensor)

    def test_explicit_simulated(self):
        cfg = CaptureConfig(environment_sensor="simulated")
        assert isinstance(build_environment_sensor(cfg), SimulatedEnvironmentSensor)

    def test_unknown_sensor_rejected(self):
        with pytest.raises(ValueError, match="Unknown environment_sensor"):
            build_environment_sensor(CaptureConfig(environment_sensor="dht99"))


class TestPipelineIntegration:
    def test_environment_lands_in_the_sidecar(self, tmp_path):
        import numpy as np

        from agri_edge.capture.camera import SimulatedCamera
        from agri_edge.config import Config, QAConfig
        from agri_edge.pipeline.runner import Pipeline
        from agri_edge.store.spool import Spool
        from agri_edge.telemetry.mavlink_link import SimulatedTelemetry

        cfg = Config()
        cfg.spool.spool_dir = tmp_path / "spool"
        cfg.capture.interval_s = 0.0
        cfg.qa = QAConfig(blur_threshold=1.0)

        spool = Spool(cfg.spool.spool_dir)
        Pipeline(
            cfg, SimulatedCamera(resolution=(32, 32)), SimulatedTelemetry(), spool,
            None, SimulatedEnvironmentSensor(),
        ).run(max_frames=1)

        import json

        entry = spool.pending()[0]
        meta = json.loads((spool.dir / entry.meta_path).read_text(encoding="utf-8"))
        assert meta["environment"]["sensor"] == "simulated"
        assert meta["environment"]["temperature_c"] == pytest.approx(24.0)

    def test_absent_sensor_gives_null_not_a_crash(self, tmp_path):
        import json

        from agri_edge.capture.camera import SimulatedCamera
        from agri_edge.config import Config, QAConfig
        from agri_edge.pipeline.runner import Pipeline
        from agri_edge.store.spool import Spool
        from agri_edge.telemetry.mavlink_link import SimulatedTelemetry

        cfg = Config()
        cfg.spool.spool_dir = tmp_path / "spool"
        cfg.capture.interval_s = 0.0
        cfg.qa = QAConfig(blur_threshold=1.0)

        spool = Spool(cfg.spool.spool_dir)
        Pipeline(
            cfg, SimulatedCamera(resolution=(32, 32)), SimulatedTelemetry(), spool, None
        ).run(max_frames=1)

        entry = spool.pending()[0]
        meta = json.loads((spool.dir / entry.meta_path).read_text(encoding="utf-8"))
        assert meta["environment"] is None

    def test_failing_sensor_does_not_stop_capture(self, tmp_path):
        """A flaky I2C line must not cost the flight its imagery."""
        from agri_edge.capture.camera import SimulatedCamera
        from agri_edge.config import Config, QAConfig
        from agri_edge.pipeline.runner import Pipeline
        from agri_edge.sensors.environment import EnvironmentSensor
        from agri_edge.store.spool import Spool
        from agri_edge.telemetry.mavlink_link import SimulatedTelemetry

        class Broken(EnvironmentSensor):
            def read(self):
                raise OSError("I2C bus error")

        cfg = Config()
        cfg.spool.spool_dir = tmp_path / "spool"
        cfg.capture.interval_s = 0.0
        cfg.qa = QAConfig(blur_threshold=1.0)

        spool = Spool(cfg.spool.spool_dir)
        stats = Pipeline(
            cfg, SimulatedCamera(resolution=(32, 32)), SimulatedTelemetry(), spool,
            None, Broken(),
        ).run(max_frames=2)
        assert stats.spooled == 2
