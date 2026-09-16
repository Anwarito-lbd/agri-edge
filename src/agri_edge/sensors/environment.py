"""Environmental sensing: air temperature, humidity, pressure.

WHY THIS IS NOT A FEATURE REQUEST
---------------------------------
`docs/briefs/04-compliance-checklist.md` already requires that every spray
operation record **wind speed and direction, temperature and humidity**. That is
a Health Canada / provincial applicator obligation, not a nice-to-have, and until
now nothing in the pipeline captured it. This closes that gap.

It also improves the imagery itself: `qa/checks.py` warns that thermal and
multispectral comparisons across dates are meaningless without knowing the
conditions they were flown in. Stamping conditions onto every frame makes that
checkable after the fact instead of guessable.

WHAT THIS DOES NOT DO
---------------------
**It does not measure soil moisture.** An air sensor on an airframe reads the air
it is flying through. Soil moisture from a drone is a genuinely hard remote
sensing problem: thermal and NDVI give *proxies* that correlate under controlled
conditions, and actual volumetric water content needs in-ground probes or
specialised instruments. Anything here labelled "soil" would be a lie.

What the derived values below *do* support is **spray-condition assessment** --
vapour pressure deficit and dew point are the standard indicators for evaporation
and drift risk, and both come free from temperature and humidity.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class EnvironmentReading:
    """One environmental sample. Immutable -- it becomes part of a frame's record."""

    timestamp: float = 0.0
    temperature_c: float | None = None
    humidity_pct: float | None = None
    pressure_hpa: float | None = None
    sensor: str = "none"

    # WIND. Not measured by the BME280 and not measurable from the aircraft at
    # all -- a drone sits in its own downwash, so an anemometer bolted to the
    # airframe reads the rotors, not the weather. It has to come from a mast at
    # the field edge or a handheld meter. See airframe brief item 08.
    #
    # `wind_source` records which, because a reading whose provenance is unknown
    # cannot support a spray record.
    wind_speed_ms: float | None = None
    wind_direction_deg: float | None = None      # degrees FROM which it blows
    wind_source: str = "none"                    # none | mast | handheld | forecast
    wind_measured_at: float | None = None

    @property
    def valid(self) -> bool:
        return self.temperature_c is not None and self.humidity_pct is not None

    def age_s(self, now: float | None = None) -> float:
        return (now if now is not None else time.time()) - self.timestamp

    @property
    def dew_point_c(self) -> float | None:
        """Dew point via the Magnus formula.

        Relevant operationally: when the surface is at or below dew point there is
        free moisture on the leaf, which changes both spray adhesion and how a
        thermal image should be read.
        """
        if self.temperature_c is None or self.humidity_pct is None:
            return None
        rh = max(1e-3, min(100.0, self.humidity_pct))
        a, b = 17.62, 243.12
        gamma = (a * self.temperature_c) / (b + self.temperature_c) + math.log(rh / 100.0)
        return (b * gamma) / (a - gamma)

    @property
    def vapour_pressure_deficit_kpa(self) -> float | None:
        """VPD -- how much drying power the air has.

        The standard spray-condition indicator. High VPD evaporates fine droplets
        before they land, which both wastes product and increases drift; it is
        also a direct driver of crop water stress.
        """
        if self.temperature_c is None or self.humidity_pct is None:
            return None
        # Tetens equation for saturation vapour pressure, kPa.
        svp = 0.6108 * math.exp((17.27 * self.temperature_c) / (self.temperature_c + 237.3))
        avp = svp * (max(0.0, min(100.0, self.humidity_pct)) / 100.0)
        return round(svp - avp, 4)

    # Wind thresholds in m/s. Standard agricultural spray guidance is expressed
    # in km/h (3-15 ideal), converted here because everything else in this
    # codebase is SI.
    WIND_CALM_MS = 0.83      #  3 km/h -- BELOW this is dangerous, see below
    WIND_GOOD_MAX_MS = 4.17  # 15 km/h
    WIND_CAUTION_MAX_MS = 5.56  # 20 km/h
    WIND_MAX_AGE_S = 1800.0  # 30 min

    def spray_advisory(self, now: float | None = None) -> tuple[str, str]:
        """A coarse spray-condition read. Returns `(level, reason)`.

        Deliberately coarse, and deliberately advisory. Thresholds vary by product
        and jurisdiction, and the **product label is authoritative** -- this
        flags conditions worth a second look, it does not authorise or forbid an
        application.

        **Wind is checked first, and its absence blocks an "ok".** Wind is the
        dominant drift factor: this advisory once returned "ok" in a 40 km/h
        crosswind because it only looked at temperature and humidity. Canadian
        spray records are also required to carry wind speed and direction, so a
        reading without it cannot support one regardless of how pleasant the
        temperature is.

        The counterintuitive part is the LOW end. Dead calm is not ideal, it is
        dangerous: still air below about 3 km/h usually means a temperature
        inversion, where fine droplets hang in a stable layer and then move off
        target as a concentrated cloud when it breaks -- often hundreds of metres,
        long after the operator has packed up. Every agricultural extension
        service warns about this and it is the condition an inexperienced
        operator is most likely to think is perfect.
        """
        if not self.valid:
            return ("unknown", "no environmental reading")

        t, rh = self.temperature_c, self.humidity_pct
        vpd = self.vapour_pressure_deficit_kpa or 0.0

        # --- wind first: it dominates drift, and its absence is disqualifying ---
        w = self.wind_speed_ms
        if w is None or self.wind_source in ("none", ""):
            return (
                "unknown",
                "no wind measurement -- wind dominates drift and is required on a "
                "spray record. Fit a ground mast or enter a handheld reading; an "
                "anemometer on the aircraft measures its own downwash.",
            )
        if self.wind_source == "airframe":
            return (
                "unknown",
                "wind reported from the airframe, which sits in its own downwash. "
                "That number describes the rotors, not the weather.",
            )
        age = (now if now is not None else time.time()) - (self.wind_measured_at or 0.0)
        if self.wind_measured_at is not None and age > self.WIND_MAX_AGE_S:
            return ("unknown", f"wind reading is {age / 60:.0f} min old -- stale for spraying")
        if self.wind_direction_deg is None:
            return ("unknown", "wind speed without direction -- a spray record needs both")

        kmh = w * 3.6
        if w < self.WIND_CALM_MS:
            return (
                "poor",
                f"{kmh:.0f} km/h -- too calm. Still air suggests a temperature "
                "inversion; fine droplets will hang and move off target later.",
            )
        if w > self.WIND_CAUTION_MAX_MS:
            return ("poor", f"{kmh:.0f} km/h -- too windy, unacceptable drift")
        if w > self.WIND_GOOD_MAX_MS:
            return ("caution", f"{kmh:.0f} km/h -- near the upper wind limit")

        if t is not None and t > 30:
            return ("poor", f"{t:.0f} C -- high temperature increases evaporation and drift")
        if rh is not None and rh < 40:
            return ("poor", f"{rh:.0f}% RH -- dry air evaporates fine droplets before they land")
        if vpd > 2.0:
            return ("poor", f"VPD {vpd:.2f} kPa -- strong drying conditions")
        if vpd < 0.4:
            return ("caution", f"VPD {vpd:.2f} kPa -- very humid; slow drying, runoff risk")
        if t is not None and t < 5:
            return ("caution", f"{t:.0f} C -- low temperature slows uptake")
        return (
            "ok",
            f"{kmh:.0f} km/h from {self.wind_direction_deg:.0f} deg, "
            f"{t:.0f} C, {rh:.0f}% RH, VPD {vpd:.2f} kPa",
        )

    def to_dict(self) -> dict:
        return {
            "sensor": self.sensor,
            "timestamp": self.timestamp,
            "temperature_c": self.temperature_c,
            "humidity_pct": self.humidity_pct,
            "pressure_hpa": self.pressure_hpa,
            "dew_point_c": round(self.dew_point_c, 2) if self.dew_point_c is not None else None,
            "vapour_pressure_deficit_kpa": self.vapour_pressure_deficit_kpa,
            "wind_speed_ms": self.wind_speed_ms,
            "wind_direction_deg": self.wind_direction_deg,
            "wind_source": self.wind_source,
            "spray_advisory": self.spray_advisory()[0],
            "spray_advisory_reason": self.spray_advisory()[1],
            # Air, not soil. Stated in the record so nobody later mistakes it.
            "measures": "ambient air at the airframe; NOT soil moisture",
        }


class EnvironmentSensor:
    def read(self) -> EnvironmentReading:
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - trivial
        pass


class NullEnvironmentSensor(EnvironmentSensor):
    """No sensor fitted. Returns an invalid reading rather than failing.

    Environmental data is valuable but never flight-critical, so its absence must
    not stop a capture run.
    """

    def read(self) -> EnvironmentReading:
        return EnvironmentReading(timestamp=time.time(), sensor="none")


class SimulatedEnvironmentSensor(EnvironmentSensor):
    """Plausible conditions for bench work and tests.

    Defaults to a warm, moderately dry afternoon -- conditions that sit near the
    edge of the spray advisory, so the advisory logic is actually exercised.
    """

    def __init__(self, temperature_c: float = 24.0, humidity_pct: float = 55.0,
                 pressure_hpa: float = 1013.0, drift: float = 0.0):
        self.temperature_c = temperature_c
        self.humidity_pct = humidity_pct
        self.pressure_hpa = pressure_hpa
        self.drift = drift
        self._n = 0

    def read(self) -> EnvironmentReading:
        self._n += 1
        d = self.drift * self._n
        return EnvironmentReading(
            timestamp=time.time(),
            temperature_c=round(self.temperature_c + d, 2),
            humidity_pct=round(max(0.0, min(100.0, self.humidity_pct - d)), 2),
            pressure_hpa=self.pressure_hpa,
            sensor="simulated",
        )


class BME280Sensor(EnvironmentSensor):
    """Bosch BME280 over I2C -- temperature, humidity and pressure.

    The right part for this job: one small I2C device, about C$10, reading all
    three. Wire to the Pi's SDA/SCL (pins 3 and 5) and enable I2C with
    `sudo raspi-config`. Address is 0x76 or 0x77 depending on the breakout.

    Mount it away from the Pi's own heat and out of direct propeller downwash:
    the board self-heats by several degrees, and downwash mixes air from above
    the canopy with air at the sensor. Both bias the reading in ways that are
    hard to notice and hard to correct afterwards.

    Requires the optional `sensors` extra. Imported lazily to keep the runtime
    core at numpy + PyYAML.
    """

    def __init__(self, address: int = 0x76, bus: int = 1):
        self.address = address
        try:  # pragma: no cover - requires hardware
            import board  # noqa: F401
            import busio
            from adafruit_bme280 import basic as adafruit_bme280
        except ImportError as exc:
            raise RuntimeError(
                "BME280 support needs the sensors extra: "
                "pip install 'agri-edge[sensors]'  (adafruit-circuitpython-bme280)"
            ) from exc

        import board

        i2c = busio.I2C(board.SCL, board.SDA)
        self._dev = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=address)

    def read(self) -> EnvironmentReading:  # pragma: no cover - requires hardware
        try:
            return EnvironmentReading(
                timestamp=time.time(),
                temperature_c=round(float(self._dev.temperature), 2),
                humidity_pct=round(float(self._dev.relative_humidity), 2),
                pressure_hpa=round(float(self._dev.pressure), 2),
                sensor=f"bme280@0x{self.address:02x}",
            )
        except Exception:
            # A flaky I2C line must not end the flight's data collection.
            log_reading_failure()
            return EnvironmentReading(timestamp=time.time(), sensor="bme280-error")


def log_reading_failure() -> None:  # pragma: no cover - trivial
    import logging

    logging.getLogger("agri_edge.sensors").warning(
        "Environmental sensor read failed; continuing without it."
    )


def build_environment_sensor(cfg, simulated: bool = False) -> EnvironmentSensor:
    """Construct the configured sensor. Never raises for a missing sensor."""
    if simulated:
        return SimulatedEnvironmentSensor()

    kind = (getattr(cfg, "environment_sensor", "none") or "none").lower()
    if kind in ("none", "off", ""):
        return NullEnvironmentSensor()
    if kind == "simulated":
        return SimulatedEnvironmentSensor()
    if kind == "bme280":
        return BME280Sensor(address=int(getattr(cfg, "environment_i2c_address", 0x76)))
    raise ValueError(
        f"Unknown environment_sensor '{kind}'. Expected none, simulated or bme280."
    )
