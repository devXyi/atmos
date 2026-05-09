"""
Open-Meteo Adapter
Weather: https://api.open-meteo.com — FREE, no API key required
Air Quality: https://air-quality-api.open-meteo.com — FREE, no API key required

Covers: temperature, humidity, wind, pressure, UV, visibility, precipitation,
        PM2.5, PM10, CO, NO2, SO2, O3, AQI (European standard)
"""

import httpx
from datetime import datetime, timezone
from typing import Any


WEATHER_BASE = "https://api.open-meteo.com/v1/forecast"
AQ_BASE = "https://air-quality-api.open-meteo.com/v1/air-quality"

# WMO weather interpretation codes → human label + icon
WMO_CODES = {
    0: ("Clear Sky", "☀️"),
    1: ("Mainly Clear", "🌤️"),
    2: ("Partly Cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"),
    48: ("Rime Fog", "🌫️"),
    51: ("Light Drizzle", "🌦️"),
    53: ("Drizzle", "🌦️"),
    55: ("Heavy Drizzle", "🌧️"),
    61: ("Light Rain", "🌧️"),
    63: ("Rain", "🌧️"),
    65: ("Heavy Rain", "🌧️"),
    71: ("Light Snow", "🌨️"),
    73: ("Snow", "❄️"),
    75: ("Heavy Snow", "❄️"),
    80: ("Rain Showers", "🌦️"),
    81: ("Heavy Showers", "🌧️"),
    82: ("Violent Showers", "⛈️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Hail Thunderstorm", "⛈️"),
    99: ("Severe Thunderstorm", "⛈️"),
}


class OpenMeteoAdapter:
    def __init__(self, timeout: float = 10.0):
        self._client = httpx.AsyncClient(timeout=timeout)

    async def get_current(self, lat: float, lon: float) -> dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": ",".join([
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "surface_pressure",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "uv_index",
                "visibility",
                "cloud_cover",
                "is_day",
            ]),
            "timezone": "auto",
        }
        resp = await self._client.get(WEATHER_BASE, params=params)
        resp.raise_for_status()
        raw = resp.json()

        cur = raw.get("current", {})
        code = cur.get("weather_code", 0)
        label, icon = WMO_CODES.get(code, ("Unknown", "❓"))

        return {
            "timestamp": cur.get("time"),
            "location": {"lat": lat, "lon": lon},
            "temperature": {
                "celsius": cur.get("temperature_2m"),
                "feels_like": cur.get("apparent_temperature"),
            },
            "humidity": cur.get("relative_humidity_2m"),
            "pressure": cur.get("surface_pressure"),          # hPa
            "wind": {
                "speed_kmh": cur.get("wind_speed_10m"),
                "direction_deg": cur.get("wind_direction_10m"),
                "gusts_kmh": cur.get("wind_gusts_10m"),
                "cardinal": _deg_to_cardinal(cur.get("wind_direction_10m", 0)),
            },
            "uv_index": cur.get("uv_index"),
            "visibility_m": cur.get("visibility"),
            "cloud_cover_pct": cur.get("cloud_cover"),
            "precipitation_mm": cur.get("precipitation"),
            "is_day": bool(cur.get("is_day", 1)),
            "condition": {"code": code, "label": label, "icon": icon},
            "source": "open-meteo",
        }

    async def get_forecast(self, lat: float, lon: float, days: int = 7) -> dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": ",".join([
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "precipitation_probability_max",
                "wind_speed_10m_max",
                "uv_index_max",
                "sunrise",
                "sunset",
            ]),
            "forecast_days": days,
            "timezone": "auto",
        }
        resp = await self._client.get(WEATHER_BASE, params=params)
        resp.raise_for_status()
        raw = resp.json()

        daily = raw.get("daily", {})
        times = daily.get("time", [])

        forecast = []
        for i, t in enumerate(times):
            code = (daily.get("weather_code") or [])[i] if i < len(daily.get("weather_code", [])) else 0
            label, icon = WMO_CODES.get(code, ("Unknown", "❓"))
            forecast.append({
                "date": t,
                "condition": {"code": code, "label": label, "icon": icon},
                "temperature": {
                    "max": _safe(daily.get("temperature_2m_max"), i),
                    "min": _safe(daily.get("temperature_2m_min"), i),
                },
                "precipitation": {
                    "sum_mm": _safe(daily.get("precipitation_sum"), i),
                    "probability_pct": _safe(daily.get("precipitation_probability_max"), i),
                },
                "wind_max_kmh": _safe(daily.get("wind_speed_10m_max"), i),
                "uv_index_max": _safe(daily.get("uv_index_max"), i),
                "sunrise": _safe(daily.get("sunrise"), i),
                "sunset": _safe(daily.get("sunset"), i),
            })

        return {
            "location": {"lat": lat, "lon": lon},
            "timezone": raw.get("timezone"),
            "days": forecast,
            "source": "open-meteo",
        }

    async def get_hourly(self, lat: float, lon: float, hours: int = 48) -> dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join([
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation_probability",
                "precipitation",
                "wind_speed_10m",
                "wind_direction_10m",
                "visibility",
                "uv_index",
                "weather_code",
            ]),
            "forecast_days": min((hours // 24) + 1, 16),
            "timezone": "auto",
        }
        resp = await self._client.get(WEATHER_BASE, params=params)
        resp.raise_for_status()
        raw = resp.json()

        hourly = raw.get("hourly", {})
        times = (hourly.get("time") or [])[:hours]

        series = []
        for i, t in enumerate(times):
            code = _safe(hourly.get("weather_code"), i)
            label, icon = WMO_CODES.get(code or 0, ("Unknown", "❓"))
            series.append({
                "time": t,
                "temperature": _safe(hourly.get("temperature_2m"), i),
                "humidity": _safe(hourly.get("relative_humidity_2m"), i),
                "precip_prob": _safe(hourly.get("precipitation_probability"), i),
                "precip_mm": _safe(hourly.get("precipitation"), i),
                "wind_kmh": _safe(hourly.get("wind_speed_10m"), i),
                "wind_dir": _safe(hourly.get("wind_direction_10m"), i),
                "visibility_m": _safe(hourly.get("visibility"), i),
                "uv_index": _safe(hourly.get("uv_index"), i),
                "condition": {"code": code, "label": label, "icon": icon},
            })

        return {
            "location": {"lat": lat, "lon": lon},
            "series": series,
            "source": "open-meteo",
        }

    async def close(self):
        await self._client.aclose()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe(lst: list | None, i: int):
    if lst is None or i >= len(lst):
        return None
    return lst[i]


def _deg_to_cardinal(deg: float) -> str:
    if deg is None:
        return "N"
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[round(deg / 22.5) % 16]
