# PHASE_CHECKLIST_79_166 — Agri-Edge Operations Station

Generated with working code preferred over empty stubs. Legend: **DONE** / **PARTIAL** / **STUB**.

> **Re-graded 24 Sept 2026** (docs/audit-2026-09-24.md). The original sheet read
> 88/88 DONE. "DONE" there meant *a code path exists and runs on seeded demo
> data*. Everything in this station still runs on `seed_demo()` data held in
> memory: no sensor, weather or MQTT reading reaches the store, and PostGIS is a
> schema file. Rows whose substance depends on that are now **PARTIAL**, with
> the gap named. Rows fixed during the audit say so.

| § | Status | Notes |
|---|--------|-------|
| 79 | DONE | OPERATIONS_STATION.md + concept docs |
| 80 | DONE | DeviceType enum — all roles |
| 81 | PARTIAL | WeatherObservation + WeatherAggregate separate — models only; weather comes from seed_demo, no ingestion route or provider |
| 82 | DONE | TempKind typed temperatures |
| 83 | DONE | Temperature alert rules in AlertEngine |
| 84 | PARTIAL | dewpoint, VPD, frost, heat derived — GDD is a single-day stub, not accumulated over a season |
| 85 | DONE | Soil multi-depth observations |
| 86 | DONE | quality.py impossible/stuck/jump/missing/battery/signal/cal |
| 87 | DONE | WaterSource/Tank/Pump/Valve/FlowMeter/WaterReading/WaterUsageEvent |
| 88 | DONE | GeoJSON FeatureCollections |
| 89 | DONE | Layer enable/disable via map assets + API toggle |
| 90 | DONE | Time control ranges now/hour/today/week/month/custom |
| 91 | DONE | Standard formats only GeoJSON/GeoTIFF path strings |
| 92 | DONE | Farm/field/zone/station layers |
| 93 | DONE | Alert engine |
| 94 | DONE | AlertSeverity |
| 95 | DONE | AlertCategory |
| 96 | DONE | Alert rules (temp) |
| 97 | DONE | Dedupe by source_key; dedupe_seconds re-opens a recently resolved alert (was unused until 24 Sept) |
| 98 | DONE | NotificationProvider + dashboard/log/multiplex |
| 99 | DONE | ACK/RESOLVE/ESCALATE with checked transitions; RESOLVED is terminal (ACK used to re-open it) |
| 100 | DONE | Live screen JSON /api/ops/live |
| 101 | DONE | Overview /api/ops/overview |
| 102 | DONE | Field/sensor/weather screen endpoints |
| 103 | DONE | RTKStation model + API |
| 104 | DONE | ServiceStation model — no physical dock servicing |
| 105 | DONE | VariableRatePrescription |
| 106 | DONE | SafetyConstraints |
| 107 | DONE | validate_prescription |
| 108 | DONE | feedback_maps commanded/actual/error FeatureCollections from sim segments |
| 109 | DONE | Weather-aware mission validation — missing wind now fails closed (was skipped) |
| 110 | PARTIAL | Microclimate grid GeoJSON — interpolates hard-coded points, not store readings |
| 111 | PARTIAL | Crop health MapAsset — `sim://` path with hard-coded quality; no real NDVI raster or time series |
| 112 | DONE | MapField workflow select→sensor→GSD→route→validate→approve→execute→publish |
| 113 | DONE | ODM async to done + RGB_ORTHO MapAsset (HTTP submit did not register the layer until 24 Sept) |
| 114 | DONE | MapCatalogue MapAsset layers list |
| 115 | DONE | 3D scene API terrain/fields/vehicles/stations Cesium-ready JSON |
| 116 | DONE | VR non-safety-critical; /api/ops/vr/status supported=false + reason |
| 117 | DONE | TRANSPORT_NOTE abstraction |
| 118 | DONE | OfflineGateway sync-without-dupe |
| 119 | DONE | RetentionPolicy config |
| 120 | PARTIAL | SensorReading + optional SQLite — persist_sensor is never called and serve() passes no SQLite path; readings are in-memory seed data |
| 121 | DONE | Sensor APIs |
| 122 | DONE | Alert APIs |
| 123 | DONE | Map APIs |
| 124 | PARTIAL | MQTT topic catalogue endpoint — a hard-coded list; MqttBridge exists but nothing wires it to the store |
| 125 | DONE | Device health JSON |
| 126 | DONE | QualityFlag enum + evaluators |
| 127 | DONE | CalibrationRecord |
| 128 | DONE | MaintenanceSchedule + engine |
| 129 | DONE | Maintenance alerts |
| 130 | DONE | battery analytics pack_id/cycles/soh from DeviceHealth seed |
| 131 | DONE | energy_per_mission from seeded mission energy log |
| 132 | DONE | water commanded vs measured + mismatch alert hook |
| 133 | DONE | application weeds detected/treated/skipped from sim vision events |
| 134 | DONE | KPI page transparent formulas, health_score=None |
| 135 | DONE | DataOrigin FORECAST vs MEASURED vs DERIVED |
| 136 | DONE | Frost workflow recommend-only |
| 137 | DONE | Heat workflow recommend-only |
| 138 | DONE | Irrigation dashboard |
| 139 | DONE | Rule-based irrigation skeleton no ML |
| 140 | DONE | GreenhouseZone actuators_automated forced False |
| 141 | DONE | PestObservation |
| 142 | DONE | CameraEvent seed + API list/create |
| 143 | DONE | ScoutReport seed + API list/create |
| 144 | DONE | ManualObservation seed + API list/create |
| 145 | DONE | Task model + API |
| 146 | DONE | Timeline builder |
| 147 | DONE | report_summary |
| 148 | DONE | daily_brief factual only |
| 149 | DONE | MobileNote seed + API list/create |
| 150 | PARTIAL | Role enum — defined, never enforced; the API has a shared write token (OPS_API_TOKEN) but no users or roles |
| 151 | PARTIAL | AuditEntry + store.add_audit — in memory only, and the actor is whatever string the client sends |
| 152 | DONE | confirm_command helpers |
| 153 | DONE | SIMULATION mode flag + banner |
| 154 | DONE | Demo synthetic=true everywhere in seed |
| 155 | DONE | Page nav /api/ops/nav + HTML pages |
| 156 | DONE | Release-1 UI Overview/Map/Live/Weather/Sensors/Alerts |
| 157 | DONE | Irrigation page zone table from irrigation.zone_table + tests |
| 158 | DONE | VRA approve + list cells — approval fails closed on unvalidated/missing wind (it always approved until 24 Sept) |
| 159 | DONE | Release-4/5 map3d.html SIMULATION banner linking scene API |
| 160 | DONE | Test plans in tests/test_ops_*.py |
| 161 | DONE | Failure/quality tests |
| 162 | DONE | scripts/ops_acceptance_162.py |
| 163 | DONE | Architecture notes in OPERATIONS_STATION.md |
| 164 | DONE | Product principles documented |
| 165 | DONE | Priority/release list |
| 166 | DONE | Demo script in docs + acceptance |

## Summary counts
- DONE: 80
- PARTIAL: 8
- STUB: 0
- Total: 88 (expect 88 sections: 79–166)

## Not hardware — software still to build
- Ingestion: MQTT (`MqttBridge`) and HTTP routes for sensor/weather readings into the store
- Persistence the API actually uses (SQLite now, PostGIS/Timescale later)
- Users and roles behind the audit log (§150–151)
- Real weather provider (forecast + observations) and seasonal GDD

## Hardware-only remaining
- Real weather/soil radios and calibration benches
- Physical dock servicing (explicitly out of scope for automation)
- Greenhouse actuator hardware (models only; never auto)
- Live Mosquitto field brokers beyond ground_iot compose
- PostGIS production DB (SQLite/in-memory used in CI)

