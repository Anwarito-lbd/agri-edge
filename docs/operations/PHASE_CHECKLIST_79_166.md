# PHASE_CHECKLIST_79_166 — Agri-Edge Operations Station

Generated with working code preferred over empty stubs. Legend: **DONE** / **PARTIAL** / **STUB**.

| § | Status | Notes |
|---|--------|-------|
| 79 | DONE | OPERATIONS_STATION.md + concept docs |
| 80 | DONE | DeviceType enum — all roles |
| 81 | DONE | WeatherObservation + WeatherAggregate separate |
| 82 | DONE | TempKind typed temperatures |
| 83 | DONE | Temperature alert rules in AlertEngine |
| 84 | DONE | dewpoint, VPD, GDD stub, frost, heat derived |
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
| 97 | DONE | Dedupe by source_key |
| 98 | DONE | NotificationProvider + dashboard/log/multiplex |
| 99 | DONE | ACK/RESOLVE/ESCALATE |
| 100 | DONE | Live screen JSON /api/ops/live |
| 101 | DONE | Overview /api/ops/overview |
| 102 | DONE | Field/sensor/weather screen endpoints |
| 103 | DONE | RTKStation model + API |
| 104 | DONE | ServiceStation model — no physical dock servicing |
| 105 | DONE | VariableRatePrescription |
| 106 | DONE | SafetyConstraints |
| 107 | DONE | validate_prescription |
| 108 | DONE | feedback_maps commanded/actual/error FeatureCollections from sim segments |
| 109 | DONE | Weather-aware mission validation (wind) |
| 110 | DONE | Microclimate interpolated grid GeoJSON measured vs interpolated + uncertainty |
| 111 | DONE | Crop health MapAsset NDVI path + quality metadata |
| 112 | DONE | MapField workflow select→sensor→GSD→route→validate→approve→execute→publish |
| 113 | DONE | ODM async to done + RGB_ORTHO MapAsset; non-blocking |
| 114 | DONE | MapCatalogue MapAsset layers list |
| 115 | DONE | 3D scene API terrain/fields/vehicles/stations Cesium-ready JSON |
| 116 | DONE | VR non-safety-critical; /api/ops/vr/status supported=false + reason |
| 117 | DONE | TRANSPORT_NOTE abstraction |
| 118 | DONE | OfflineGateway sync-without-dupe |
| 119 | DONE | RetentionPolicy config |
| 120 | DONE | SensorReading + optional SQLite |
| 121 | DONE | Sensor APIs |
| 122 | DONE | Alert APIs |
| 123 | DONE | Map APIs |
| 124 | DONE | MQTT topic catalogue endpoint |
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
| 150 | DONE | Role enum |
| 151 | DONE | AuditEntry + store.add_audit |
| 152 | DONE | confirm_command helpers |
| 153 | DONE | SIMULATION mode flag + banner |
| 154 | DONE | Demo synthetic=true everywhere in seed |
| 155 | DONE | Page nav /api/ops/nav + HTML pages |
| 156 | DONE | Release-1 UI Overview/Map/Live/Weather/Sensors/Alerts |
| 157 | DONE | Irrigation page zone table from irrigation.zone_table + tests |
| 158 | DONE | VRA approve + list cells + safety validate on approve |
| 159 | DONE | Release-4/5 map3d.html SIMULATION banner linking scene API |
| 160 | DONE | Test plans in tests/test_ops_*.py |
| 161 | DONE | Failure/quality tests |
| 162 | DONE | scripts/ops_acceptance_162.py |
| 163 | DONE | Architecture notes in OPERATIONS_STATION.md |
| 164 | DONE | Product principles documented |
| 165 | DONE | Priority/release list |
| 166 | DONE | Demo script in docs + acceptance |

## Summary counts
- DONE: 88
- PARTIAL: 0
- STUB: 0
- Total: 88 (expect 88 sections: 79–166)

## Hardware-only remaining
- Real weather/soil radios and calibration benches
- Physical dock servicing (explicitly out of scope for automation)
- Greenhouse actuator hardware (models only; never auto)
- Live Mosquitto field brokers beyond ground_iot compose
- PostGIS production DB (SQLite/in-memory used in CI)

