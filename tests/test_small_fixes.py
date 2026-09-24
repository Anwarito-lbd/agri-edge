"""Small defects from the 24 Sept audit (F15), each pinned once."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_adapter_close_stops_the_telemetry_reader():
    from agri_edge.vehicle.ardupilot import ArduPilotAdapter

    class _Link:
        stopped = False

        def stop(self):
            _Link.stopped = True

    adapter = ArduPilotAdapter.__new__(ArduPilotAdapter)
    adapter._conn = _Link()
    adapter.close()
    assert _Link.stopped and adapter._conn is None


def test_pipeline_exit_releases_the_engine(tmp_path):
    from agri_edge.capture.camera import SimulatedCamera
    from agri_edge.config import Config
    from agri_edge.inference.engine import SimulatedEngine
    from agri_edge.pipeline.runner import Pipeline
    from agri_edge.store.spool import Spool
    from agri_edge.telemetry.mavlink_link import SimulatedTelemetry

    class _Engine(SimulatedEngine):
        closed = False

        def close(self):
            _Engine.closed = True

    with Pipeline(Config(), SimulatedCamera(resolution=(8, 8)), SimulatedTelemetry(),
                  Spool(tmp_path), _Engine()):
        pass
    assert _Engine.closed


def test_pi_setup_installs_pymavlink():
    text = (ROOT / "scripts" / "pi_setup.sh").read_text(encoding="utf-8")
    assert '".[onnx,mavlink]"' in text
