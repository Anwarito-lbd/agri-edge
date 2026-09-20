# Current system architecture (as implemented)

## Split
- **This repo (`agri-edge`):** Python edge pipeline, training, mechanical handoff, ground_iot compose, docs.
- **`agri-edge-web`:** Marketing + companion Demo + dashboard map (Vercel).

## Edge data path (today)
```
Camera / file / stub
  → QA
  → Inference (YOLOX onnxruntime and/or green-on-brown)
  → Indices / georeference
  → Spool + provenance
  → Optional farmOS push (env credentials)
```

## Safety (today)
- `telemetry/mavlink_link.py`: **no write** to aircraft.
- Treatment: requires local validation flag + treatment geofence (fails closed).
- Phone companion: status/alerts only (web mock); no arm.

## Ground IoT (today)
```
ESP32 (future) → Mosquitto → Node-RED / agri_edge.iot helpers
Irrigation topics are ground-only (see MQTT_CONTRACT.md).
```

## Brain role
Agri-Edge owns agricultural intelligence and integration. Adapters for FC, farmOS, guidance come next per MASTER spec — without deleting the working read-only companion contract.
