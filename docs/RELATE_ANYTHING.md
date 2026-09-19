# RelateAnything — laptop research track

**Repo:** https://github.com/Maelic/RelateAnything  
**Decision (19 Sep 2026):** Use for **offline / laptop** scene relations only. **Do not** install on the Pi flight image.

## What it adds
Open-vocabulary **relations** between detections — e.g. weed *in* crop row, sheep *near* water, stress patch *beside* bare soil — beyond class boxes alone.

## Licence gate
- Upstream code ≈ Apache-2.0  
- Released weights are **DINOv3 derivatives** (Meta DINOv3 licence: pass licence + display “Built with DINOv3” if you distribute)  
- Training annotations (RA-4M) involve **Gemma** terms  
→ Not equivalent to YOLOX for a clean permissive edge ship.

## Procedure (when ready)
1. Clone into gitignored `vendor/RelateAnything` on the **laptop** (WSL preferred).  
2. Accept DINOv3 / third-party notices; keep out of `scripts/pi_setup.sh`.  
3. Run offline on spool frames / orthos; export GeoJSON relations into farmOS or companion “insight” topic.  
4. Edge keep YOLOX + green-on-brown for real-time.

## Product copy
“Detect on the aircraft. Relate and explain on the ground station when the model licence allows.”
