"""
Atmos Core — Canonical Data Models
Every adapter, ingester, and analytics module outputs these types.
Nothing else flows into storage or the API layer.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any
import uuid
import json


# ─── Location ─────────────────────────────────────────────────────────────────

@dataclass
class Location:
    lat:     float
    lon:     float
    geohash: str  = ""
    city:    str  = ""
    country: str  = ""

    def __post_init__(self):
        if not self.geohash:
            self.geohash = _encode_geohash(self.lat, self.lon, precision=6)


# ─── Atmosphere ───────────────────────────────────────────────────────────────

@dataclass
class AtmosphereReading:
    # AQI
    aqi_us:  float | None = None
    aqi_eu:  float | None = None

    # Particulates (μg/m³)
    pm2_5:   float | None = None
    pm10:    float | None = None
    dust:    float | None = None

    # Gases (μg/m³)
    o3:      float | None = None
    no2:     float | None = None
    so2:     float | None = None
    co:      float | None = None

    # Aerosol
    aerosol_optical_depth: float | None = None

    # Category string: good / moderate / unhealthy_sg / unhealthy / very_unhealthy / hazardous
    category: str = "unknown"


# ─── Weather ──────────────────────────────────────────────────────────────────

@dataclass
class WeatherReading:
    temp_c:          float | None = None
    feels_like_c:    float | None = None
    humidity_pct:    float | None = None
    pressure_hpa:    float | None = None
    wind_speed_kmh:  float | None = None
    wind_dir_deg:    float | None = None
    wind_gusts_kmh:  float | None = None
    wind_cardinal:   str   = ""
    uv_index:        float | None = None
    visibility_m:    float | None = None
    cloud_cover_pct: float | None = None
    precip_mm:       float | None = None
    weather_code:    int   | None = None
    condition_label: str   = ""
    condition_icon:  str   = ""
    is_day:          bool  = True


# ─── Hazards ──────────────────────────────────────────────────────────────────

@dataclass
class FireDetection:
    lat:        float
    lon:        float
    frp_mw:     float  = 0.0   # Fire Radiative Power in megawatts
    confidence: str    = ""    # nominal / high / low
    date:       str    = ""
    time_utc:   str    = ""
    satellite:  str    = ""
    day_night:  str    = ""

@dataclass
class HazardReading:
    fire_nearby:          bool              = False
    fire_count_500km:     int               = 0
    fire_detections:      list[FireDetection] = field(default_factory=list)
    smoke_level:          str               = "unknown"  # clear/hazy/smoky/heavy_smoke/extreme
    aerosol_optical_depth: float | None     = None


# ─── Analytics ────────────────────────────────────────────────────────────────

@dataclass
class AnalyticsReading:
    dominant_source:     str        = "unknown"
    source_confidence:   int        = 0
    health_risk_general: str        = "unknown"   # good/moderate/high/extreme
    exceedances:         list[str]  = field(default_factory=list)
    alerts:              list[str]  = field(default_factory=list)


# ─── Canonical Atmospheric Snapshot ───────────────────────────────────────────

@dataclass
class AtmosphericSnapshot:
    """
    The single canonical event/data object for all of Atmos.

    This is:
      - the brain format
      - the storage format (maps 1:1 to atmospheric_snapshots table)
      - the API response format
      - the ML training format
      - the streaming event format
    """
    event_id:   str      = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:  datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    location:   Location          = field(default_factory=lambda: Location(0.0, 0.0))
    atmosphere: AtmosphereReading = field(default_factory=AtmosphereReading)
    weather:    WeatherReading    = field(default_factory=WeatherReading)
    hazards:    HazardReading     = field(default_factory=HazardReading)
    analytics:  AnalyticsReading  = field(default_factory=AnalyticsReading)

    # Source provenance — which APIs contributed to this snapshot
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, d: dict) -> "AtmosphericSnapshot":
        snap = cls()
        snap.event_id  = d.get("event_id", snap.event_id)
        snap.timestamp = _parse_dt(d.get("timestamp", ""))
        snap.sources   = d.get("sources", [])

        loc = d.get("location", {})
        snap.location = Location(
            lat=loc.get("lat", 0.0),
            lon=loc.get("lon", 0.0),
            geohash=loc.get("geohash", ""),
            city=loc.get("city", ""),
            country=loc.get("country", ""),
        )

        atm = d.get("atmosphere", {})
        snap.atmosphere = AtmosphereReading(**{
            k: atm.get(k) for k in AtmosphereReading.__dataclass_fields__
        })

        wx = d.get("weather", {})
        snap.weather = WeatherReading(**{
            k: wx.get(k) for k in WeatherReading.__dataclass_fields__
        })

        hz = d.get("hazards", {})
        fires = [FireDetection(**f) for f in hz.get("fire_detections", [])]
        snap.hazards = HazardReading(
            fire_nearby=hz.get("fire_nearby", False),
            fire_count_500km=hz.get("fire_count_500km", 0),
            fire_detections=fires,
            smoke_level=hz.get("smoke_level", "unknown"),
            aerosol_optical_depth=hz.get("aerosol_optical_depth"),
        )

        an = d.get("analytics", {})
        snap.analytics = AnalyticsReading(
            dominant_source=an.get("dominant_source", "unknown"),
            source_confidence=an.get("source_confidence", 0),
            health_risk_general=an.get("health_risk_general", "unknown"),
            exceedances=an.get("exceedances", []),
            alerts=an.get("alerts", []),
        )

        return snap


# ─── Geohash (self-contained, no external dep) ────────────────────────────────

_GH_CHARS = "0123456789bcdefghjkmnpqrstuvwxyz"

def _encode_geohash(lat: float, lon: float, precision: int = 6) -> str:
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    result, bits, bit_count = [], 0, 0
    use_lon = True
    while len(result) < precision:
        for _ in range(5):
            if use_lon:
                mid = (lon_range[0] + lon_range[1]) / 2
                if lon >= mid:
                    bits = (bits << 1) | 1
                    lon_range[0] = mid
                else:
                    bits = bits << 1
                    lon_range[1] = mid
            else:
                mid = (lat_range[0] + lat_range[1]) / 2
                if lat >= mid:
                    bits = (bits << 1) | 1
                    lat_range[0] = mid
                else:
                    bits = bits << 1
                    lat_range[1] = mid
            use_lon = not use_lon
            bit_count += 1
        result.append(_GH_CHARS[bits])
        bits = 0
    return "".join(result)


def _parse_dt(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.now(timezone.utc)
