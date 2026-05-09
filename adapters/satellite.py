"""
Satellite Adapter
Active Fires: NASA FIRMS (Fire Information for Resource Management System)
              https://firms.modaps.eosdis.nasa.gov/api/
              Free API key at https://firms.modaps.eosdis.nasa.gov/api/area/

Smoke/Aerosol: Open-Meteo Air Quality — dust + aerosol optical depth (free, no key)

Set NASA_FIRMS_KEY in .env.
"""

import os
import csv
import io
import httpx
import math
from typing import Any
from datetime import datetime, timezone

FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
AQ_BASE    = "https://air-quality-api.open-meteo.com/v1/air-quality"

FIRMS_KEY  = os.getenv("NASA_FIRMS_KEY", "")


class SatelliteAdapter:
    def __init__(self, timeout: float = 20.0):
        self._client = httpx.AsyncClient(timeout=timeout)

    # ── Active Fires (NASA FIRMS) ─────────────────────────────────────────────

    async def get_active_fires(
        self,
        lat: float,
        lon: float,
        radius_km: int = 500,
    ) -> dict[str, Any]:
        """
        Returns active fire detections from VIIRS S-NPP in the last 24h
        within radius_km of the given coordinate.

        FIRMS CSV API: /api/area/csv/{key}/{source}/{area}/{days}
        area = W,S,E,N bounding box
        """
        if not FIRMS_KEY:
            return {
                "fires": [],
                "count": 0,
                "note": "NASA_FIRMS_KEY not set. Get a free key at https://firms.modaps.eosdis.nasa.gov/api/",
                "source": "nasa-firms",
            }

        deg = _km_to_deg(radius_km, lat)
        bbox = f"{lon-deg},{lat-deg},{lon+deg},{lat+deg}"  # W,S,E,N
        url  = f"{FIRMS_BASE}/{FIRMS_KEY}/VIIRS_SNPP_NRT/{bbox}/1"

        resp = await self._client.get(url)
        resp.raise_for_status()

        fires = _parse_firms_csv(resp.text)

        return {
            "fires": fires,
            "count": len(fires),
            "query": {"lat": lat, "lon": lon, "radius_km": radius_km},
            "source": "nasa-firms/viirs-snpp",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── Smoke / Aerosol ───────────────────────────────────────────────────────

    async def get_smoke_data(self, lat: float, lon: float) -> dict[str, Any]:
        """
        Aerosol optical depth + dust from Open-Meteo — free, global, hourly.
        High AOD values indicate smoke/haze/dust in the atmosphere.
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join([
                "dust",
                "aerosol_optical_depth",
                "pm2_5",
                "pm10",
            ]),
            "forecast_days": 3,
            "timezone": "auto",
        }
        resp = await self._client.get(AQ_BASE, params=params)
        resp.raise_for_status()
        raw = resp.json()

        hourly = raw.get("hourly", {})
        times  = hourly.get("time", [])

        # Current hour index
        series = []
        for i, t in enumerate(times[:72]):  # 3 days max
            aod  = _safe(hourly.get("aerosol_optical_depth"), i)
            dust = _safe(hourly.get("dust"), i)
            pm25 = _safe(hourly.get("pm2_5"), i)
            series.append({
                "time":                  t,
                "aerosol_optical_depth": aod,
                "dust_ug_m3":           dust,
                "pm2_5_ug_m3":          pm25,
                "smoke_level":          _aod_to_level(aod),
            })

        current = series[0] if series else {}
        return {
            "location": {"lat": lat, "lon": lon},
            "current":  current,
            "forecast": series,
            "source":   "open-meteo-aq",
        }

    async def close(self):
        await self._client.aclose()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe(lst, i):
    if lst is None or i >= len(lst):
        return None
    return lst[i]


def _km_to_deg(km: float, lat: float) -> float:
    """Approximate degrees per km at given latitude."""
    lat_deg = km / 111.0
    lon_deg = km / (111.0 * math.cos(math.radians(lat)))
    return max(lat_deg, lon_deg)


def _aod_to_level(aod: float | None) -> str:
    if aod is None:
        return "unknown"
    if aod < 0.1:   return "clear"
    if aod < 0.3:   return "hazy"
    if aod < 0.6:   return "smoky"
    if aod < 1.0:   return "heavy_smoke"
    return "extreme"


def _parse_firms_csv(text: str) -> list[dict]:
    """
    FIRMS CSV columns (VIIRS):
    latitude, longitude, bright_ti4, scan, track, acq_date, acq_time,
    satellite, instrument, confidence, version, bright_ti5, frp, daynight
    """
    fires = []
    try:
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            try:
                fires.append({
                    "lat":        float(row["latitude"]),
                    "lon":        float(row["longitude"]),
                    "brightness": float(row.get("bright_ti4", 0) or 0),
                    "frp":        float(row.get("frp", 0) or 0),          # Fire Radiative Power (MW)
                    "confidence": row.get("confidence", "n").strip().lower(),
                    "date":       row.get("acq_date", ""),
                    "time_utc":   row.get("acq_time", ""),
                    "satellite":  row.get("satellite", ""),
                    "day_night":  row.get("daynight", ""),
                })
            except (ValueError, KeyError):
                continue
    except Exception:
        pass
    return fires
