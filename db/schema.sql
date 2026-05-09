"""
Atmos DB — Async PostgreSQL connection pool + query helpers
Uses asyncpg for high-performance async queries.
"""

import asyncpg
import json
import os
import logging
from datetime import datetime
from typing import Any

from core.models import AtmosphericSnapshot, FireDetection

log = logging.getLogger("atmos.db")

_pool: asyncpg.Pool | None = None


async def connect() -> asyncpg.Pool:
    global _pool
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL environment variable not set")

    _pool = await asyncpg.create_pool(
        dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
        # Register JSONB codec
        init=_init_conn,
    )
    log.info("Connected to TimescaleDB")
    return _pool


async def _init_conn(conn: asyncpg.Connection):
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def close():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Call connect() first.")
    return _pool


# ── Write ──────────────────────────────────────────────────────────────────────

async def insert_snapshot(snap: AtmosphericSnapshot) -> str:
    """Insert a canonical AtmosphericSnapshot. Returns event_id."""
    pool = get_pool()

    fire_ids = await _insert_fire_detections(snap)

    sql = """
    INSERT INTO atmospheric_snapshots (
        event_id, timestamp,
        lat, lon, geohash, city, country,
        aqi_us, aqi_eu, pm2_5, pm10, dust, o3, no2, so2, co,
        aerosol_optical_depth, aqi_category,
        temp_c, feels_like_c, humidity_pct, pressure_hpa,
        wind_speed_kmh, wind_dir_deg, wind_gusts_kmh, wind_cardinal,
        uv_index, visibility_m, cloud_cover_pct, precip_mm,
        weather_code, condition_label, is_day,
        fire_nearby, fire_count_500km, smoke_level,
        dominant_source, source_confidence, health_risk_general,
        exceedances, active_alerts, sources, raw_snapshot
    ) VALUES (
        $1, $2,
        $3, $4, $5, $6, $7,
        $8, $9, $10, $11, $12, $13, $14, $15, $16,
        $17, $18,
        $19, $20, $21, $22,
        $23, $24, $25, $26,
        $27, $28, $29, $30,
        $31, $32, $33,
        $34, $35, $36,
        $37, $38, $39,
        $40, $41, $42, $43
    )
    ON CONFLICT DO NOTHING
    RETURNING event_id
    """

    s = snap
    a = s.atmosphere
    w = s.weather
    h = s.hazards
    an = s.analytics

    row = await pool.fetchrow(sql,
        s.event_id, s.timestamp,
        s.location.lat, s.location.lon, s.location.geohash, s.location.city, s.location.country,
        a.aqi_us, a.aqi_eu, a.pm2_5, a.pm10, a.dust, a.o3, a.no2, a.so2, a.co,
        a.aerosol_optical_depth, a.category,
        w.temp_c, w.feels_like_c, w.humidity_pct, w.pressure_hpa,
        w.wind_speed_kmh, w.wind_dir_deg, w.wind_gusts_kmh, w.wind_cardinal,
        w.uv_index, w.visibility_m, w.cloud_cover_pct, w.precip_mm,
        w.weather_code, w.condition_label, w.is_day,
        h.fire_nearby, h.fire_count_500km, h.smoke_level,
        an.dominant_source, an.source_confidence, an.health_risk_general,
        an.exceedances, an.alerts, s.sources,
        s.to_dict(),
    )

    return str(row["event_id"]) if row else s.event_id


async def _insert_fire_detections(snap: AtmosphericSnapshot) -> list[str]:
    if not snap.hazards.fire_detections:
        return []
    pool = get_pool()
    sql = """
    INSERT INTO fire_detections
        (timestamp, lat, lon, frp_mw, confidence, satellite, day_night, snapshot_id)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    ON CONFLICT DO NOTHING
    RETURNING id::TEXT
    """
    ids = []
    async with pool.acquire() as conn:
        for f in snap.hazards.fire_detections:
            row = await conn.fetchrow(sql,
                snap.timestamp, f.lat, f.lon,
                f.frp_mw, f.confidence, f.satellite, f.day_night,
                snap.event_id,
            )
            if row:
                ids.append(row["id"])
    return ids


async def insert_alert(
    alert_type: str, severity: str, title: str, message: str,
    lat: float, lon: float, geohash: str, data: dict, snapshot_id: str | None = None,
):
    pool = get_pool()
    await pool.execute("""
    INSERT INTO alert_events
        (timestamp, lat, lon, geohash, alert_type, severity, title, message, data, snapshot_id)
    VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7, $8, $9)
    """, lat, lon, geohash, alert_type, severity, title, message, data, snapshot_id)


async def update_ingestion_job(job_id: str, status: str, records: int = 0, error: str | None = None):
    pool = get_pool()
    await pool.execute("""
    UPDATE ingestion_jobs
    SET status = $2, completed_at = NOW(), records_written = $3, error = $4,
        duration_ms = EXTRACT(EPOCH FROM (NOW() - started_at)) * 1000
    WHERE id = $1
    """, job_id, status, records, error)


# ── Read ───────────────────────────────────────────────────────────────────────

async def get_latest_snapshot(lat: float, lon: float, geohash: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow("""
    SELECT * FROM atmospheric_snapshots
    WHERE geohash = $1
    ORDER BY timestamp DESC
    LIMIT 1
    """, geohash)
    return dict(row) if row else None


async def get_aqi_trend(
    geohash: str,
    hours: int = 168,
) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("""
    SELECT bucket AS time, aqi_us_avg, aqi_us_max, pm2_5_avg
    FROM aqi_hourly_stats
    WHERE geohash = $1
      AND bucket > NOW() - ($2 * INTERVAL '1 hour')
    ORDER BY bucket ASC
    """, geohash, hours)
    return [dict(r) for r in rows]


async def get_fires_in_radius(lat: float, lon: float, radius_km: float, hours: int = 24) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch("""
    SELECT id, timestamp, lat, lon, frp_mw, confidence, satellite
    FROM fire_detections
    WHERE ST_DWithin(
        geom::geography,
        ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography,
        $3 * 1000
    )
    AND timestamp > NOW() - ($4 * INTERVAL '1 hour')
    ORDER BY timestamp DESC
    """, lat, lon, radius_km, hours)
    return [dict(r) for r in rows]


async def get_latest_all_locations() -> list[dict]:
    """Used by the global heatmap — one row per monitored location."""
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM latest_snapshots ORDER BY aqi_us DESC NULLS LAST")
    return [dict(r) for r in rows]


async def get_active_alerts(lat: float, lon: float, radius_km: float = 200) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch("""
    SELECT *
    FROM alert_events
    WHERE ST_DWithin(
        ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
        ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography,
        $3 * 1000
    )
    AND timestamp > NOW() - INTERVAL '6 hours'
    AND resolved_at IS NULL
    ORDER BY timestamp DESC
    """, lat, lon, radius_km)
    return [dict(r) for r in rows]


async def get_monitored_locations() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch("""
    SELECT * FROM monitored_locations
    WHERE active = TRUE
    ORDER BY priority ASC, city ASC
    """)
    return [dict(r) for r in rows]
