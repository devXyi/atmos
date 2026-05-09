"""
Atmos Core — Geo Utilities
Spatial helpers used across normalizers, analytics, and ingestion.
No external geo dependency — pure math.
"""

from __future__ import annotations
import math


EARTH_RADIUS_KM = 6371.0


# ─── Distance ─────────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in km."""
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# ─── Bounding Box ─────────────────────────────────────────────────────────────

def bounding_box(lat: float, lon: float, radius_km: float) -> dict:
    """
    Returns W, S, E, N bounding box (in degrees) around a point.
    Used for NASA FIRMS, WAQI station queries, etc.
    """
    delta_lat = math.degrees(radius_km / EARTH_RADIUS_KM)
    delta_lon = math.degrees(radius_km / (EARTH_RADIUS_KM * math.cos(math.radians(lat))))
    return {
        "west":  lon - delta_lon,
        "south": lat - delta_lat,
        "east":  lon + delta_lon,
        "north": lat + delta_lat,
    }


def bbox_string(lat: float, lon: float, radius_km: float) -> str:
    """Returns 'W,S,E,N' string for FIRMS API."""
    b = bounding_box(lat, lon, radius_km)
    return f"{b['west']:.4f},{b['south']:.4f},{b['east']:.4f},{b['north']:.4f}"


# ─── Grid Generation ─────────────────────────────────────────────────────────

def generate_grid(
    center_lat: float,
    center_lon: float,
    resolution_deg: float = 0.25,
    radius_deg: float = 2.0,
) -> list[tuple[float, float]]:
    """
    Generates a regular lat/lon grid for heatmap queries.
    Returns list of (lat, lon) tuples.
    """
    points = []
    lat = center_lat - radius_deg
    while lat <= center_lat + radius_deg + 1e-9:
        lon = center_lon - radius_deg
        while lon <= center_lon + radius_deg + 1e-9:
            points.append((round(lat, 4), round(lon, 4)))
            lon += resolution_deg
        lat += resolution_deg
    return points


# ─── Cardinal Direction ───────────────────────────────────────────────────────

_CARDINALS = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
               "S","SSW","SW","WSW","W","WNW","NW","NNW"]

def deg_to_cardinal(deg: float) -> str:
    return _CARDINALS[round(deg / 22.5) % 16]


# ─── Geohash (self-contained) ────────────────────────────────────────────────

_GH_CHARS = "0123456789bcdefghjkmnpqrstuvwxyz"

def encode_geohash(lat: float, lon: float, precision: int = 6) -> str:
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    result, bits = [], 0
    use_lon = True
    while len(result) < precision:
        for _ in range(5):
            if use_lon:
                mid = (lon_range[0] + lon_range[1]) / 2
                if lon >= mid:
                    bits = (bits << 1) | 1
                    lon_range[0] = mid
                else:
                    bits <<= 1
                    lon_range[1] = mid
            else:
                mid = (lat_range[0] + lat_range[1]) / 2
                if lat >= mid:
                    bits = (bits << 1) | 1
                    lat_range[0] = mid
                else:
                    bits <<= 1
                    lat_range[1] = mid
            use_lon = not use_lon
        result.append(_GH_CHARS[bits])
        bits = 0
    return "".join(result)


def geohash_neighbors(geohash: str) -> list[str]:
    """Returns the 8 neighboring geohash cells — useful for spatial proximity queries."""
    # Decode center, shift, re-encode
    lat, lon = decode_geohash(geohash)
    precision = len(geohash)
    # Approximate cell size
    lat_err = 90.0 / (2 ** (5 * precision // 2))
    lon_err = 180.0 / (2 ** (5 * (precision + 1) // 2))
    neighbors = []
    for dlat in [-1, 0, 1]:
        for dlon in [-1, 0, 1]:
            if dlat == 0 and dlon == 0:
                continue
            nlat = max(-90.0, min(90.0,  lat + dlat * lat_err * 2))
            nlon = ((lon + dlon * lon_err * 2) + 180) % 360 - 180
            neighbors.append(encode_geohash(nlat, nlon, precision))
    return neighbors


def decode_geohash(geohash: str) -> tuple[float, float]:
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    use_lon = True
    for char in geohash:
        bits = _GH_CHARS.index(char)
        for i in range(4, -1, -1):
            bit = (bits >> i) & 1
            if use_lon:
                mid = (lon_range[0] + lon_range[1]) / 2
                if bit:
                    lon_range[0] = mid
                else:
                    lon_range[1] = mid
            else:
                mid = (lat_range[0] + lat_range[1]) / 2
                if bit:
                    lat_range[0] = mid
                else:
                    lat_range[1] = mid
            use_lon = not use_lon
    lat = (lat_range[0] + lat_range[1]) / 2
    lon = (lon_range[0] + lon_range[1]) / 2
    return lat, lon
