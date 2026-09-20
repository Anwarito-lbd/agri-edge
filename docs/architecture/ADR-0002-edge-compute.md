# ADR-0002 — Edge compute profiles

**Status:** Accepted  
**Date:** 2026-09-19

## Context
Two hardware classes appear in planning: Pi 5 + Hailo (prototype) vs Jetson AGX Orin-class (heavy aircraft). Blocking MVP on Jetson delays learning.

## Decision
| Profile | Hardware | Role |
|---------|----------|------|
| **A (now)** | Raspberry Pi 5 + Hailo AI HAT | Camera inference, weed/crop/livestock detect, scouting MVP |
| **B (later)** | Jetson-class | Multi-sensor, larger ROS graph, mapping |

Implement `InferenceBackend` Protocol (Hailo / ONNX CPU / future TensorRT) so Profile B plugs in without rewriting agriculture logic.

## Consequences
- Priority: YOLOX→ONNX→HEF→Pi camera path (Milestone C).
- Do not wait for Jetson to ship scouting Demo.
- Vocular Pi 5 + Camera Module 3 is the first hardware target (Bookworm, not QNX).
