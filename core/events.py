"""
Atmos Core — Events
Typed event definitions for the ingestion pipeline.
Every background worker emits these; every consumer reads these.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
import json

from core.models import AtmosphericSnapshot


class EventType(str, Enum):
    SNAPSHOT_INGESTED   = "snapshot.ingested"     # new AtmosphericSnapshot written to DB
    ALERT_TRIGGERED     = "alert.triggered"       # an alert threshold crossed
    ALERT_CLEARED       = "alert.cleared"         # alert condition resolved
    FIRE_DETECTED       = "fire.detected"         # new fire detection appeared
    ANOMALY_DETECTED    = "anomaly.detected"      # AQI / weather anomaly
    INGESTION_FAILED    = "ingestion.failed"      # worker failed to fetch / normalize
    INGESTION_STARTED   = "ingestion.started"     # worker cycle began
    INGESTION_COMPLETED = "ingestion.completed"   # worker cycle finished


class Severity(str, Enum):
    INFO     = "info"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


@dataclass
class AtmosEvent:
    event_id:   str       = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.SNAPSHOT_INGESTED
    timestamp:  datetime  = field(default_factory=lambda: datetime.now(timezone.utc))
    severity:   Severity  = Severity.INFO
    payload:    dict      = field(default_factory=dict)
    source:     str       = ""   # which worker/service emitted this

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"]  = self.timestamp.isoformat()
        d["event_type"] = self.event_type.value
        d["severity"]   = self.severity.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


# ─── Event Factories ──────────────────────────────────────────────────────────

def snapshot_ingested(snap: AtmosphericSnapshot, source: str = "ingester") -> AtmosEvent:
    return AtmosEvent(
        event_type=EventType.SNAPSHOT_INGESTED,
        severity=Severity.INFO,
        source=source,
        payload={
            "event_id":  snap.event_id,
            "lat":       snap.location.lat,
            "lon":       snap.location.lon,
            "geohash":   snap.location.geohash,
            "aqi_us":    snap.atmosphere.aqi_us,
            "pm2_5":     snap.atmosphere.pm2_5,
            "category":  snap.atmosphere.category,
            "temp_c":    snap.weather.temp_c,
            "timestamp": snap.timestamp.isoformat(),
        },
    )


def alert_triggered(title: str, message: str, severity: Severity, data: dict, source: str = "alert_engine") -> AtmosEvent:
    return AtmosEvent(
        event_type=EventType.ALERT_TRIGGERED,
        severity=severity,
        source=source,
        payload={"title": title, "message": message, "data": data},
    )


def fire_detected(lat: float, lon: float, frp_mw: float, confidence: str, source: str = "nasa-firms") -> AtmosEvent:
    return AtmosEvent(
        event_type=EventType.FIRE_DETECTED,
        severity=Severity.HIGH if confidence == "high" else Severity.MEDIUM,
        source=source,
        payload={"lat": lat, "lon": lon, "frp_mw": frp_mw, "confidence": confidence},
    )


def anomaly_detected(metric: str, value: float, expected: float, lat: float, lon: float) -> AtmosEvent:
    return AtmosEvent(
        event_type=EventType.ANOMALY_DETECTED,
        severity=Severity.HIGH,
        source="anomaly_engine",
        payload={
            "metric":   metric,
            "value":    value,
            "expected": expected,
            "delta":    round(value - expected, 2),
            "lat":      lat,
            "lon":      lon,
        },
    )


def ingestion_failed(worker: str, error: str, lat: float | None = None, lon: float | None = None) -> AtmosEvent:
    return AtmosEvent(
        event_type=EventType.INGESTION_FAILED,
        severity=Severity.MEDIUM,
        source=worker,
        payload={"error": error, "lat": lat, "lon": lon},
    )
