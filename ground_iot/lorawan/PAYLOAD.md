# agri-edge LoRaWAN uplink payloads (version 1)

Big-endian. A missing reading is the field's MISSING value, never 0.
Encoder: `firmware/agriedge_payload.c`. Decoders: `chirpstack_codec.js`
(ChirpStack v4 device profile) and `agri_edge.iot.lorawan` (bridge). All three
are checked against each other in `tests/test_lorawan.py`.

## fPort 1 — soil (3 + 5·n bytes, n ≤ 4)

| Offset | Size | Field | Encoding | Missing |
|---|---|---|---|---|
| 0 | 1 | version | `1` | — |
| 1 | 1 | battery_pct | 0–100 | `0xFF` |
| 2 | 1 | n depths | 0–4 | — |
| 3+5k | 1 | depth_cm | 0–255 | — |
| 4+5k | 2 | moisture_pct | uint16, ×10 | `0xFFFF` |
| 6+5k | 2 | temp_c | int16, ×10 | `0x7FFF` |

## fPort 2 — weather (16 bytes)

| Offset | Size | Field | Encoding | Missing |
|---|---|---|---|---|
| 0 | 1 | version | `1` | — |
| 1 | 1 | battery_pct | 0–100 | `0xFF` |
| 2 | 2 | air_temp_c | int16, ×10 | `0x7FFF` |
| 4 | 1 | rh_pct | ×2 (0.5 % steps) | `0xFF` |
| 5 | 2 | pressure_hpa | uint16, ×10 | `0xFFFF` |
| 7 | 2 | wind_ms | uint16, ×10 | `0xFFFF` |
| 9 | 2 | wind_dir_deg | uint16 | `0xFFFF` |
| 11 | 2 | precip_mm (since last uplink) | uint16, ×10 | `0xFFFF` |
| 13 | 2 | solar_wm2 | uint16 | `0xFFFF` |
| 15 | 1 | reserved | `0` | — |

16 bytes fits DR0 in US915 (11-byte limit does **not** — use DR1+ or AS923/EU868).
Canada is US915: configure the device profile for DR1 or higher, or send soil
with ≤ 1 depth at DR0.
