"""Synthetic demo data generators — always synthetic=True (§153–154)."""
from __future__ import annotations

import random
from typing import Any

from .types import (
    CalibrationRecord,
    DataOrigin,
    Device,
    DeviceType,
    QualityFlag,
    SoilObservation,
    TempKind,
    TypedTemperature,
    WeatherAggregate,
    WeatherObservation,
    new_id,
    utcnow,
)
from .schema import (
    WaterUsageEvent,
    VisionTreatmentEvent,
    MissionEnergyLog,
    MobileNote,
    ManualObservation,
    ScoutReport,
    CameraEvent,
    DeviceHealth,
    FlowMeter,
    GreenhouseZone,
    PestObservation,
    Pump,
    RTKStation,
    ServiceStation,
    Tank,
    Task,
    Valve,
    WaterSource,
)
from .geo import default_map_assets
from .store import OpsStore
from .derived import derive_from_weather
from .quality import evaluate_soil_reading, evaluate_weather_reading


def seed_demo(store: OpsStore, *, seed: int = 42) -> dict[str, Any]:
    rng = random.Random(seed)
    store.simulation_mode = True

    wx = Device(
        device_id="wx1",
        device_type=DeviceType.WEATHER_STATION,
        name="WX-1",
        lat=45.402,
        lon=-75.697,
        battery_pct=88.0,
        signal_rssi=-70.0,
        last_seen=utcnow().isoformat(),
        synthetic=True,
    )
    soil = Device(
        device_id="soil1",
        device_type=DeviceType.SOIL_MULTI_DEPTH,
        name="SOIL-1",
        lat=45.403,
        lon=-75.696,
        battery_pct=12.0,  # triggers low battery quality
        signal_rssi=-96.0,
        last_seen=utcnow().isoformat(),
        synthetic=True,
    )
    gw = Device(
        device_id="gw1",
        device_type=DeviceType.GATEWAY,
        name="Edge Gateway",
        synthetic=True,
    )
    store.devices[wx.device_id] = wx
    store.devices[soil.device_id] = soil
    store.devices[gw.device_id] = gw

    air_c = 18.5 + rng.uniform(-2, 2)
    rh = 65.0 + rng.uniform(-10, 10)
    q = evaluate_weather_reading(air_c, rh)
    obs = WeatherObservation(
        obs_id=new_id("wo_"),
        station_id=wx.device_id,
        ts=utcnow().isoformat(),
        air_temp=TypedTemperature(value_c=round(air_c, 2), kind=TempKind.AIR, origin=DataOrigin.MEASURED),
        rh_pct=round(rh, 1),
        wind_ms=round(rng.uniform(0.5, 4.0), 2),
        wind_dir_deg=round(rng.uniform(0, 360), 1),
        precip_mm=0.0,
        pressure_hpa=1013.0,
        solar_wm2=400.0,
        quality=q.flag,
        origin=DataOrigin.SIMULATED,
        synthetic=True,
    )
    store.persist_weather(obs)
    store.weather_aggs.append(
        WeatherAggregate(
            agg_id=new_id("wa_"),
            station_id=wx.device_id,
            period="hour",
            start_ts=obs.ts,
            end_ts=obs.ts,
            air_temp_min_c=air_c - 1,
            air_temp_max_c=air_c + 1,
            air_temp_mean_c=air_c,
            precip_sum_mm=0.0,
            wind_max_ms=obs.wind_ms,
            sample_count=1,
            synthetic=True,
        )
    )

    for depth in (10.0, 30.0, 60.0):
        moist = round(rng.uniform(15, 35), 1)
        sq = evaluate_soil_reading(
            moist,
            battery_pct=soil.battery_pct,
            signal_rssi=soil.signal_rssi,
            days_since_cal=400.0,
        )
        store.soil.append(
            SoilObservation(
                obs_id=new_id("so_"),
                probe_id=soil.device_id,
                ts=utcnow().isoformat(),
                depth_cm=depth,
                moisture_pct=moist,
                soil_temp=TypedTemperature(
                    value_c=round(12 + depth * 0.05, 2),
                    kind=TempKind.SOIL,
                    origin=DataOrigin.MEASURED,
                ),
                quality=sq.flag,
                origin=DataOrigin.SIMULATED,
                synthetic=True,
                zone_id="zone_a",
            )
        )

    for d in (wx, soil, gw):
        store.health[d.device_id] = DeviceHealth(
            device_id=d.device_id,
            ts=utcnow().isoformat(),
            online=True,
            battery_pct=d.battery_pct,
            signal_rssi=getattr(d, "signal_rssi", None),
            firmware="sim-1.0",
            pack_id=f"pack_{d.device_id}",
            cycles=12 + (abs(hash(d.device_id)) % 40),
            soh=95.0 - (abs(hash(d.device_id)) % 10),
            synthetic=True,
        )

    store.water_sources["ws1"] = WaterSource(source_id="ws1", name="Well 1", kind="well", synthetic=True)
    store.tanks["tk1"] = Tank(tank_id="tk1", name="Main tank", capacity_l=10000, level_pct=72.0, source_id="ws1", synthetic=True)
    store.pumps["pu1"] = Pump(pump_id="pu1", name="Pump A", rated_lpm=120, running=False, synthetic=True)
    store.valves["v1"] = Valve(valve_id="v1", name="Zone A valve", zone_id="zone_a", open_pct=0.0, synthetic=True)
    store.flow_meters["fm1"] = FlowMeter(meter_id="fm1", name="FM Zone A", zone_id="zone_a", last_lpm=0.0, synthetic=True)

    for asset in default_map_assets():
        store.map_assets[asset.asset_id] = asset

    store.rtk["rtk_base"] = RTKStation(station_id="rtk_base", name="RTK Base", kind="base", lat=45.40, lon=-75.70, fix_quality="fixed", synthetic=True)
    store.service_stations["svc1"] = ServiceStation(
        station_id="svc1", name="Pad 1", lat=45.399, lon=-75.701, status="idle", synthetic=True
    )
    store.greenhouse["gh1"] = GreenhouseZone(zone_id="gh1", name="Tunnel 1", target_air_c=22.0, actuators_automated=False, synthetic=True)
    store.pests.append(
        PestObservation(obs_id=new_id("pe_"), ts=utcnow().isoformat(), species="aphid", count=3, zone_id="zone_a", source="manual", synthetic=True)
    )
    store.tasks["t1"] = Task(task_id="t1", title="Check frost cloth", status="open", assignee="operator", synthetic=True)
    store.calibrations.append(
        CalibrationRecord(cal_id="cal1", device_id="soil1", calibrated_at="2025-01-01T00:00:00+00:00", next_due="2026-01-01T00:00:00+00:00", synthetic=True)
    )

    # Raise a frost-watch style alert from slightly cool air for demo variety
    cool = TypedTemperature(value_c=1.5, kind=TempKind.AIR)
    store.alerts.evaluate_temperature(cool, device_id="wx1", synthetic=True)

    derived = derive_from_weather(air_c, rh)
    store.add_audit("system", "seed_demo", "store", "synthetic demo seeded", role="admin")

    
    # --- §110–111 map layers already via default_map_assets (enriched in geo) ---
    # --- §132 water commanded vs measured ---
    store.water_usage.append(
        WaterUsageEvent(
            event_id=new_id("wu_"),
            zone_id="zone_a",
            start_ts=utcnow().isoformat(),
            end_ts=utcnow().isoformat(),
            volume_l=250.0,
            commanded_volume_l=200.0,
            measured_volume_l=250.0,
            reason="irrigation",
            synthetic=True,
        )
    )
    store.water_usage.append(
        WaterUsageEvent(
            event_id=new_id("wu_"),
            zone_id="zone_b",
            start_ts=utcnow().isoformat(),
            volume_l=100.0,
            commanded_volume_l=100.0,
            measured_volume_l=98.0,
            reason="irrigation",
            synthetic=True,
        )
    )
    # --- §131 mission energy ---
    store.mission_energy.append(
        MissionEnergyLog(
            mission_id="msn_demo_1",
            vehicle_id="ugv_sim_1",
            energy_kwh=1.25,
            duration_s=1800,
            ts=utcnow().isoformat(),
            synthetic=True,
        )
    )
    store.mission_energy.append(
        MissionEnergyLog(
            mission_id="msn_demo_2",
            vehicle_id="ugv_sim_1",
            energy_kwh=0.85,
            duration_s=1200,
            ts=utcnow().isoformat(),
            synthetic=True,
        )
    )
    # --- §133 vision + treatment ---
    store.vision_events.extend([
        VisionTreatmentEvent(event_id=new_id("vt_"), ts=utcnow().isoformat(), kind="weed_detected", lat=45.401, lon=-75.698, confidence=0.91, synthetic=True),
        VisionTreatmentEvent(event_id=new_id("vt_"), ts=utcnow().isoformat(), kind="treated", lat=45.401, lon=-75.698, confidence=0.91, synthetic=True),
        VisionTreatmentEvent(event_id=new_id("vt_"), ts=utcnow().isoformat(), kind="weed_detected", lat=45.402, lon=-75.697, confidence=0.77, synthetic=True),
        VisionTreatmentEvent(event_id=new_id("vt_"), ts=utcnow().isoformat(), kind="skipped", lat=45.402, lon=-75.697, confidence=0.77, reason="buffer_zone", synthetic=True),
        VisionTreatmentEvent(event_id=new_id("vt_"), ts=utcnow().isoformat(), kind="weed_detected", lat=45.403, lon=-75.696, confidence=0.88, synthetic=True),
        VisionTreatmentEvent(event_id=new_id("vt_"), ts=utcnow().isoformat(), kind="treated", lat=45.403, lon=-75.696, confidence=0.88, synthetic=True),
    ])
    # --- §142–144, §149 ---
    store.cameras.append(
        CameraEvent(event_id=new_id("cam_"), camera_id="cam_gate", ts=utcnow().isoformat(), label="wildlife", confidence=0.82, image_path="sim://cam/wildlife.jpg", synthetic=True)
    )
    store.scouts.append(
        ScoutReport(report_id=new_id("sc_"), ts=utcnow().isoformat(), scout_id="scout_a", notes="Edge weeds near ditch", zone_id="zone_a", synthetic=True)
    )
    store.manual.append(
        ManualObservation(obs_id=new_id("mo_"), ts=utcnow().isoformat(), observer="operator", text="Standing water after rain", category="water", lat=45.4015, lon=-75.6975, synthetic=True)
    )
    store.notes.append(
        MobileNote(note_id=new_id("mn_"), ts=utcnow().isoformat(), author="operator", text="Check valve v1 tomorrow", lat=45.401, lon=-75.698, synthetic=True)
    )

    return {
        "simulation": True,
        "synthetic": True,
        "cameras": len(store.cameras),
        "mission_energy": len(store.mission_energy),
        "vision_events": len(store.vision_events),
        "devices": len(store.devices),
        "weather": len(store.weather),
        "soil": len(store.soil),
        "derived": derived,
        "alerts": len(store.alerts.list_alerts()),
    }
