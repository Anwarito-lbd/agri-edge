"""The batch-2 documents must keep their honesty labels and safety statements."""
from __future__ import annotations

from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"


def _t(rel: str) -> str:
    return (DOCS / rel).read_text(encoding="utf-8")


def test_bench_plan_is_blocked_hardware_water_only_and_has_the_safety_controls():
    t = _t("mechanical/WATER_ONLY_BENCH_TEST_PLAN.md")
    assert "Status: BLOCKED-HARDWARE" in t
    for needle in ("Water only", "No flight", "propellers physically removed", "GFCI", "E-stop",
                   "containment", "No AI in the loop", "TreatmentDecisionEngine", "Transport Canada",
                   "claims **no** RPAS compliance", "pass/fail", "Data-recording template",
                   "L1 electrical-on", "never moves to VALIDATED"):
        assert needle.lower() in t.lower(), needle


def test_px4_note_keeps_ardupilot_primary_and_cites_sources():
    t = _t("architecture/px4-evaluation.md")
    assert "ArduPilot SITL stays the primary" in t and "UNVERIFIED" in t
    for crit in ("Licence", "MAVLink compatibility", "Companion integration", "Community", "Pixhawk board targets"):
        assert crit in t, crit
    assert t.count("https://") >= 8
    assert "px4-evaluation.md" in _t("architecture/ADR-0001-flight-stack.md")


def test_adapter_docs_state_what_is_unverified():
    f = _t("operations/FARMOS_ADAPTER.md")
    a = _t("operations/AGOPENGPS_ADAPTER.md")
    assert "never talked to a real farmOS" in f and "allow_network=True" in f
    assert "SIMULATED" in a and "UNVERIFIED" in a and "GuidanceCommandRefused" in a
