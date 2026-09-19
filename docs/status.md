# Capability status

**Legend:** Code = implemented in repo · Sim = works in sim/tests · Hardware = run on real device · Field = farm-validated  
Statuses: ✅ done · ⏳ partial/unproven · ❌ absent · N/A

| Component | Code | Sim | Hardware | Field |
|-----------|------|-----|----------|-------|
| YOLOX training / export ONNX | ✅ | N/A | N/A | N/A |
| YOLOX numpy decode / NMS | ✅ | ✅ | ⏳ | ⏳ |
| Green-on-brown (OWL port) | ✅ | ✅ | ⏳ | ⏳ |
| Tiled inference | ✅ | ✅ | ⏳ | ⏳ |
| Hailo compile script | ✅ | ⏳ | ⏳ | ⏳ |
| Hailo live inference | ⏳ | ⏳ | ⏳ | ⏳ |
| Pi camera runtime | ✅ scripts | ⏳ | ⏳ | ⏳ |
| Georeference | ✅ | ✅ | ⏳ | ⏳ |
| Treatment geofence | ✅ | ✅ | ⏳ | ⏳ |
| MAVLink read-only | ✅ | ✅ | ⏳ | ⏳ |
| farmOS client | ✅ | stub | ⏳ | ⏳ |
| WebODM client | ✅ | stub | ⏳ | ⏳ |
| Ground MQTT topics | ✅ | ✅ | ⏳ | ⏳ |
| Mosquitto + Node-RED compose | ✅ | ⏳ | N/A | N/A |
| Thermal / MS indices | ✅ | ✅ | ⏳ cams | ⏳ |
| RelateAnything | hook only | ⏳ | N/A laptop | ❌ |
| Companion phone UI | agri-edge-web | Demo | N/A | N/A |
| ArduPilot SITL | script | ⏳ | N/A | N/A |
| VehicleAdapter (mission cmd) | ❌ | ❌ | ❌ | ❌ |
| Decision / safety supervisor (spec) | partial geofence | ⏳ | ❌ | ❌ |
| Physical treatment actuator | ❌ | ❌ | ❌ | ❌ |
| Postgres / PostGIS backend | ❌ | ❌ | ❌ | ❌ |
| `validated_locally` | flag false | N/A | ⏳ | ❌ |

Do not mark Hardware/Field green without evidence.
