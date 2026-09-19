#!/usr/bin/env python3
"""§162 Acceptance harness with simulation data."""
from __future__ import annotations

import sys
from agri_edge.ops.store import reset_store
from agri_edge.ops.simulate import seed_demo
from agri_edge.ops.derived import derive_from_weather, frost_risk
from agri_edge.ops.irrigation import rule_based_irrigation
from agri_edge.ops.vra import make_demo_prescription, validate_prescription
from agri_edge.ops.gateway import OfflineGateway
from agri_edge.ops.analytics import kpi_page
from agri_edge.ops.geo import demo_farm_geojson
from agri_edge.ops.commands import confirm_command


def main() -> int:
    steps = []
    store = reset_store()
    seed = seed_demo(store)
    steps.append(("seed_synthetic", seed["synthetic"] is True))
    steps.append(("simulation_banner", store.overview()["banner"] == "SIMULATION"))
    steps.append(("devices", len(store.devices) >= 3))
    steps.append(("multi_depth_soil", len({s.depth_cm for s in store.soil}) >= 3))
    w = store.weather[-1]
    d = derive_from_weather(w.air_temp.value_c, w.rh_pct or 50)
    steps.append(("derived_origin", d["origin"] == "DERIVED"))
    steps.append(("frost_no_auto", frost_risk(0)["auto_irrigate"] is False))
    steps.append(("geojson", demo_farm_geojson()["type"] == "FeatureCollection"))
    rec = rule_based_irrigation(moisture_pct=10)
    steps.append(("irrigation_no_auto", rec.auto_execute is False))
    rx = make_demo_prescription()
    steps.append(("vra_no_auto", validate_prescription(rx)["auto_apply"] is False))
    gw = OfflineGateway()
    gw.enqueue("t", {"obs_id": "a"}, idempotency_key="a")
    gw.enqueue("t", {"obs_id": "a"}, idempotency_key="a")
    steps.append(("gateway_dedupe", len(gw.buffer) == 1))
    kpi = kpi_page(store)
    steps.append(("no_fake_health", kpi["health_score"] is None))
    steps.append(("cmd_forbid_arm", confirm_command("arm", human_confirmed=True).confirmed is False))
    gh = list(store.greenhouse.values())[0].to_dict()
    steps.append(("gh_no_auto", gh["actuators_automated"] is False))
    svc = list(store.service_stations.values())[0]
    steps.append(("dock_not_auto", svc.servicing_automated is False))

    failed = [n for n, ok in steps if not ok]
    for n, ok in steps:
        print(f"{'PASS' if ok else 'FAIL'}: {n}")
    print(f"\n{len(steps)-len(failed)}/{len(steps)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
