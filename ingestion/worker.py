"""
Atmos Ingestion Worker
Continuous background pipeline:
  Monitored Locations → Fetch APIs → Normalize → AtmosphericSnapshot → TimescaleDB

Run standalone:
    python -m ingestion.worker

Or imported and scheduled by the main data_engine.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

from adapters.open_meteo import OpenMeteoAdapter
from adapters.aqi import AQIAdapter
from adapters.satellite import SatelliteAdapter
from analytics import HealthRiskAnalyzer, AlertEngine
from core.normalizers import build_snapshot
from core.events import snapshot_ingested, ingestion_failed, alert_triggered
from core.models import AtmosphericSnapshot
from core.geo import encode_geohash
import db.database as db

log = logging.getLogger("atmos.ingester")

# Adapters (shared across all worker tasks)
_weather_adapter   = OpenMeteoAdapter()
_aqi_adapter       = AQIAdapter()
_satellite_adapter = SatelliteAdapter()
_health_analyzer   = HealthRiskAnalyzer()
_alert_engine      = AlertEngine()


async def ingest_location(lat: float, lon: float, city: str = "", country: str = "") -> AtmosphericSnapshot | None:
    """
    Full ingestion pipeline for a single location.
    Fetches all sources in parallel, normalizes to AtmosphericSnapshot, writes to DB.
    Returns the snapshot or None on failure.
    """
    job_id = str(uuid.uuid4())
    geohash = encode_geohash(lat, lon, precision=6)

    log.info(f"[ingest] {city or geohash} ({lat:.3f},{lon:.3f})")

    # Register job
    await db.get_pool().execute("""
    INSERT INTO ingestion_jobs (id, worker, lat, lon, status)
    VALUES ($1, 'continuous_worker', $2, $3, 'running')
    """, job_id, lat, lon)

    try:
        # ── Parallel fetch ────────────────────────────────────────────────────
        results = await asyncio.gather(
            _weather_adapter.get_current(lat, lon),
            _aqi_adapter.get_current(lat, lon),
            _satellite_adapter.get_active_fires(lat, lon, radius_km=500),
            _satellite_adapter.get_smoke_data(lat, lon),
            return_exceptions=True,
        )

        weather_raw = results[0] if not isinstance(results[0], Exception) else None
        aqi_raw     = results[1] if not isinstance(results[1], Exception) else None
        fires_raw   = results[2] if not isinstance(results[2], Exception) else None
        smoke_raw   = results[3] if not isinstance(results[3], Exception) else None

        # Log any partial failures without aborting
        for i, (name, res) in enumerate(zip(
            ["weather", "aqi", "fires", "smoke"], results
        )):
            if isinstance(res, Exception):
                log.warning(f"[ingest] {name} fetch failed for {city}: {res}")

        # ── Analytics ─────────────────────────────────────────────────────────
        health_raw  = _health_analyzer.compute(aqi_raw)   if aqi_raw     else None
        sources_raw = _health_analyzer.estimate_sources(weather_raw, aqi_raw) if (weather_raw and aqi_raw) else None
        alerts_raw  = {"alerts": _alert_engine.evaluate(weather_raw, aqi_raw)}

        # ── Normalize → canonical snapshot ────────────────────────────────────
        snap = build_snapshot(
            lat=lat, lon=lon,
            weather_raw=weather_raw,
            aqi_raw=aqi_raw,
            fires_raw=fires_raw,
            smoke_raw=smoke_raw,
            health_raw=health_raw,
            sources_raw=sources_raw,
            alerts_raw=alerts_raw,
        )
        snap.location.city    = city
        snap.location.country = country

        # ── Persist ───────────────────────────────────────────────────────────
        await db.insert_snapshot(snap)

        # ── Persist alerts to alert_events table ──────────────────────────────
        for alert in _alert_engine.evaluate(weather_raw, aqi_raw):
            sev_map = {"critical": "critical", "high": "high", "medium": "medium"}
            await db.insert_alert(
                alert_type  = alert.get("type", "UNKNOWN"),
                severity    = sev_map.get(alert.get("severity", ""), "medium"),
                title       = alert.get("title", ""),
                message     = alert.get("message", ""),
                lat         = lat,
                lon         = lon,
                geohash     = geohash,
                data        = alert.get("data", {}),
                snapshot_id = snap.event_id,
            )

        # ── Update last_ingested on monitored_locations ───────────────────────
        await db.get_pool().execute("""
        UPDATE monitored_locations
        SET last_ingested = NOW()
        WHERE lat = $1 AND lon = $2
        """, lat, lon)

        await db.update_ingestion_job(job_id, "success", records=1)
        log.info(f"[ingest] ✓ {city or geohash} — AQI: {snap.atmosphere.aqi_us}, PM2.5: {snap.atmosphere.pm2_5}")
        return snap

    except Exception as e:
        log.error(f"[ingest] ✗ {city or geohash}: {e}")
        await db.update_ingestion_job(job_id, "failed", error=str(e))
        return None


async def run_worker_cycle():
    """
    One full cycle: fetch all monitored locations and ingest each.
    Locations are processed with bounded concurrency (10 at a time).
    """
    locations = await db.get_monitored_locations()
    if not locations:
        log.warning("[worker] No monitored locations found. Check monitored_locations table.")
        return

    log.info(f"[worker] Starting cycle — {len(locations)} locations")

    sem = asyncio.Semaphore(10)  # max 10 concurrent fetches

    async def _bounded(loc):
        async with sem:
            return await ingest_location(
                lat=loc["lat"],
                lon=loc["lon"],
                city=loc.get("city", ""),
                country=loc.get("country", ""),
            )

    results = await asyncio.gather(*[_bounded(loc) for loc in locations], return_exceptions=True)
    success = sum(1 for r in results if r is not None and not isinstance(r, Exception))
    log.info(f"[worker] Cycle complete — {success}/{len(locations)} succeeded")


async def run_continuous(default_interval_sec: int = 300):
    """
    Main loop. Runs forever, cycling every `default_interval_sec` seconds.
    Individual locations can have custom intervals (honoured in future versions
    by checking last_ingested + interval_sec per row).
    """
    log.info(f"[worker] Continuous ingestion started (default interval: {default_interval_sec}s)")
    while True:
        try:
            await run_worker_cycle()
        except Exception as e:
            log.error(f"[worker] Cycle error: {e}")
        await asyncio.sleep(default_interval_sec)


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    async def main():
        await db.connect()
        interval = int(os.getenv("INGEST_INTERVAL_SEC", "300"))
        await run_continuous(interval)

    asyncio.run(main())
