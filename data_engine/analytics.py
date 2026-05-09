"""
Analytics Module
- HealthRiskAnalyzer:  AQI → health risk by demographic, pollution source estimation
- AQITrendAnalyzer:    Historical AQI trend from Open-Meteo air quality model
- AlertEngine:         Rule-based alert derivation from live weather + AQI data
"""

import httpx
from datetime import datetime, timezone, timedelta
from typing import Any


AQ_BASE      = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_BASE = "https://api.open-meteo.com/v1/forecast"


# ─── Health Risk Analyzer ─────────────────────────────────────────────────────

class HealthRiskAnalyzer:

    # WHO-aligned risk multipliers by group
    SENSITIVE_GROUPS = {
        "general_population":    {"multiplier": 1.0,  "label": "General Population"},
        "children":              {"multiplier": 1.6,  "label": "Children (under 12)"},
        "elderly":               {"multiplier": 1.5,  "label": "Elderly (65+)"},
        "cardiovascular":        {"multiplier": 1.8,  "label": "Cardiovascular Conditions"},
        "respiratory":           {"multiplier": 2.0,  "label": "Respiratory Conditions (asthma, COPD)"},
        "outdoor_workers":       {"multiplier": 1.4,  "label": "Outdoor Workers"},
    }

    def compute(self, aqi_data: dict) -> dict[str, Any]:
        aqi = aqi_data.get("aqi") or 0
        pollutants = aqi_data.get("pollutants", {})

        risks = {}
        for key, meta in self.SENSITIVE_GROUPS.items():
            adjusted = min(aqi * meta["multiplier"], 500)
            risks[key] = {
                "group":        meta["label"],
                "adjusted_aqi": round(adjusted),
                "risk_level":   _aqi_to_risk(adjusted),
                "guidance":     _risk_guidance(adjusted, key),
            }

        pm25  = (pollutants.get("pm2_5")           or {}).get("value")
        pm10  = (pollutants.get("pm10")            or {}).get("value")
        no2   = (pollutants.get("nitrogen_dioxide") or {}).get("value")
        o3    = (pollutants.get("ozone")           or {}).get("value")

        exceedances = []
        if pm25  and pm25 > 35.4:   exceedances.append(f"PM2.5 ({pm25:.1f} μg/m³) exceeds WHO 24h guideline (15 μg/m³)")
        if pm10  and pm10 > 154:    exceedances.append(f"PM10 ({pm10:.1f} μg/m³) exceeds safe threshold")
        if no2   and no2 > 200:     exceedances.append(f"NO2 ({no2:.1f} μg/m³) above WHO hourly limit")
        if o3    and o3 > 180:      exceedances.append(f"Ozone ({o3:.1f} μg/m³) at hazardous level")

        return {
            "aqi":            aqi,
            "category":       aqi_data.get("category", {}),
            "risks":          risks,
            "exceedances":    exceedances,
            "recommendations": _overall_recommendations(aqi),
            "source":         "prexus-atmos-analytics",
        }

    def estimate_sources(self, weather: dict, aqi_data: dict) -> dict[str, Any]:
        """
        Heuristic pollution source estimation based on:
        - Wind direction (where pollution is coming from)
        - NO2/CO ratio (traffic signature)
        - SO2 presence (industrial/coal)
        - PM ratio (PM2.5/PM10: fine = combustion, coarse = dust)
        """
        wind_dir  = (weather.get("wind") or {}).get("direction_deg", 0) or 0
        wind_spd  = (weather.get("wind") or {}).get("speed_kmh", 0) or 0
        pollutants = aqi_data.get("pollutants", {})

        no2  = (pollutants.get("nitrogen_dioxide") or {}).get("value", 0) or 0
        co   = (pollutants.get("carbon_monoxide")  or {}).get("value", 0) or 0
        so2  = (pollutants.get("sulphur_dioxide")  or {}).get("value", 0) or 0
        pm25 = (pollutants.get("pm2_5")           or {}).get("value", 0) or 0
        pm10 = (pollutants.get("pm10")            or {}).get("value", 0) or 0
        dust = (pollutants.get("dust")            or {}).get("value", 0) or 0

        sources = []

        # Traffic / vehicular
        if no2 > 40 or co > 1000:
            confidence = min(int(((no2 / 80) * 60) + ((co / 2000) * 40)), 95)
            sources.append({
                "type":       "vehicular_traffic",
                "label":      "Vehicular Traffic",
                "confidence": confidence,
                "indicators": [f"NO2: {no2:.0f} μg/m³", f"CO: {co:.0f} μg/m³"],
            })

        # Industrial / coal
        if so2 > 20:
            confidence = min(int((so2 / 100) * 90), 90)
            sources.append({
                "type":       "industrial_coal",
                "label":      "Industrial / Coal Combustion",
                "confidence": confidence,
                "indicators": [f"SO2: {so2:.0f} μg/m³"],
            })

        # Dust / construction
        pm_ratio = (pm25 / pm10) if pm10 > 0 else 0
        if dust > 50 or (pm10 > 100 and pm_ratio < 0.5):
            confidence = min(int((dust / 200) * 80 + (1 - pm_ratio) * 20), 85)
            sources.append({
                "type":       "dust_construction",
                "label":      "Dust / Construction / Road Resuspension",
                "confidence": confidence,
                "indicators": [f"Dust: {dust:.0f} μg/m³", f"PM ratio: {pm_ratio:.2f}"],
            })

        # Biomass burning (high PM2.5, PM2.5/PM10 > 0.7)
        if pm25 > 55 and pm_ratio > 0.65:
            sources.append({
                "type":       "biomass_burning",
                "label":      "Biomass / Agricultural Burning",
                "confidence": min(int(pm_ratio * 90), 88),
                "indicators": [f"PM2.5: {pm25:.0f} μg/m³", f"PM ratio: {pm_ratio:.2f}"],
            })

        # Wind transport direction
        transport_from = _cardinal(wind_dir)
        if wind_spd > 10:
            sources.append({
                "type":       "long_range_transport",
                "label":      f"Long-range Transport from {transport_from}",
                "confidence": min(int(wind_spd * 2), 75),
                "indicators": [f"Wind: {wind_spd:.0f} km/h from {transport_from}"],
            })

        sources.sort(key=lambda x: x["confidence"], reverse=True)
        return {
            "sources":         sources,
            "wind_direction":  transport_from,
            "wind_speed_kmh":  wind_spd,
            "source":          "prexus-atmos-analytics",
        }


# ─── AQI Trend Analyzer ───────────────────────────────────────────────────────

class AQITrendAnalyzer:
    def __init__(self, timeout: float = 15.0):
        self._client = httpx.AsyncClient(timeout=timeout)

    async def get_hourly_trend(self, lat: float, lon: float, hours: int = 168) -> dict[str, Any]:
        """
        Open-Meteo AQ historical/forecast model.
        Provides up to 92 days past + 7 days forecast.
        """
        past_days = min(hours // 24, 92)
        params = {
            "latitude":   lat,
            "longitude":  lon,
            "hourly":     "us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone",
            "past_days":  past_days,
            "forecast_days": 1,
            "timezone":   "auto",
        }
        resp = await self._client.get(AQ_BASE, params=params)
        resp.raise_for_status()
        raw = resp.json()

        hourly = raw.get("hourly", {})
        times  = (hourly.get("time") or [])

        # Slice to requested hours from now (past only)
        series = []
        for i, t in enumerate(times):
            aqi = _safe(hourly.get("us_aqi"), i)
            series.append({
                "time":  t,
                "aqi":   aqi,
                "pm2_5": _safe(hourly.get("pm2_5"), i),
                "pm10":  _safe(hourly.get("pm10"), i),
                "no2":   _safe(hourly.get("nitrogen_dioxide"), i),
                "o3":    _safe(hourly.get("ozone"), i),
                "category": _aqi_to_risk(aqi or 0),
            })

        series = series[-hours:] if len(series) > hours else series

        # Compute stats
        aqi_values = [s["aqi"] for s in series if s["aqi"] is not None]
        stats = {}
        if aqi_values:
            stats = {
                "mean":    round(sum(aqi_values) / len(aqi_values), 1),
                "max":     max(aqi_values),
                "min":     min(aqi_values),
                "latest":  aqi_values[-1] if aqi_values else None,
            }

        return {
            "location": {"lat": lat, "lon": lon},
            "hours":    hours,
            "series":   series,
            "stats":    stats,
            "source":   "open-meteo-aq",
        }

    async def close(self):
        await self._client.aclose()


# ─── Alert Engine ─────────────────────────────────────────────────────────────

class AlertEngine:

    def evaluate(self, weather: dict | None, aqi_data: dict | None) -> list[dict]:
        alerts = []
        now = datetime.now(timezone.utc).isoformat()

        if aqi_data:
            aqi = aqi_data.get("aqi") or 0

            if aqi > 300:
                alerts.append(_alert("HAZARDOUS_AQI", "critical", "Hazardous Air Quality",
                    f"AQI is {aqi}. Avoid all outdoor activity. Health emergency conditions.",
                    {"aqi": aqi}, now))
            elif aqi > 200:
                alerts.append(_alert("VERY_UNHEALTHY_AQI", "high", "Very Unhealthy Air Quality",
                    f"AQI is {aqi}. Everyone should avoid prolonged outdoor exposure.",
                    {"aqi": aqi}, now))
            elif aqi > 150:
                alerts.append(_alert("UNHEALTHY_AQI", "medium", "Unhealthy Air Quality",
                    f"AQI is {aqi}. Sensitive groups should limit outdoor activity.",
                    {"aqi": aqi}, now))

            # PM2.5 check
            pm25 = (aqi_data.get("pollutants", {}).get("pm2_5") or {}).get("value")
            if pm25 and pm25 > 150:
                alerts.append(_alert("HIGH_PM25", "high", "Extreme PM2.5 Pollution",
                    f"PM2.5 at {pm25:.0f} μg/m³ — 10× WHO daily guideline. Use N95 masks indoors.",
                    {"pm2_5": pm25}, now))

            so2 = (aqi_data.get("pollutants", {}).get("sulphur_dioxide") or {}).get("value")
            if so2 and so2 > 100:
                alerts.append(_alert("HIGH_SO2", "medium", "Elevated SO2 — Industrial Pollution",
                    f"SO2 at {so2:.0f} μg/m³. May cause respiratory irritation.",
                    {"so2": so2}, now))

        if weather:
            wind_spd  = (weather.get("wind") or {}).get("speed_kmh", 0) or 0
            wind_gust = (weather.get("wind") or {}).get("gusts_kmh", 0) or 0
            precip    = weather.get("precipitation_mm", 0) or 0
            uv        = weather.get("uv_index", 0) or 0
            vis       = weather.get("visibility_m", 10000) or 10000
            code      = (weather.get("condition") or {}).get("code", 0) or 0

            if wind_gust > 90:
                alerts.append(_alert("SEVERE_WIND", "critical", "Severe Wind Gusts",
                    f"Gusts up to {wind_gust:.0f} km/h. Risk of structural damage.",
                    {"gusts_kmh": wind_gust}, now))
            elif wind_gust > 60:
                alerts.append(_alert("STRONG_WIND", "medium", "Strong Wind Advisory",
                    f"Wind gusts at {wind_gust:.0f} km/h.",
                    {"gusts_kmh": wind_gust}, now))

            if code in (95, 96, 99):
                alerts.append(_alert("THUNDERSTORM", "high", "Thunderstorm Active",
                    "Severe thunderstorm in your area. Stay indoors.",
                    {"weather_code": code}, now))

            if precip > 50:
                alerts.append(_alert("HEAVY_RAIN", "high", "Heavy Rainfall Warning",
                    f"{precip:.0f} mm of precipitation. Flooding risk.",
                    {"precip_mm": precip}, now))

            if uv >= 11:
                alerts.append(_alert("EXTREME_UV", "high", "Extreme UV Index",
                    f"UV Index: {uv}. Avoid sun exposure 10am–4pm.",
                    {"uv_index": uv}, now))
            elif uv >= 8:
                alerts.append(_alert("HIGH_UV", "medium", "High UV Index",
                    f"UV Index: {uv}. Apply SPF 30+.",
                    {"uv_index": uv}, now))

            if vis < 500:
                alerts.append(_alert("LOW_VISIBILITY", "high", "Very Low Visibility",
                    f"Visibility down to {vis}m. Dangerous driving conditions.",
                    {"visibility_m": vis}, now))

        return alerts

    def reconstruct_from_trend(self, trend: dict) -> list[dict]:
        """Replay alert logic over historical AQI series."""
        series  = trend.get("series", [])
        alerts  = []
        for point in series:
            aqi = point.get("aqi")
            if aqi is None:
                continue
            if aqi > 200:
                alerts.append({
                    "type":      "VERY_UNHEALTHY_AQI",
                    "severity":  "high",
                    "time":      point.get("time"),
                    "aqi":       aqi,
                })
            elif aqi > 150:
                alerts.append({
                    "type":     "UNHEALTHY_AQI",
                    "severity": "medium",
                    "time":     point.get("time"),
                    "aqi":      aqi,
                })
        return alerts


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe(lst, i):
    if lst is None or i >= len(lst):
        return None
    return lst[i]


def _alert(type_, severity, title, message, data, timestamp):
    return {
        "type":      type_,
        "severity":  severity,
        "title":     title,
        "message":   message,
        "data":      data,
        "timestamp": timestamp,
    }


def _aqi_to_risk(aqi: float) -> str:
    if aqi <= 50:   return "good"
    if aqi <= 100:  return "moderate"
    if aqi <= 150:  return "unhealthy_sg"
    if aqi <= 200:  return "unhealthy"
    if aqi <= 300:  return "very_unhealthy"
    return "hazardous"


def _cardinal(deg: float) -> str:
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[round(deg / 22.5) % 16]


def _risk_guidance(adjusted_aqi: float, group: str) -> str:
    if adjusted_aqi <= 50:
        return "No restrictions. Enjoy outdoor activities."
    if adjusted_aqi <= 100:
        if group in ("respiratory", "cardiovascular"):
            return "Consider reducing prolonged exertion outdoors."
        return "Air quality acceptable. Sensitive individuals may notice mild effects."
    if adjusted_aqi <= 150:
        return "Limit prolonged outdoor exertion. Wear a mask if outdoors for extended periods."
    if adjusted_aqi <= 200:
        return "Avoid outdoor activity. Stay indoors with windows closed."
    if adjusted_aqi <= 300:
        return "Health emergency conditions. Do not go outdoors. Use air purifier indoors."
    return "Extreme health hazard. Evacuate or shelter-in-place with sealed windows."


def _overall_recommendations(aqi: float) -> list[str]:
    if aqi <= 50:
        return ["Safe for outdoor activities", "Good day for exercise"]
    if aqi <= 100:
        return [
            "Unusually sensitive people should consider reducing outdoor activity",
            "Good day for most people",
        ]
    if aqi <= 150:
        return [
            "Reduce prolonged outdoor exertion",
            "People with asthma should carry inhalers",
            "Consider wearing a mask outdoors",
        ]
    if aqi <= 200:
        return [
            "Everyone should avoid prolonged outdoor exposure",
            "Close windows and use air purifier",
            "Vulnerable groups: stay indoors",
        ]
    if aqi <= 300:
        return [
            "Avoid all outdoor activity",
            "Wear N95 mask if you must go out",
            "Use air purifier indoors",
            "Check on elderly and children",
        ]
    return [
        "Health emergency — avoid going outdoors",
        "Seal windows and doors",
        "Evacuate if possible",
        "Seek medical attention if experiencing breathing difficulty",
    ]
