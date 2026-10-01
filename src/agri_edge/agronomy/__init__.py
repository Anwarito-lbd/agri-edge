"""Agronomy: the models that turn weather, soil and crop into decisions.

Pure numpy / stdlib, so the same code runs on the ops station and, if ever
needed, on the Pi. Every model here names its source and its simplifications;
none of them has been calibrated on a local farm yet, and outputs say so.

* `et0`            FAO-56 Penman-Monteith reference evapotranspiration
* `crops`, `soils` crop coefficients / growth stages, soil water constants
* `gdd`            seasonal growing degree days and BBCH stage estimate
* `water_balance`  FAO-56 root-zone depletion -> irrigation recommendation
* `disease`        sclerotinia (canola), fusarium head blight (wheat),
                   late blight (potato) risk windows
* `frost`          frost risk against crop-stage sensitivity
* `weather`        Open-Meteo (Canadian GEM model) + station observations
* `engine`         everything above for one field, as explained recommendations
"""
