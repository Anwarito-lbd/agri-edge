"""Agronomy models, checked against their published references where one exists."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import pytest

from agri_edge.agronomy import disease, frost
from agri_edge.agronomy.crops import CROPS, get_crop
from agri_edge.agronomy.engine import FieldProfile, assess_field
from agri_edge.agronomy.et0 import (
    DayInputs,
    et0_hargreaves,
    et0_penman_monteith,
    extraterrestrial_radiation,
    sat_vapour_pressure,
    wind_at_2m,
)
from agri_edge.agronomy.gdd import accumulate, daily_gdd
from agri_edge.agronomy.soils import get_soil
from agri_edge.agronomy.water_balance import advise, run_balance
from agri_edge.agronomy.weather import (
    Day,
    Hour,
    WeatherSeries,
    merge_station,
    open_meteo_url,
    parse_open_meteo,
    station_days,
)

# -- FAO-56 reference values ---------------------------------------------------


def test_fao56_example_18_brussels():
    """FAO-56 Example 18: Brussels, 6 July -> ET0 = 3.9 mm/day."""
    d = DayInputs(doy=187, lat_deg=50 + 48 / 60, elevation_m=100, t_max=21.5, t_min=12.3,
                  rh_max=84, rh_min=63, u2=wind_at_2m(10 / 3.6, 10.0), sunshine_h=9.25)
    assert d.u2 == pytest.approx(2.078, abs=0.01)
    assert et0_penman_monteith(d) == pytest.approx(3.9, abs=0.05)


def test_fao56_intermediates():
    assert sat_vapour_pressure(21.5) == pytest.approx(2.564, abs=0.002)
    assert sat_vapour_pressure(12.3) == pytest.approx(1.431, abs=0.002)
    ra, n = extraterrestrial_radiation(50 + 48 / 60, 187)
    assert ra == pytest.approx(41.09, abs=0.1)
    assert n == pytest.approx(16.1, abs=0.1)


def test_hargreaves_is_in_the_same_range():
    pm = et0_penman_monteith(DayInputs(doy=187, lat_deg=50.8, elevation_m=100, t_max=21.5,
                                       t_min=12.3, rh_max=84, rh_min=63, u2=2.078,
                                       sunshine_h=9.25))
    hg = et0_hargreaves(187, 50.8, 21.5, 12.3)
    assert 0.6 * pm < hg < 1.4 * pm


def test_et0_rejects_inverted_temperatures():
    with pytest.raises(ValueError):
        et0_penman_monteith(DayInputs(doy=1, lat_deg=50, elevation_m=0, t_max=1, t_min=5))


def test_polar_latitudes_do_not_crash():
    ra, _ = extraterrestrial_radiation(80.0, 355)
    assert ra == 0.0


# -- crops, GDD ------------------------------------------------------------------


def test_gdd_clips_to_base_and_cap():
    assert daily_gdd(25, 15, 5, 30) == 15
    assert daily_gdd(35, 20, 5, 30) == pytest.approx(20)        # 35 counts as 30
    assert daily_gdd(8, -4, 5, 30) == pytest.approx(1.5)        # -4 counts as 5
    assert daily_gdd(3, -10, 5, 30) == 0


def test_stage_progresses_with_thermal_time():
    canola = get_crop("canola")
    start = date(2026, 5, 10)
    days = [(start + timedelta(days=i), 25.0, 13.0) for i in range(45)]   # 14 GDD/day
    s = accumulate(canola, start, days)
    assert s.gdd == pytest.approx(45 * 14)
    assert s.stage_bbch == 62 and s.stage_name == "20% bloom"
    assert s.next_stage == "full bloom"


@pytest.mark.parametrize("key", sorted(CROPS))
def test_every_crop_is_consistent(key):
    c = CROPS[key]
    assert list(c.kc_gdd) == sorted(c.kc_gdd)
    assert [s.gdd for s in c.stages] == sorted(s.gdd for s in c.stages)
    assert c.kc(0) == c.kc_ini and c.kc(c.kc_gdd[2]) == c.kc_mid and c.kc(1e6) == c.kc_end
    assert c.root_depth_m(0) == pytest.approx(0.15) and c.root_depth_m(1e6) == c.root_max_m


def test_unknown_crop_and_soil_are_refused():
    with pytest.raises(ValueError):
        get_crop("rice")
    with pytest.raises(ValueError):
        get_soil("moon_dust")


# -- weather -------------------------------------------------------------------


def _open_meteo_payload(start: date, n_days: int, *, tmax=26.0, tmin=12.0, rain=0.0,
                        rh_hourly=60.0, t_hourly=None):
    days = [(start + timedelta(days=i)).isoformat() for i in range(n_days)]
    hours = [(datetime.combine(start, datetime.min.time()) + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M")
             for h in range(24 * n_days)]
    return {
        "latitude": 50.45, "longitude": -104.6, "elevation": 577.0,
        "daily": {"time": days, "temperature_2m_max": [tmax] * n_days,
                  "temperature_2m_min": [tmin] * n_days, "precipitation_sum": [rain] * n_days,
                  "relative_humidity_2m_max": [85] * n_days, "relative_humidity_2m_min": [40] * n_days,
                  "shortwave_radiation_sum": [24.0] * n_days, "wind_speed_10m_mean": [4.0] * n_days},
        "hourly": {"time": hours,
                   "temperature_2m": [t_hourly(i) if t_hourly else 18.0 for i in range(len(hours))],
                   "relative_humidity_2m": [rh_hourly] * len(hours),
                   "precipitation": [0.0] * len(hours), "wind_speed_10m": [4.0] * len(hours),
                   "shortwave_radiation": [300.0] * len(hours)},
    }


def test_open_meteo_parse_labels_past_and_forecast():
    today = date(2026, 7, 20)
    ws = parse_open_meteo(_open_meteo_payload(today - timedelta(days=10), 17), today)
    assert len(ws.days) == 17 and len(ws.hours) == 17 * 24
    assert {d.source for d in ws.past(today)} == {"model"}
    assert {d.source for d in ws.ahead(today)} == {"forecast"}
    assert all(d.et0_mm and 3 < d.et0_mm < 9 for d in ws.days)
    assert ws.hours[0].time.tzinfo is not None


def test_open_meteo_url_asks_for_the_canadian_model():
    url = open_meteo_url(50.45, -104.6)
    assert "models=gem_seamless" in url and "wind_speed_unit=ms" in url


class _Obs:
    def __init__(self, ts, t, rh=60.0, rain=0.0, q="GOOD"):
        from agri_edge.ops.types import QualityFlag, TempKind, TypedTemperature
        self.ts, self.rh_pct, self.precip_mm = ts, rh, rain
        self.air_temp = TypedTemperature(t, TempKind.AIR)
        self.wind_ms, self.solar_wm2 = 2.0, None
        self.quality = QualityFlag(q)


def test_station_days_need_coverage_and_replace_model_days():
    d0 = date(2026, 7, 10)
    obs = [_Obs(datetime(2026, 7, 10, h, tzinfo=timezone.utc).isoformat(), 10 + h, rain=0.5)
           for h in range(24)]
    obs += [_Obs(datetime(2026, 7, 11, h, tzinfo=timezone.utc).isoformat(), 30) for h in range(3)]
    obs += [_Obs(datetime(2026, 7, 10, 12, tzinfo=timezone.utc).isoformat(), 99, q="BAD")]
    days = station_days(obs, 50.45, 577)
    assert set(days) == {d0}, "3 readings do not make a day; the BAD one is ignored"
    assert days[d0].t_max == 33 and days[d0].t_min == 10 and days[d0].precip_mm == pytest.approx(12)
    ws = parse_open_meteo(_open_meteo_payload(d0 - timedelta(days=2), 6), date(2026, 7, 13))
    merged = merge_station(ws, days)
    assert next(d for d in merged.days if d.date == d0).source == "station"


# -- water balance ---------------------------------------------------------------


def _days(start, n, tmax=28.0, tmin=14.0, rain=0.0, et0=6.0, source="model"):
    return [Day(start + timedelta(days=i), tmax, tmin, rain, source=source, et0_mm=et0)
            for i in range(n)]


def test_dry_spell_leads_to_irrigation_with_reasons():
    crop, soil = get_crop("potato"), get_soil("sandy_loam")
    seeded = date(2026, 5, 20)
    today = seeded + timedelta(days=60)
    bal = run_balance(crop, soil, seeded, _days(seeded, 67))
    a = advise(bal, today)
    assert a.action == "irrigate" and a.amount_mm > 0
    assert any("stress threshold" in w for w in a.why)
    assert a.depletion_mm <= a.taw_mm


def test_forecast_rain_turns_irrigate_into_wait():
    crop, soil = get_crop("potato"), get_soil("sandy_loam")
    seeded = date(2026, 5, 20)
    today = seeded + timedelta(days=60)
    days = _days(seeded, 60) + _days(today, 3, rain=40.0)
    a = advise(run_balance(crop, soil, seeded, days), today)
    assert a.action == "wait"


def test_rain_refills_and_no_irrigation_is_needed():
    crop, soil = get_crop("spring_wheat"), get_soil("silt_loam")
    seeded = date(2026, 5, 1)
    today = seeded + timedelta(days=40)
    days = _days(seeded, 47, rain=8.0, et0=4.0)
    a = advise(run_balance(crop, soil, seeded, days), today)
    assert a.action == "none"
    assert a.depletion_mm < a.raw_mm


def test_probe_reading_resets_the_model():
    crop, soil = get_crop("potato"), get_soil("loam")
    seeded = date(2026, 5, 20)
    probe_day = seeded + timedelta(days=50)
    bal = run_balance(crop, soil, seeded, _days(seeded, 55),
                      probe_vwc={probe_day: soil.theta_fc})     # probe says: full
    b = next(x for x in bal if x.date == probe_day.isoformat())
    assert b.probe_reset and b.depletion_mm == 0
    assert advise(bal, probe_day + timedelta(days=2)).confidence == "high"


def test_no_weather_is_no_data_not_a_guess():
    a = advise([], date(2026, 7, 1))
    assert a.action == "no-data" and a.confidence == "low"


# -- disease ---------------------------------------------------------------------


def _series_with_hours(today, rh, temp, days_back=14, days_ahead=3, rain=0.0):
    start = today - timedelta(days=days_back)
    ws = WeatherSeries(50.0, -100.0, 500.0)
    for i in range(days_back + days_ahead):
        d = start + timedelta(days=i)
        ws.days.append(Day(d, temp + 5, temp - 5, rain, source="model" if d < today else "forecast"))
        for h in range(24):
            t = datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=h)
            ws.hours.append(Hour(t, temp, rh(h) if callable(rh) else rh, 0.0))
    return ws


def test_sclerotinia_only_in_flower_and_high_when_wet():
    today = date(2026, 7, 10)
    wet = _series_with_hours(today, 95.0, 18.0, rain=3.0)
    assert disease.sclerotinia_canola(wet, today, bbch=31).level == "none"
    r = disease.sclerotinia_canola(wet, today, bbch=62)
    assert r.level == "high" and any("14 days" in w for w in r.why)
    assert "field history of sclerotinia" in r.missing
    dry = _series_with_hours(today, 45.0, 22.0)
    assert disease.sclerotinia_canola(dry, today, bbch=62).level == "low"


def test_fhb_counts_warm_humid_hours_at_flowering():
    today = date(2026, 7, 20)
    humid_nights = _series_with_hours(today, lambda h: 95.0 if h < 6 else 50.0, 18.0)
    r = disease.fhb_wheat(humid_nights, today, bbch=61)
    assert r.level == "high"                       # 6 h x 7 days = 42 h
    cold = _series_with_hours(today, 95.0, 8.0)    # humid but too cold
    assert disease.fhb_wheat(cold, today, bbch=61).level == "low"
    assert not disease.fhb_wheat(humid_nights, today, bbch=31).in_window


def test_hutton_period_for_late_blight():
    today = date(2026, 8, 1)
    muggy = _series_with_hours(today, lambda h: 95.0 if h < 8 else 70.0, 15.0)
    r = disease.late_blight_potato(muggy, today, bbch=40)
    assert r.level == "high" and "Hutton" in r.why[0]
    cool = _series_with_hours(today, 95.0, 8.0)    # humid but min < 10 C
    assert disease.late_blight_potato(cool, today, bbch=40).level == "low"


# -- frost -----------------------------------------------------------------------


def test_frost_severity_depends_on_stage():
    today = date(2026, 6, 1)
    ws = WeatherSeries(50.0, -100.0, 500.0, days=[Day(today, 8.0, -2.5, source="forecast")])
    assert frost.assess("canola", ws, today, bbch=62).level == "damaging"   # flowering: -2.0
    assert frost.assess("canola", ws, today, bbch=20).level == "frost"      # rosette: -4.0
    mild = WeatherSeries(50.0, -100.0, 500.0, days=[Day(today, 15.0, 1.5, source="forecast")])
    assert frost.assess("canola", mild, today, bbch=20).level == "watch"


# -- engine ----------------------------------------------------------------------


def test_field_assessment_explains_itself():
    today = date(2026, 7, 15)
    seeded = today - timedelta(days=38)     # 16 GDD/day (base 5) x 38 = 608: in bloom
    ws = parse_open_meteo(_open_meteo_payload(seeded, 45, tmax=28.0, tmin=14.0,
                                              rh_hourly=95.0), today)
    profile = FieldProfile("north", "North quarter", "canola", seeded.isoformat(), "loam",
                           50.45, -104.6, 577.0, irrigated=True).validate()
    out = assess_field(profile, ws, today)
    kinds = [r["kind"] for r in out["recommendations"]]
    assert "stage" in kinds
    assert 60 <= out["season"]["stage_bbch"] <= 69
    assert "disease" in kinds, "flowering canola in saturated air"
    for r in out["recommendations"]:
        assert r["why"], f"{r['title']} has no explanation"
        assert r["sources"] == ["model"]
    priorities = [r["priority"] for r in out["recommendations"]]
    assert priorities == sorted(priorities)
    assert out["calibrated"] is False


def test_field_profile_validation():
    with pytest.raises(ValueError):
        FieldProfile("x", "x", "canola", "2026-05-01", "loam", 95.0, 0.0).validate()
    with pytest.raises(ValueError):
        FieldProfile("a/b", "x", "canola", "2026-05-01", "loam", 50.0, 0.0).validate()
    assert math.isfinite(FieldProfile("ok", "x", "potato", "2026-05-01", "sand", 50, -100).validate().lat)
