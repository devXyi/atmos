"""
Atmos Core
Canonical data models, normalizers, geo utilities, and event types.
Import from here, not from submodules directly.
"""

from core.models import (
    AtmosphericSnapshot,
    AtmosphereReading,
    WeatherReading,
    HazardReading,
    FireDetection,
    AnalyticsReading,
    Location,
)
from core.normalizers import (
    normalize_weather,
    normalize_aqi,
    normalize_fires,
    normalize_analytics,
    build_snapshot,
)
from core.geo import (
    haversine_km,
    bounding_box,
    bbox_string,
    generate_grid,
    deg_to_cardinal,
    encode_geohash,
    decode_geohash,
    geohash_neighbors,
)
from core.events import (
    AtmosEvent,
    EventType,
    Severity,
    snapshot_ingested,
    alert_triggered,
    fire_detected,
    anomaly_detected,
    ingestion_failed,
)

__all__ = [
    "AtmosphericSnapshot", "AtmosphereReading", "WeatherReading",
    "HazardReading", "FireDetection", "AnalyticsReading", "Location",
    "normalize_weather", "normalize_aqi", "normalize_fires",
    "normalize_analytics", "build_snapshot",
    "haversine_km", "bounding_box", "bbox_string", "generate_grid",
    "deg_to_cardinal", "encode_geohash", "decode_geohash", "geohash_neighbors",
    "AtmosEvent", "EventType", "Severity",
    "snapshot_ingested", "alert_triggered", "fire_detected",
    "anomaly_detected", "ingestion_failed",
]
