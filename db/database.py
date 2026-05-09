-- ============================================================
-- Prexus Atmos — Database Schema
-- PostgreSQL + TimescaleDB + PostGIS
--
-- Run order:
--   1. Enable extensions
--   2. Create tables
--   3. Create hypertables
--   4. Create indexes
--   5. Create continuous aggregates
--   6. Create retention policy
-- ============================================================


-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for text search on city names


-- ── Core Snapshot Table ───────────────────────────────────────────────────────
-- This is the heart of Atmos storage.
-- One row = one canonical AtmosphericSnapshot.

CREATE TABLE IF NOT EXISTS atmospheric_snapshots (
    -- Identity
    event_id        UUID            NOT NULL DEFAULT uuid_generate_v4(),
    timestamp       TIMESTAMPTZ     NOT NULL,

    -- Location
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    geohash         TEXT            NOT NULL,
    city            TEXT            DEFAULT '',
    country         TEXT            DEFAULT '',
    geom            GEOMETRY(Point, 4326),  -- PostGIS point, auto-populated by trigger

    -- Atmosphere / AQI
    aqi_us          INTEGER,
    aqi_eu          INTEGER,
    pm2_5           FLOAT,
    pm10            FLOAT,
    dust            FLOAT,
    o3              FLOAT,
    no2             FLOAT,
    so2             FLOAT,
    co              FLOAT,
    aerosol_optical_depth FLOAT,
    aqi_category    TEXT            DEFAULT 'unknown',

    -- Weather
    temp_c          FLOAT,
    feels_like_c    FLOAT,
    humidity_pct    FLOAT,
    pressure_hpa    FLOAT,
    wind_speed_kmh  FLOAT,
    wind_dir_deg    FLOAT,
    wind_gusts_kmh  FLOAT,
    wind_cardinal   TEXT            DEFAULT '',
    uv_index        FLOAT,
    visibility_m    FLOAT,
    cloud_cover_pct FLOAT,
    precip_mm       FLOAT,
    weather_code    INTEGER,
    condition_label TEXT            DEFAULT '',
    is_day          BOOLEAN         DEFAULT TRUE,

    -- Hazards
    fire_nearby          BOOLEAN     DEFAULT FALSE,
    fire_count_500km     INTEGER     DEFAULT 0,
    smoke_level          TEXT        DEFAULT 'unknown',

    -- Analytics
    dominant_source      TEXT        DEFAULT 'unknown',
    source_confidence    INTEGER     DEFAULT 0,
    health_risk_general  TEXT        DEFAULT 'unknown',
    exceedances          TEXT[]      DEFAULT ARRAY[]::TEXT[],
    active_alerts        TEXT[]      DEFAULT ARRAY[]::TEXT[],

    -- Provenance
    sources              TEXT[]      DEFAULT ARRAY[]::TEXT[],

    -- Full snapshot JSON for ML / export (denormalized for speed)
    raw_snapshot         JSONB
);

-- Convert to TimescaleDB hypertable partitioned by time
SELECT create_hypertable(
    'atmospheric_snapshots',
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);


-- ── Fire Detections Table ─────────────────────────────────────────────────────
-- Separate table — fires are sparse and need their own spatial queries.

CREATE TABLE IF NOT EXISTS fire_detections (
    id              UUID            NOT NULL DEFAULT uuid_generate_v4(),
    timestamp       TIMESTAMPTZ     NOT NULL,
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    geom            GEOMETRY(Point, 4326),
    frp_mw          FLOAT           DEFAULT 0,
    confidence      TEXT            DEFAULT '',
    satellite       TEXT            DEFAULT '',
    day_night       TEXT            DEFAULT '',
    snapshot_id     UUID            -- FK to atmospheric_snapshots.event_id
);

SELECT create_hypertable(
    'fire_detections',
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);


-- ── Alert Events Table ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alert_events (
    id              UUID            NOT NULL DEFAULT uuid_generate_v4(),
    timestamp       TIMESTAMPTZ     NOT NULL,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    geohash         TEXT            DEFAULT '',
    alert_type      TEXT            NOT NULL,
    severity        TEXT            NOT NULL,  -- info/medium/high/critical
    title           TEXT            NOT NULL,
    message         TEXT            DEFAULT '',
    data            JSONB,
    resolved_at     TIMESTAMPTZ,
    snapshot_id     UUID
);

SELECT create_hypertable(
    'alert_events',
    'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);


-- ── Ingestion Jobs Table ──────────────────────────────────────────────────────
-- Tracks every worker run for observability.

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id              UUID            NOT NULL DEFAULT uuid_generate_v4(),
    started_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    worker          TEXT            NOT NULL,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    status          TEXT            NOT NULL DEFAULT 'running',  -- running/success/failed
    records_written INTEGER         DEFAULT 0,
    error           TEXT,
    duration_ms     INTEGER
);


-- ── Monitored Locations Table ─────────────────────────────────────────────────
-- The set of locations the ingestion workers actively poll.

CREATE TABLE IF NOT EXISTS monitored_locations (
    id              UUID            NOT NULL DEFAULT uuid_generate_v4() PRIMARY KEY,
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    geohash         TEXT            NOT NULL,
    city            TEXT            DEFAULT '',
    country         TEXT            DEFAULT '',
    priority        INTEGER         DEFAULT 1,   -- 1=high, 2=medium, 3=low
    interval_sec    INTEGER         DEFAULT 300, -- poll interval
    active          BOOLEAN         DEFAULT TRUE,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    last_ingested   TIMESTAMPTZ
);

-- Seed with global capitals + high-pollution cities
INSERT INTO monitored_locations (lat, lon, city, country, priority, interval_sec) VALUES
    (28.6139,  77.2090,  'New Delhi',    'IN', 1, 300),
    (19.0760,  72.8777,  'Mumbai',       'IN', 1, 300),
    (22.5726,  88.3639,  'Kolkata',      'IN', 1, 300),
    (12.9716,  77.5946,  'Bengaluru',    'IN', 1, 300),
    (39.9042, 116.4074,  'Beijing',      'CN', 1, 300),
    (31.2304, 121.4737,  'Shanghai',     'CN', 1, 300),
    (23.1291, 113.2644,  'Guangzhou',    'CN', 1, 300),
    (40.7128, -74.0060,  'New York',     'US', 1, 300),
    (34.0522,-118.2437,  'Los Angeles',  'US', 1, 300),
    (51.5074,  -0.1278,  'London',       'GB', 2, 600),
    (48.8566,   2.3522,  'Paris',        'FR', 2, 600),
    (52.5200,  13.4050,  'Berlin',       'DE', 2, 600),
    (35.6762, 139.6503,  'Tokyo',        'JP', 2, 600),
    (-33.8688, 151.2093, 'Sydney',       'AU', 2, 600),
    (-23.5505, -46.6333, 'São Paulo',    'BR', 2, 600),
    (30.0444,  31.2357,  'Cairo',        'EG', 2, 600),
    (14.6928,  -17.4467, 'Dakar',        'SN', 3, 900),
    (6.5244,    3.3792,  'Lagos',        'NG', 2, 600),
    (55.7558,  37.6173,  'Moscow',       'RU', 2, 600),
    (1.3521,  103.8198,  'Singapore',    'SG', 2, 600)
ON CONFLICT DO NOTHING;


-- ── Triggers ──────────────────────────────────────────────────────────────────

-- Auto-populate PostGIS geometry from lat/lon on atmospheric_snapshots
CREATE OR REPLACE FUNCTION set_geom_from_latlon()
RETURNS TRIGGER AS $$
BEGIN
    NEW.geom = ST_SetSRID(ST_MakePoint(NEW.lon, NEW.lat), 4326);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_atmos_snap_geom
    BEFORE INSERT OR UPDATE ON atmospheric_snapshots
    FOR EACH ROW EXECUTE FUNCTION set_geom_from_latlon();

CREATE TRIGGER trg_fire_geom
    BEFORE INSERT OR UPDATE ON fire_detections
    FOR EACH ROW EXECUTE FUNCTION set_geom_from_latlon();


-- ── Indexes ───────────────────────────────────────────────────────────────────

-- Spatial indexes (PostGIS GIST)
CREATE INDEX IF NOT EXISTS idx_atmos_snap_geom    ON atmospheric_snapshots USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_fire_det_geom       ON fire_detections       USING GIST (geom);

-- Geohash prefix search (fast proximity without PostGIS)
CREATE INDEX IF NOT EXISTS idx_atmos_geohash       ON atmospheric_snapshots (geohash, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_fire_geohash        ON fire_detections       (geohash text_pattern_ops);

-- AQI / category for dashboard queries
CREATE INDEX IF NOT EXISTS idx_atmos_aqi           ON atmospheric_snapshots (aqi_us, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_atmos_category      ON atmospheric_snapshots (aqi_category, timestamp DESC);

-- Alert queries
CREATE INDEX IF NOT EXISTS idx_alert_type_ts       ON alert_events (alert_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alert_severity      ON alert_events (severity, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alert_geohash       ON alert_events (geohash, timestamp DESC);

-- City search
CREATE INDEX IF NOT EXISTS idx_atmos_city          ON atmospheric_snapshots USING GIN (city gin_trgm_ops);


-- ── Continuous Aggregates (TimescaleDB) ───────────────────────────────────────
-- Pre-aggregate hourly stats for fast trend queries.

CREATE MATERIALIZED VIEW IF NOT EXISTS aqi_hourly_stats
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp)  AS bucket,
    geohash,
    city,
    AVG(aqi_us)                        AS aqi_us_avg,
    MAX(aqi_us)                        AS aqi_us_max,
    MIN(aqi_us)                        AS aqi_us_min,
    AVG(pm2_5)                         AS pm2_5_avg,
    AVG(pm10)                          AS pm10_avg,
    AVG(no2)                           AS no2_avg,
    AVG(o3)                            AS o3_avg,
    AVG(temp_c)                        AS temp_c_avg,
    AVG(humidity_pct)                  AS humidity_avg,
    COUNT(*)                           AS sample_count
FROM atmospheric_snapshots
GROUP BY bucket, geohash, city
WITH NO DATA;

-- Refresh policy: run every 30 minutes, covering last 3 hours
SELECT add_continuous_aggregate_policy('aqi_hourly_stats',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE
);

-- Daily aggregate for longer trend views
CREATE MATERIALIZED VIEW IF NOT EXISTS aqi_daily_stats
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', timestamp)   AS bucket,
    geohash,
    city,
    country,
    AVG(aqi_us)                        AS aqi_us_avg,
    MAX(aqi_us)                        AS aqi_us_max,
    MIN(aqi_us)                        AS aqi_us_min,
    PERCENTILE_CONT(0.95)
        WITHIN GROUP (ORDER BY aqi_us) AS aqi_us_p95,
    AVG(pm2_5)                         AS pm2_5_avg,
    AVG(temp_c)                        AS temp_c_avg,
    SUM(fire_count_500km)              AS total_fires,
    COUNT(*)                           AS sample_count
FROM atmospheric_snapshots
GROUP BY bucket, geohash, city, country
WITH NO DATA;

SELECT add_continuous_aggregate_policy('aqi_daily_stats',
    start_offset => INTERVAL '2 days',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);


-- ── Retention Policy ──────────────────────────────────────────────────────────
-- Raw snapshots: keep 90 days (hourly + daily aggregates kept forever)
SELECT add_retention_policy('atmospheric_snapshots',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

SELECT add_retention_policy('fire_detections',
    INTERVAL '90 days',
    if_not_exists => TRUE
);


-- ── Useful Views ──────────────────────────────────────────────────────────────

-- Latest snapshot per monitored location
CREATE OR REPLACE VIEW latest_snapshots AS
SELECT DISTINCT ON (geohash)
    event_id, timestamp, lat, lon, geohash, city, country,
    aqi_us, aqi_category, pm2_5, pm10, no2, o3,
    temp_c, humidity_pct, wind_speed_kmh, wind_cardinal,
    fire_nearby, fire_count_500km, smoke_level,
    dominant_source, health_risk_general, active_alerts
FROM atmospheric_snapshots
ORDER BY geohash, timestamp DESC;

-- Active high-severity alerts in last 6 hours
CREATE OR REPLACE VIEW active_high_alerts AS
SELECT *
FROM alert_events
WHERE severity IN ('high', 'critical')
  AND timestamp > NOW() - INTERVAL '6 hours'
  AND resolved_at IS NULL
ORDER BY timestamp DESC;
