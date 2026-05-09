"""
AQI Adapter
Primary:   WAQI (World Air Quality Index) — https://waqi.info — needs free API key
Secondary: Open-Meteo Air Quality API — FREE, no key — PM2.5, PM10, CO, NO2, SO2, O3
Heatmap:   Open-Meteo AQ grid (0.25° resolution, global)

Set WAQI_TOKEN in .env. If absent, falls back to Open-Meteo only.
"""

import os
import asyncio
import httpx
import math
from typing import Any

WAQI_BASE = "https://api.waqi.info"
AQ_BASE   = "https://air-quality-api.open-meteo.com/v1/air-quality"

WAQI_TOKEN = os.getenv("WAQI_TOKEN", "")  # free at https://aqicn.org/data-platform/token/


def aqi_category(aqi: float | None) -> dict:
    if aqi is None:
        return {"level": "Unknown", "color": "#888888", "health": "No data"}
    if aqi <= 50:
        return {"level": "Good",            "color": "#00e400", "health": "Air quality is satisfactory."}
    if aqi <= 100:
        return {"level": "Moderate",        "color": "#ffff00", "health": "Acceptable; some pollutants may affect sensitive groups."}
    if aqi <= 150:
        return {"level": "Unhealthy (SG)",  "color": "#ff7e00", "health": "Sensitive groups may experience health effects."}
    if aqi <= 200:
        return {"level": "Unhealthy",       "color": "#ff0000", "health": "Everyone may begin to experience health effects."}
    if aqi <= 300:
        return {"level": "Very Unhealthy",  "color": "#8f3f97", "health": "Health alert: everyone may experience serious effects."}
    return {"level": "Hazardous",           "color": "#7e0023", "health": "Health warning of emergency conditions."}


class AQIAdapter:
    def __init__(self, timeout: float = 12.0):
        self._client = httpx.AsyncClient(timeout=timeout)

    # ── Current AQI ──────────────────────────────────────────────────────────

    async def get_current(self, lat: float, lon: float) -> dict[str, Any]:
        """
        Tries WAQI first (richest station data), falls back to Open-Meteo AQ model.
        Both are merged into a unified schema.
        """
        waqi_data, om_data = await asyncio.gather(
            self._waqi_current(lat, lon),
            self._om_current(lat, lon),
            return_exceptions=True,
        )

        result: dict = {
            "location": {"lat": lat, "lon": lon},
            "pollutants": {},
            "source": [],
        }

        # Open-Meteo always succeeds — use as base
        if isinstance(om_data, dict):
            result["pollutants"].update(om_data.get("pollutants", {}))
            result["aqi_eu"] = om_data.get("aqi_eu")
            result["source"].append("open-meteo-aq")
            result["timestamp"] = om_data.get("timestamp")

        # WAQI enriches with US AQI + station name
        if isinstance(waqi_data, dict) and not isinstance(waqi_data, Exception):
            result["aqi_us"] = waqi_data.get("aqi_us")
            result["station"] = waqi_data.get("station")
            result["dominant_pollutant"] = waqi_data.get("dominant_pollutant")
            result["source"].append("waqi")
            # Prefer WAQI pollutant values (station-measured > model)
            result["pollutants"].update(waqi_data.get("pollutants", {}))
        else:
            # Derive a US-style AQI from PM2.5 if WAQI unavailable
            pm25 = (result["pollutants"].get("pm2_5") or {}).get("value")
            result["aqi_us"] = _pm25_to_aqi(pm25) if pm25 else result.get("aqi_eu")

        aqi_val = result.get("aqi_us") or result.get("aqi_eu")
        result["aqi"] = aqi_val
        result["category"] = aqi_category(aqi_val)
        return result

    async def _waqi_current(self, lat: float, lon: float) -> dict | None:
        if not WAQI_TOKEN:
            return None
        url = f"{WAQI_BASE}/feed/geo:{lat};{lon}/"
        resp = await self._client.get(url, params={"token": WAQI_TOKEN})
        resp.raise_for_status()
        raw = resp.json()
        if raw.get("status") != "ok":
            return None
        d = raw["data"]
        iaqi = d.get("iaqi", {})

        def _extract(key):
            v = iaqi.get(key, {}).get("v")
            return {"value": v} if v is not None else None

        return {
            "aqi_us": d.get("aqi"),
            "station": d.get("city", {}).get("name"),
            "dominant_pollutant": d.get("dominentpol"),
            "pollutants": {
                "pm2_5":  _extract("pm25"),
                "pm10":   _extract("pm10"),
                "co":     _extract("co"),
                "no2":    _extract("no2"),
                "so2":    _extract("so2"),
                "o3":     _extract("o3"),
            },
        }

    async def _om_current(self, lat: float, lon: float) -> dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": ",".join([
                "pm2_5", "pm10", "carbon_monoxide",
                "nitrogen_dioxide", "sulphur_dioxide", "ozone",
                "european_aqi", "us_aqi",
                "dust", "uv_index",
            ]),
            "timezone": "auto",
        }
        resp = await self._client.get(AQ_BASE, params=params)
        resp.raise_for_status()
        raw = resp.json()
        cur = raw.get("current", {})

        def _p(key, unit):
            v = cur.get(key)
            return {"value": v, "unit": unit} if v is not None else None

        return {
            "timestamp": cur.get("time"),
            "aqi_eu": cur.get("european_aqi"),
            "aqi_us": cur.get("us_aqi"),
            "pollutants": {
                "pm2_5":           _p("pm2_5", "μg/m³"),
                "pm10":            _p("pm10", "μg/m³"),
                "carbon_monoxide": _p("carbon_monoxide", "μg/m³"),
                "nitrogen_dioxide":_p("nitrogen_dioxide", "μg/m³"),
                "sulphur_dioxide": _p("sulphur_dioxide", "μg/m³"),
                "ozone":           _p("ozone", "μg/m³"),
                "dust":            _p("dust", "μg/m³"),
            },
            "source": "open-meteo-aq",
        }

    # ── Forecast ─────────────────────────────────────────────────────────────

    async def get_forecast(self, lat: float, lon: float, hours: int = 72) -> dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join([
                "pm2_5", "pm10", "carbon_monoxide",
                "nitrogen_dioxide", "sulphur_dioxide", "ozone",
                "european_aqi", "us_aqi",
            ]),
            "forecast_days": min((hours // 24) + 1, 7),
            "timezone": "auto",
        }
        resp = await self._client.get(AQ_BASE, params=params)
        resp.raise_for_status()
        raw = resp.json()

        hourly = raw.get("hourly", {})
        times = (hourly.get("time") or [])[:hours]

        series = []
        for i, t in enumerate(times):
            aqi_us = _safe(hourly.get("us_aqi"), i)
            series.append({
                "time": t,
                "aqi_us": aqi_us,
                "aqi_eu": _safe(hourly.get("european_aqi"), i),
                "pm2_5":  _safe(hourly.get("pm2_5"), i),
                "pm10":   _safe(hourly.get("pm10"), i),
                "no2":    _safe(hourly.get("nitrogen_dioxide"), i),
                "o3":     _safe(hourly.get("ozone"), i),
                "category": aqi_category(aqi_us),
            })

        return {
            "location": {"lat": lat, "lon": lon},
            "series": series,
            "source": "open-meteo-aq",
        }

    # ── Nearby Stations ──────────────────────────────────────────────────────

    async def get_nearby_stations(self, lat: float, lon: float, radius: int = 25000) -> dict[str, Any]:
        if not WAQI_TOKEN:
            return {"stations": [], "note": "WAQI_TOKEN not set — set it in .env for station data"}

        # WAQI bounds search
        deg = radius / 111000  # approx deg per meter
        url = f"{WAQI_BASE}/map/bounds/"
        params = {
            "latlng": f"{lat-deg},{lon-deg},{lat+deg},{lon+deg}",
            "token": WAQI_TOKEN,
        }
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        raw = resp.json()

        if raw.get("status") != "ok":
            return {"stations": []}

        stations = []
        for s in raw.get("data", []):
            aqi_val = s.get("aqi")
            try:
                aqi_val = int(aqi_val)
            except (TypeError, ValueError):
                aqi_val = None
            stations.append({
                "uid": s.get("uid"),
                "name": s.get("station", {}).get("name"),
                "lat": s.get("lat"),
                "lon": s.get("lon"),
                "aqi": aqi_val,
                "category": aqi_category(aqi_val),
            })

        return {"stations": stations, "count": len(stations)}

    # ── Heatmap Grid ─────────────────────────────────────────────────────────

    async def get_heatmap_grid(
        self,
        center_lat: float,
        center_lon: float,
        resolution: float = 0.25,
        radius_deg: float = 2.0,
    ) -> dict[str, Any]:
        """
        Fetches AQI from Open-Meteo for a grid of lat/lon points.
        Open-Meteo is free and supports multi-point requests via comma-separated lat/lon.
        Returns list of {lat, lon, aqi, category} for frontend heatmap rendering.
        """
        # Build grid points
        points = []
        lat = center_lat - radius_deg
        while lat <= center_lat + radius_deg:
            lon = center_lon - radius_deg
            while lon <= center_lon + radius_deg:
                points.append((round(lat, 4), round(lon, 4)))
                lon += resolution
            lat += resolution

        # Open-Meteo supports batch requests with comma-separated coordinates
        lats = ",".join(str(p[0]) for p in points)
        lons = ",".join(str(p[1]) for p in points)

        params = {
            "latitude": lats,
            "longitude": lons,
            "current": "us_aqi,pm2_5",
            "timezone": "auto",
        }

        resp = await self._client.get(AQ_BASE, params=params)
        resp.raise_for_status()
        raw = resp.json()

        # Batch response is a list when multiple points requested
        if not isinstance(raw, list):
            raw = [raw]

        cells = []
        for i, item in enumerate(raw):
            cur = item.get("current", {})
            aqi_val = cur.get("us_aqi")
            pm25    = cur.get("pm2_5")
            lat_p, lon_p = points[i] if i < len(points) else (center_lat, center_lon)
            cells.append({
                "lat": lat_p,
                "lon": lon_p,
                "aqi": aqi_val,
                "pm2_5": pm25,
                "category": aqi_category(aqi_val),
            })

        return {
            "center": {"lat": center_lat, "lon": center_lon},
            "resolution_deg": resolution,
            "radius_deg": radius_deg,
            "cells": cells,
            "count": len(cells),
            "source": "open-meteo-aq",
        }

    async def close(self):
        await self._client.aclose()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe(lst, i):
    if lst is None or i >= len(lst):
        return None
    return lst[i]


def _pm25_to_aqi(pm25: float) -> int:
    """
    EPA breakpoints for PM2.5 → US AQI.
    https://www.airnow.gov/sites/default/files/2020-05/aqi-technical-assistance-document-sept2018.pdf
    """
    breakpoints = [
        (0.0,   12.0,   0,   50),
        (12.1,  35.4,   51,  100),
        (35.5,  55.4,   101, 150),
        (55.5,  150.4,  151, 200),
        (150.5, 250.4,  201, 300),
        (250.5, 350.4,  301, 400),
        (350.5, 500.4,  401, 500),
    ]
    for c_lo, c_hi, i_lo, i_hi in breakpoints:
        if c_lo <= pm25 <= c_hi:
            return round(((i_hi - i_lo) / (c_hi - c_lo)) * (pm25 - c_lo) + i_lo)
    return 500
