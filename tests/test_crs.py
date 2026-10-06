"""
Tests for app/services/crs.py.
Covers: zone arithmetic, hemisphere selection, clamping, polar rejection,
and that to_utm returns meter-range coordinates for a known location.
"""
import pytest
from shapely.geometry import Point, Polygon

from app.services.crs import to_utm, to_wgs84, utm_epsg_for


# ---------------------------------------------------------------------------
# utm_epsg_for: zone arithmetic
# ---------------------------------------------------------------------------

def test_chennai_northern():
    # Chennai (80.27°E, 13.08°N) -> zone 44 northern -> 32644
    assert utm_epsg_for(80.27, 13.08) == 32644


def test_sydney_southern():
    # Sydney (151.2°E, 33.9°S) -> zone 56 southern -> 32756
    assert utm_epsg_for(151.2, -33.9) == 32756


def test_new_york_northern():
    # New York (-74.0°E, 40.7°N) -> zone 18 northern -> 32618
    assert utm_epsg_for(-74.0, 40.7) == 32618


def test_lon_180_clamps_to_zone_60():
    # Without clamping, (180+180)//6 + 1 = 61; must be clamped to 60.
    assert utm_epsg_for(180, 0) == 32660


def test_lon_minus_180_gives_zone_1():
    assert utm_epsg_for(-180, 0) == 32601


def test_polar_north_raises():
    with pytest.raises(ValueError, match="polar"):
        utm_epsg_for(0, 85)


def test_polar_south_raises():
    with pytest.raises(ValueError, match="polar"):
        utm_epsg_for(0, -85)


def test_exactly_84_is_ok():
    # Boundary: abs(lat)==84 is still valid.
    assert utm_epsg_for(0, 84) == 32631


# ---------------------------------------------------------------------------
# to_utm: coordinate range sanity check
# ---------------------------------------------------------------------------

def test_to_utm_chennai_polygon():
    # A small square near Chennai; easting should be in the 100 000-900 000 m
    # range that UTM eastings always fall in (false easting 500 000 at CM).
    poly = Polygon([
        (80.27, 13.08),
        (80.28, 13.08),
        (80.28, 13.09),
        (80.27, 13.09),
        (80.27, 13.08),
    ])
    projected, epsg = to_utm(poly)

    assert epsg == 32644
    x, y = projected.centroid.x, projected.centroid.y
    assert 100_000 < x < 900_000, f"easting {x} out of UTM range"
    assert y > 0, "northing should be positive in northern hemisphere"


# ---------------------------------------------------------------------------
# to_wgs84: no-op when source is already 4326
# ---------------------------------------------------------------------------

def test_to_wgs84_passthrough():
    pt = Point(80.27, 13.08)
    result = to_wgs84(pt, "EPSG:4326")
    assert result is pt  # same object, no transform applied


def test_to_wgs84_from_utm():
    # Project a point to UTM 44N then back; should land very close to origin.
    from pyproj import Transformer
    import shapely.ops

    src = Transformer.from_crs(4326, 32644, always_xy=True)
    pt_utm = shapely.ops.transform(src.transform, Point(80.27, 13.08))

    pt_back = to_wgs84(pt_utm, "EPSG:32644")
    assert abs(pt_back.x - 80.27) < 1e-6
    assert abs(pt_back.y - 13.08) < 1e-6
