"""
Tests for app/services/measure.py.
Cross-checks UTM-based results against pyproj.Geod (geodesic) within 0.5%,
which is well inside UTM's scale-factor distortion band.
"""
import math

import pytest
from pyproj import Geod
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
)

from app.services.measure import measure_geometry

GEOD = Geod(ellps="WGS84")
REL_TOL = 0.005  # 0.5 %


def rel_close(a: float, b: float, tol: float = REL_TOL) -> bool:
    """True if a and b agree within relative tolerance tol."""
    return math.isclose(a, b, rel_tol=tol)


# ---------------------------------------------------------------------------
# Polygon: area cross-check against Geod
# ---------------------------------------------------------------------------

CHENNAI_POLY = Polygon([
    (80.27, 13.08), (80.37, 13.08),
    (80.37, 13.18), (80.27, 13.18),
    (80.27, 13.08),
])

SYDNEY_POLY = Polygon([
    (151.2, -33.9), (151.3, -33.9),
    (151.3, -34.0), (151.2, -34.0),
    (151.2, -33.9),
])


def test_polygon_area_vs_geod_chennai():
    result = measure_geometry(CHENNAI_POLY)

    assert result.supported
    assert result.area_sq_m is not None

    geod_area, _ = GEOD.geometry_area_perimeter(CHENNAI_POLY)
    assert rel_close(result.area_sq_m, abs(geod_area)), (
        f"UTM area {result.area_sq_m:.1f} vs Geod {abs(geod_area):.1f}"
    )


# ---------------------------------------------------------------------------
# Line: length cross-check against Geod
# ---------------------------------------------------------------------------

def test_line_length_vs_geod():
    line = LineString([(80.27, 13.08), (80.37, 13.18)])
    result = measure_geometry(line)

    assert result.supported
    assert result.length_m is not None

    geod_len = GEOD.geometry_length(line)
    assert rel_close(result.length_m, geod_len), (
        f"UTM length {result.length_m:.1f} vs Geod {geod_len:.1f}"
    )


# ---------------------------------------------------------------------------
# MultiPolygon: area equals sum of parts
# ---------------------------------------------------------------------------

def test_multipolygon_area_sum_of_parts():
    p1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    p2 = Polygon([(2, 0), (3, 0), (3, 1), (2, 1), (2, 0)])
    multi = MultiPolygon([p1, p2])

    r_multi = measure_geometry(multi)
    r1 = measure_geometry(p1)
    r2 = measure_geometry(p2)

    assert r_multi.supported
    assert rel_close(r_multi.area_sq_m, r1.area_sq_m + r2.area_sq_m)


# ---------------------------------------------------------------------------
# Hole: polygon with hole < polygon without hole
# ---------------------------------------------------------------------------

def test_polygon_hole_smaller_than_solid():
    outer = [(80.27, 13.08), (80.37, 13.08), (80.37, 13.18), (80.27, 13.18)]
    inner = [(80.29, 13.10), (80.35, 13.10), (80.35, 13.16), (80.29, 13.16)]
    solid = Polygon(outer)
    with_hole = Polygon(outer, [inner])

    r_solid = measure_geometry(solid)
    r_hole = measure_geometry(with_hole)

    assert r_hole.area_sq_m < r_solid.area_sq_m


# ---------------------------------------------------------------------------
# Point: supported, no numeric measurement
# ---------------------------------------------------------------------------

def test_point_supported_no_measurement():
    result = measure_geometry(Point(80.27, 13.08))
    assert result.supported is True
    assert result.area_sq_m is None
    assert result.length_m is None
    assert result.note == "no measurement for points"


# ---------------------------------------------------------------------------
# Unsupported / invalid cases
# ---------------------------------------------------------------------------

def test_empty_polygon_unsupported():
    result = measure_geometry(Polygon())
    assert result.supported is False
    assert result.note == "empty geometry"


def test_invalid_bowtie_polygon_unsupported():
    # Figure-eight / bow-tie: self-intersecting -> not valid
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    assert not bowtie.is_valid  # sanity-check the fixture itself
    result = measure_geometry(bowtie)
    assert result.supported is False
    assert result.note == "invalid geometry"


def test_geometry_collection_unsupported():
    gc = GeometryCollection([Point(0, 0), LineString([(0, 0), (1, 1)])])
    result = measure_geometry(gc)
    assert result.supported is False
    assert "unsupported geometry type" in result.note


def test_none_unsupported():
    result = measure_geometry(None)
    assert result.supported is False
    assert result.note == "empty geometry"


# ---------------------------------------------------------------------------
# measurement_crs: correct hemisphere / zone label
# ---------------------------------------------------------------------------

def test_measurement_crs_northern_chennai():
    result = measure_geometry(CHENNAI_POLY)
    assert result.measurement_crs == "EPSG:32644"


def test_measurement_crs_southern_sydney():
    result = measure_geometry(SYDNEY_POLY)
    assert result.measurement_crs == "EPSG:32756"


def test_measurement_crs_line():
    line = LineString([(80.27, 13.08), (80.37, 13.18)])
    result = measure_geometry(line)
    assert result.measurement_crs == "EPSG:32644"
