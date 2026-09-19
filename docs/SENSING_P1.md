# Sensing P1 — thermal + multispectral + relations (code)

**Status:** Software modules landed 19 Sep 2026. Hardware still required for field claims.

| Module | Path | Notes |
|--------|------|-------|
| Thermal / CWSI | `src/agri_edge/sensors/thermal.py` | Synthetic OK for Demo |
| Multispectral indices | `src/agri_edge/sensors/multispectral.py` | NDVI/NDRE/GNDVI/OSAVI |
| RelateAnything hook | `src/agri_edge/relations/laptop_relate.py` | Laptop only; vendor optional |
| CLI | `scripts/laptop_relate_anything.py` | `--demo-schema` works without vendor |

Tests: `tests/test_sensing_p1.py`

See [NICHE_GAP_ANALYSIS.md](NICHE_GAP_ANALYSIS.md), [RELATE_ANYTHING.md](RELATE_ANYTHING.md).
