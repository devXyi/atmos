"""
Atmos Core — Normalizers
Raw API responses → AtmosphericSnapshot

Every adapter in data_engine/adapters/ returns its own raw dict.
These normalizers translate that into the canonical model.
The adapters themselves are untouched — normalizers are a separate concern.
"""

from __future__ import annotations
from datetime import datetime, timezone

from core.models import (
    AtmosphericSnapshot,
    AtmosphereReading,
    WeatherReading,
    HazardReading,
    FireDetection,
    AnalyticsReading,
    Location,
)


# ─── Weather Normalizer ───────────────────────────────────────────────────────

def normalize_weather(raw: dict, snap: AtmosphericSnapshot) -> AtmosphericSnapshot:
    """
    Merges Open-Meteo current weather response into an AtmosphericSnapshot.
    Can be called on an existing snapshot to enrich it.
    """
    if not raw:
        return snap

    loc = raw.get("location", {})
    if loc:
        snap.location.lat = loc.get("lat", snap.location.lat)
        snap.location.lon = loc.get("lon", snap.location.lon)

    t   = raw.get("temperature", {})
    w   = raw.get("wind", {})
    cond = raw.get("condition", {})

    snap.weather = WeatherReading(
        temp_c          = t.get("celsius"),
        feels_like_c    = t.get("feels_like"),
        humidity_pct    = raw.get("humidity"),
        pressure_hpa    = raw.get("pressure"),
        wind_speed_kmh  = w.get("speed_kmh"),
        wind_dir_deg    = w.get("direction_deg"),
        wind_gusts_kmh  = w.get("gusts_kmh"),
        wind_cardinal   = w.get("cardinal", ""),
        uv_index        = raw.get("uv_index"),
        visibility_m    = raw.get("visibility_m"),
        cloud_cover_pct = raw.get("cloud_cover_pct"),
        precip_mm       = raw.get("precipitation_mm"),
        weather_code    = cond.get("code"),
        condition_label = cond.get("label", ""),
        condition_icon  = cond.get("icon", ""),
        is_day          = raw.get("is_day", True),
    )

    if "open-meteo" not in snap.sources:
        snap.sources.append("open-meteo")

    return snap


# ─── AQI Normalizer ───────────────────────────────────────────────────────────

def normalize_aqi(raw: dict, snap: AtmosphericSnapshot) -> AtmosphericSnapshot:
    """
    Merges AQI adapter response (unified WAQI + Open-Meteo AQ) into snapshot.
    """
    if not raw:
        return snap

    p = raw.get("pollutants", {})

    def _v(key: str) -> float | None:
        entry = p.get(key)
        if entry is None:
            return None
        if isinstance(entry, dict):
            return entry.get("value")
        return entry

    snap.atmosphere = AtmosphereReading(
        aqi_us   = raw.get("aqi_us") or raw.get("aqi"),
        aqi_eu   = raw.get("aqi_eu"),
        pm2_5    = _v("pm2_5"),
        pm10     = _v("pm10"),
        dust     = _v("dust"),
        o3       = _v("ozone"),
        no2      = _v("nitrogen_dioxide"),
        so2      = _v("sulphur_dioxide"),
        co       = _v("carbon_monoxide"),
        category = (raw.get("category") or {}).get("level", "unknown"),
    )

    for src in (raw.get("source") or []):
        if src not in snap.sources:
            snap.sources.append(src)

    return snap


# ─── Satellite Normalizer ─────────────────────────────────────────────────────

def normalize_fires(raw_fires: dict, raw_smoke: dict | None, snap: AtmosphericSnapshot) -> AtmosphericSnapshot:
    """
    Merges NASA FIRMS fire detections + Open-Meteo aerosol into snapshot.
    """
    fires_list = (raw_fires or {}).get("fires", [])
    detections = [
        FireDetection(
            lat=f.get("lat", 0.0),
            lon=f.get("lon", 0.0),
            frp_mw=f.get("frp", 0.0),
            confidence=f.get("confidence", ""),
            date=f.get("date", ""),
            time_utc=f.get("time_utc", ""),
            satellite=f.get("satellite", ""),
            day_night=f.get("day_night", ""),
        )
        for f in fires_list
    ]

    smoke_cur = (raw_smoke or {}).get("current", {})
    smoke_lvl = smoke_cur.get("smoke_level", "unknown")
    aod       = smoke_cur.get("aerosol_optical_depth")

    snap.hazards = HazardReading(
        fire_nearby          = len(detections) > 0,
        fire_count_500km     = len(detections),
        fire_detections      = detections,
        smoke_level          = smoke_lvl,
        aerosol_optical_depth = aod,
    )

    # Mirror AOD into atmosphere too
    if aod is not None:
        snap.atmosphere.aerosol_optical_depth = aod

    if detections:
        snap.sources.append("nasa-firms")
    if raw_smoke:
        if "open-meteo-aq" not in snap.sources:
            snap.sources.append("open-meteo-aq")

    return snap


# ─── Analytics Normalizer ─────────────────────────────────────────────────────

def normalize_analytics(
    health_raw: dict | None,
    sources_raw: dict | None,
    alerts_raw: dict | None,
    snap: AtmosphericSnapshot,
) -> AtmosphericSnapshot:
    """
    Merges analytics layer outputs into the snapshot's analytics field.
    """
    dominant_source = "unknown"
    source_conf     = 0
    health_risk     = "unknown"
    exceedances     = []
    alert_titles    = []

    if sources_raw:
        srcs = sources_raw.get("sources", [])
        if srcs:
            top = srcs[0]
            dominant_source = top.get("type", "unknown")
            source_conf     = top.get("confidence", 0)

    if health_raw:
        risks = health_raw.get("risks", {})
        general = risks.get("general_population", {})
        health_risk = general.get("risk_level", "unknown")
        exceedances = health_raw.get("exceedances", [])

    if alerts_raw:
        for a in (alerts_raw.get("alerts") or []):
            if isinstance(a, dict):
                alert_titles.append(a.get("title", ""))

    snap.analytics = AnalyticsReading(
        dominant_source     = dominant_source,
        source_confidence   = source_conf,
        health_risk_general = health_risk,
        exceedances         = exceedances,
        alerts              = alert_titles,
    )

    return snap


# ─── Full composite normalizer ────────────────────────────────────────────────

def build_snapshot(
    lat: float,
    lon: float,
    weather_raw:  dict | None = None,
    aqi_raw:      dict | None = None,
    fires_raw:    dict | None = None,
    smoke_raw:    dict | None = None,
    health_raw:   dict | None = None,
    sources_raw:  dict | None = None,
    alerts_raw:   dict | None = None,
) -> AtmosphericSnapshot:
    """
    Full pipeline: raw API dicts → canonical AtmosphericSnapshot.
    Call this anywhere you need a complete snapshot.
    """
    snap = AtmosphericSnapshot()
    snap.location = Location(lat=lat, lon=lon)
    snap.timestamp = datetime.now(timezone.utc)

    if weather_raw:
        normalize_weather(weather_raw, snap)
    if aqi_raw:
        normalize_aqi(aqi_raw, snap)
    if fires_raw or smoke_raw:
        normalize_fires(fires_raw or {}, smoke_raw, snap)
    if health_raw or sources_raw or alerts_raw:
        normalize_analytics(health_raw, sources_raw, alerts_raw, snap)

    return snap
