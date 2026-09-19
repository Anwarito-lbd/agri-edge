# Operations Station

Agri-Edge Ops Station is the farm operations brain for weather, soil, water, alerts, maps, and operator workflows.

## Safety principles (§164)

1. No AI → unrestricted pump.
2. Treatment gated (validated_locally + geofence + payload arm + freshness).
3. Companion MAVLink read-only.
4. Irrigation commands = ground MQTT only.
5. Demo/sim data always `synthetic=true`; UI shows **SIMULATION** banner.
6. Typed temperatures (`TempKind`) — never bare ambiguous `temperature`.
7. Derived values: `origin=DERIVED` + `algorithm_version`.
8. No greenhouse actuator automation; no physical dock servicing automation.
9. 3D/VR = stubs only.

## Architecture (§163)

- Domain models in `src/agri_edge/ops/` (types, schema, store).
- Transport-agnostic (§117): MQTT/HTTP adapters feed normalized observations.
- Offline gateway buffers with idempotency keys (§118).
- Alert engine with dedupe + ACK/RESOLVE/ESCALATE (§93–99).
- Map layers as GeoJSON FeatureCollections (§88–92).
- stdlib `ThreadingHTTPServer` API: `python -m agri_edge.ops.api`.

## Priority / releases (§165)

1. Foundation: sensors, weather, alerts, quality, APIs, SIMULATION UI.
2. Map + live screens.
3. Soil/water/irrigation (rule-based).
4. VRA + weather-aware validation.
5. Maintenance/analytics/reports/roles.
6. Optional 3D/VR stubs last.

## How to run

```bash
cd agri-edge  # or agricultrul desktop tree
python -m pip install -e ".[dev]"
# Windows: .venv\Scripts\python.exe
set PYTHONPATH=src   # or use editable install
python -m agri_edge.ops.api
# open http://127.0.0.1:8765/ops/
pytest tests/test_ops_station.py tests/test_ops_quality_geo.py tests/test_ops_api.py tests/test_ops_analytics_water.py -q
python scripts/ops_acceptance_162.py
```

## Demo script (§166)

1. Start API; confirm SIMULATION banner on `/ops/`.
2. Overview shows device/alert counts from seeded synthetic data.
3. Map GeoJSON + layer list; toggle a layer via POST `/api/ops/map/layers/toggle`.
4. Weather raw vs aggregates; derived dew/VPD with algorithm_version.
5. Sensors multi-depth soil + quality flags.
6. Alerts: ACK one alert; confirm audit entry.
7. Irrigation dashboard: recommendation with `auto_execute=false`.
8. Frost/heat endpoints: recommendations only, no auto irrigate.
9. KPI page: formulas present, `health_score` is null.
10. Gateway enqueue twice with same key → single buffer entry; sync.

See `PHASE_CHECKLIST_79_166.md` for per-section status.
