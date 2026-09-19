# Normalized Detection API

**Status:** IMPLEMENTED (software) · HailoBackend = BLOCKED-HARDWARE until device.

## Contract
- `Detection` dataclass (`agri_edge.inference.engine` / re-exported from `agri_edge.detection`)
- `DetectionBackend` protocol → `InferenceResult` (detections + backend metadata only)
- Backends: `SimulatedBackend`, `CpuOnnxBackend`, `HailoBackend`
- **No HailoRT / ORT session objects** leak past the backend facade

## Treatment safety
`Detection.may_drive_treatment` requires `validated_locally` **and** `in_treatment_zone is True` (fail closed).
