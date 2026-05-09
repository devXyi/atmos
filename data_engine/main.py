"""
Prexus Atmos — Data Engine
Real data from: Open-Meteo (weather + AQ), WAQI/AQICN, OpenAQ, NASA FIRMS
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging

from adapters.open_meteo import OpenMeteoAdapter
from adapters.aqi import AQIAdapter
from adapters.satellite import SatelliteAdapter
from analytics import HealthRiskAnalyzer, AQITrendAnalyzer, AlertEngine
from cache import Cache

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("atmos.engine")

cache = Cache()
weather_adapter = OpenMeteoAdapter()
aqi_adapter = AQIAdapter()
satellite_adapter = SatelliteAdapter()
health_analyzer = HealthRiskAnalyzer()
trend_analyzer = AQITrendAnalyzer()
alert_engine = AlertEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Prexus Atmos Data Engine starting...")
    await cache.connect()
    yield
    await cache.close()
    log.info("Data Engine shut down.")


app = FastAPI(
    title="Prexus Atmos Data Engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ─── Weather ──────────────────────────────────────────────────────────────────

@app.get("/weather/current")
async def weather_current(
    lat: float = Query(28.6139, ge=-90, le=90),
    lon: float = Query(77.2090, ge=-180, le=180),
):
    key = f"weather:current:{lat:.3f}:{lon:.3f}"
    if cached := await cache.get(key):
        return cached
    data = await weather_adapter.get_current(lat, lon)
    await cache.set(key, data, ttl=300)  # 5 min
    return data


@app.get("/weather/forecast")
async def weather_forecast(
    lat: float = Query(28.6139),
    lon: float = Query(77.2090),
    days: int = Query(7, ge=1, le=16),
):
    key = f"weather:forecast:{lat:.3f}:{lon:.3f}:{days}"
    if cached := await cache.get(key):
        return cached
    data = await weather_adapter.get_forecast(lat, lon, days)
    await cache.set(key, data, ttl=1800)  # 30 min
    return data


@app.get("/weather/hourly")
async def weather_hourly(
    lat: float = Query(28.6139),
    lon: float = Query(77.2090),
    hours: int = Query(48, ge=1, le=168),
):
    key = f"weather:hourly:{lat:.3f}:{lon:.3f}:{hours}"
    if cached := await cache.get(key):
        return cached
    data = await weather_adapter.get_hourly(lat, lon, hours)
    await cache.set(key, data, ttl=900)
    return data


# ─── AQI ──────────────────────────────────────────────────────────────────────

@app.get("/aqi/current")
async def aqi_current(
    lat: float = Query(28.6139),
    lon: float = Query(77.2090),
):
    key = f"aqi:current:{lat:.3f}:{lon:.3f}"
    if cached := await cache.get(key):
        return cached
    data = await aqi_adapter.get_current(lat, lon)
    await cache.set(key, data, ttl=600)  # 10 min
    return data


@app.get("/aqi/forecast")
async def aqi_forecast(
    lat: float = Query(28.6139),
    lon: float = Query(77.2090),
    hours: int = Query(72, ge=1, le=120),
):
    key = f"aqi:forecast:{lat:.3f}:{lon:.3f}:{hours}"
    if cached := await cache.get(key):
        return cached
    data = await aqi_adapter.get_forecast(lat, lon, hours)
    await cache.set(key, data, ttl=3600)
    return data


@app.get("/aqi/stations")
async def aqi_stations(
    lat: float = Query(28.6139),
    lon: float = Query(77.2090),
    radius: int = Query(25000, ge=1000, le=100000),
):
    data = await aqi_adapter.get_nearby_stations(lat, lon, radius)
    return data


@app.get("/aqi/heatmap")
async def aqi_heatmap(
    lat: float = Query(28.6139),
    lon: float = Query(77.2090),
    resolution: float = Query(0.25, ge=0.1, le=1.0),
    radius_deg: float = Query(2.0, ge=0.5, le=10.0),
):
    """
    Returns a grid of AQI forecast values for heatmap rendering.
    Uses Open-Meteo air quality model — covers every 0.25° grid cell globally.
    """
    key = f"aqi:heatmap:{lat:.2f}:{lon:.2f}:{resolution}:{radius_deg}"
    if cached := await cache.get(key):
        return cached
    data = await aqi_adapter.get_heatmap_grid(lat, lon, resolution, radius_deg)
    await cache.set(key, data, ttl=3600)
    return data


# ─── Satellite ────────────────────────────────────────────────────────────────

@app.get("/satellite/fires")
async def satellite_fires(
    lat: float = Query(28.6139),
    lon: float = Query(77.2090),
    radius: int = Query(500, ge=50, le=2000),  # km
):
    key = f"satellite:fires:{lat:.2f}:{lon:.2f}:{radius}"
    if cached := await cache.get(key):
        return cached
    data = await satellite_adapter.get_active_fires(lat, lon, radius)
    await cache.set(key, data, ttl=1800)
    return data


@app.get("/satellite/smoke")
async def satellite_smoke(
    lat: float = Query(28.6139),
    lon: float = Query(77.2090),
):
    data = await satellite_adapter.get_smoke_data(lat, lon)
    return data


# ─── Alerts ───────────────────────────────────────────────────────────────────

@app.get("/alerts/active")
async def alerts_active(
    lat: float = Query(28.6139),
    lon: float = Query(77.2090),
):
    """Derives alerts from current AQI + weather data — no third-party alert API needed."""
    weather_task = aio_task(weather_adapter.get_current(lat, lon))
    aqi_task = aio_task(aqi_adapter.get_current(lat, lon))
    weather, aqi = await asyncio.gather(weather_task, aqi_task)
    alerts = alert_engine.evaluate(weather, aqi)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/alerts/history")
async def alerts_history(
    lat: float = Query(28.6139),
    lon: float = Query(77.2090),
    days: int = Query(7, ge=1, le=30),
):
    # Historical AQI trend used to reconstruct past alert events
    trend = await trend_analyzer.get_hourly_trend(lat, lon, hours=days * 24)
    past_alerts = alert_engine.reconstruct_from_trend(trend)
    return {"alerts": past_alerts, "days": days}


# ─── Analytics ────────────────────────────────────────────────────────────────

@app.get("/analytics/aqi-trend")
async def analytics_aqi_trend(
    lat: float = Query(28.6139),
    lon: float = Query(77.2090),
    hours: int = Query(168, ge=24, le=720),
):
    key = f"analytics:trend:{lat:.2f}:{lon:.2f}:{hours}"
    if cached := await cache.get(key):
        return cached
    data = await trend_analyzer.get_hourly_trend(lat, lon, hours)
    await cache.set(key, data, ttl=3600)
    return data


@app.get("/analytics/health-risk")
async def analytics_health_risk(
    lat: float = Query(28.6139),
    lon: float = Query(77.2090),
):
    aqi = await aqi_adapter.get_current(lat, lon)
    return health_analyzer.compute(aqi)


@app.get("/analytics/pollution-sources")
async def analytics_pollution_sources(
    lat: float = Query(28.6139),
    lon: float = Query(77.2090),
):
    """Cross-references wind direction + pollutant ratios to estimate sources."""
    weather = await weather_adapter.get_current(lat, lon)
    aqi = await aqi_adapter.get_current(lat, lon)
    return health_analyzer.estimate_sources(weather, aqi)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def aio_task(coro):
    return asyncio.ensure_future(coro)
