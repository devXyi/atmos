# Prexus Atmos — Planetary Intelligence Platform

Real-time AQI, weather, fire detection, and atmospheric analytics.

## Architecture

```
Frontend (HTML/CesiumJS)
        ↓
Go API Gateway  :8080
        ↓
Python Data Engine  :8000
        ├── Open-Meteo (weather + AQ)   — FREE, no key
        ├── WAQI / AQICN               — FREE key required
        └── NASA FIRMS                 — FREE key required
```

---

## Real Data Sources

| Source | Data | Key needed |
|--------|------|-----------|
| [Open-Meteo](https://open-meteo.com) | Weather, PM2.5, PM10, NO2, O3, SO2, CO, AQI | ❌ None |
| [WAQI](https://aqicn.org/data-platform/token/) | Station AQI, dominant pollutant | ✅ Free |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/) | Active fire detections (VIIRS) | ✅ Free |
| [Nominatim](https://nominatim.openstreetmap.org) | Geocoding / reverse geocoding | ❌ None |

---

## Quickstart

### 1. Get free API keys

- **WAQI**: https://aqicn.org/data-platform/token/
- **NASA FIRMS**: https://firms.modaps.eosdis.nasa.gov/api/

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set WAQI_TOKEN and NASA_FIRMS_KEY
```

### 3. Run with Docker Compose

```bash
docker compose up --build
```

Frontend: http://localhost:3000  
Gateway:  http://localhost:8080/health  
Engine:   http://localhost:8000/docs

---

## Run without Docker

### Python Data Engine

```bash
cd data_engine
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Go API Gateway

```bash
cd backend
go mod tidy
go run .
```

### Frontend

Open `frontend/index.html` in a browser or serve it:

```bash
cd frontend
python -m http.server 3000
```

---

## API Reference

```
GET /api/v1/weather/current?lat=&lon=
GET /api/v1/weather/forecast?lat=&lon=&days=7
GET /api/v1/weather/hourly?lat=&lon=&hours=48
GET /api/v1/aqi/current?lat=&lon=
GET /api/v1/aqi/forecast?lat=&lon=&hours=72
GET /api/v1/aqi/stations?lat=&lon=&radius=25000
GET /api/v1/aqi/heatmap?lat=&lon=&resolution=0.25&radius_deg=2
GET /api/v1/satellite/fires?lat=&lon=&radius=500
GET /api/v1/satellite/smoke?lat=&lon=
GET /api/v1/alerts/active?lat=&lon=
GET /api/v1/alerts/history?lat=&lon=&days=7
GET /api/v1/analytics/aqi-trend?lat=&lon=&hours=168
GET /api/v1/analytics/health-risk?lat=&lon=
GET /api/v1/analytics/pollution-sources?lat=&lon=
GET /api/v1/dashboard?lat=&lon=
```

---

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Vanilla JS, CesiumJS 1.122, Canvas sparklines |
| Gateway | Go 1.22, Gin |
| Data Engine | Python 3.12, FastAPI, httpx |
| Cache | In-memory (default) or Redis |
| Infra | Docker Compose, Nginx |

---

## Feature Expansion

The architecture is designed for Prexus Atmos modules:

- **Atmos Vision** — satellite imagery overlays (Sentinel-5P via Copernicus)
- **Atmos Radar** — precipitation radar from NOAA/MRMS
- **Atmos Predict** — LSTM/TFT AQI forecasting model (replace Open-Meteo fallback)
- **Atmos Earth** — Digital twin storm/flood simulation
- **Atmos Sentinel** — IoT sensor ingestion via MQTT
