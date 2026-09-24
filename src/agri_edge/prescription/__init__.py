"""Prescription maps a farmer's existing sprayer or spreader can load.

* `grid`       build a rate grid from georeferenced detections (spot spray) or
               from per-cell zones (variable rate), clipped to the treatment
               boundary, rates clamped to the safety constraints
* `isoxml`     ISO 11783-10 TASKDATA (grid type 2) for ISOBUS task controllers
* `shapefile`  ESRI polygon shapefile for everything else (pure Python)
* `export`     approval-gated zip bundles

The value is delivered by machines the farm already owns; nothing here drives
a nozzle. A prescription is a file a person loads after approving it.
"""
