"""Crop parameters: water use, rooting, and growth stage by thermal time.

Kc, rooting depth and depletion fraction p: FAO-56 Tables 12 and 22 (single
crop coefficient, sub-humid climate, no adjustment for wind/RH yet).
Stage timing by growing degree days: approximate values from prairie
extension guides (Manitoba Agriculture, Canola Council of Canada, provincial
potato guides). **They are starting points to be calibrated on the farm**,
not measurements; every output built on them says so.

Kc is interpolated against GDD rather than calendar days, so a cold spring
stretches the season the way the crop does.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Stage:
    bbch: int
    name: str
    gdd: float          # thermal time from seeding at which the stage begins


@dataclass(frozen=True)
class Crop:
    key: str
    name: str
    base_c: float                 # GDD base temperature
    cap_c: float                  # GDD upper cutoff
    kc_ini: float
    kc_mid: float
    kc_end: float
    # GDD at the END of the FAO initial / development / mid / late periods.
    kc_gdd: tuple[float, float, float, float]
    root_max_m: float
    p: float                      # depletion fraction before water stress
    stages: tuple[Stage, ...] = field(default_factory=tuple)

    def kc(self, gdd: float) -> float:
        """FAO-56 Kc curve (fig 25) against thermal time."""
        ini, dev, mid, late = self.kc_gdd
        if gdd <= ini:
            return self.kc_ini
        if gdd <= dev:
            return self.kc_ini + (self.kc_mid - self.kc_ini) * (gdd - ini) / (dev - ini)
        if gdd <= mid:
            return self.kc_mid
        if gdd <= late:
            return self.kc_mid + (self.kc_end - self.kc_mid) * (gdd - mid) / (late - mid)
        return self.kc_end

    def root_depth_m(self, gdd: float) -> float:
        """Linear root growth from 0.15 m at seeding to the maximum at the
        start of mid-season (FAO-56 eq 8.1-style simplification)."""
        _, dev, _, _ = self.kc_gdd
        frac = min(max(gdd / dev, 0.0), 1.0)
        return 0.15 + (self.root_max_m - 0.15) * frac

    def stage(self, gdd: float) -> tuple[Stage, Stage | None]:
        """(current stage, next stage or None)."""
        current = self.stages[0]
        nxt: Stage | None = None
        for i, s in enumerate(self.stages):
            if gdd >= s.gdd:
                current = s
                nxt = self.stages[i + 1] if i + 1 < len(self.stages) else None
        return current, nxt

    @property
    def season_gdd(self) -> float:
        return self.kc_gdd[-1]


CROPS: dict[str, Crop] = {
    "spring_wheat": Crop(
        key="spring_wheat", name="Spring wheat", base_c=0.0, cap_c=30.0,
        kc_ini=0.3, kc_mid=1.15, kc_end=0.3,
        kc_gdd=(250, 700, 1350, 1650), root_max_m=1.2, p=0.55,
        stages=(
            Stage(0, "seeded", 0), Stage(9, "emergence", 150), Stage(13, "3-leaf", 300),
            Stage(21, "tillering", 400), Stage(31, "stem elongation", 600),
            Stage(55, "heading", 950), Stage(65, "flowering", 1100),
            Stage(75, "milk", 1250), Stage(85, "soft dough", 1450), Stage(89, "maturity", 1650),
        ),
    ),
    "canola": Crop(
        key="canola", name="Canola", base_c=5.0, cap_c=30.0,
        kc_ini=0.35, kc_mid=1.1, kc_end=0.35,
        kc_gdd=(150, 450, 850, 1100), root_max_m=1.0, p=0.6,
        stages=(
            Stage(0, "seeded", 0), Stage(9, "emergence", 90), Stage(14, "4-leaf", 250),
            Stage(31, "bolting", 380), Stage(60, "first flower", 520),
            Stage(62, "20% bloom", 580), Stage(65, "full bloom", 650),
            Stage(69, "end of flowering", 800), Stage(80, "pod ripening", 950),
            Stage(89, "maturity", 1100),
        ),
    ),
    "potato": Crop(
        key="potato", name="Potato", base_c=7.0, cap_c=30.0,
        kc_ini=0.5, kc_mid=1.15, kc_end=0.75,
        kc_gdd=(250, 550, 1100, 1400), root_max_m=0.5, p=0.35,
        stages=(
            Stage(0, "planted", 0), Stage(9, "emergence", 250), Stage(40, "tuber initiation", 450),
            Stage(65, "full flower", 650), Stage(70, "tuber bulking", 750),
            Stage(91, "senescence", 1200), Stage(97, "vines dead", 1400),
        ),
    ),
}


def get_crop(key: str) -> Crop:
    try:
        return CROPS[key]
    except KeyError:
        raise ValueError(f"unknown crop {key!r}; known: {sorted(CROPS)}") from None
