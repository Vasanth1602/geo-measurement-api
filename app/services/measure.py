"""
Geometry measurement service.
Input geometry must already be in EPSG:4326 (WGS-84).
We project to UTM (meters) and use shapely's planar area/length.
All exceptions are caught so one bad feature never crashes a request.
"""
from dataclasses import dataclass
from typing import Optional

from shapely.validation import explain_validity

from app.services import crs as crs_svc


@dataclass
class MeasurementResult:
    supported: bool
    area_sq_m: Optional[float]
    length_m: Optional[float]
    measurement_crs: Optional[str]
    note: Optional[str]


def measure_geometry(geom_wgs84) -> MeasurementResult:
    """Measure area (polygons) or length (lines) of a WGS-84 geometry.

    Returns a MeasurementResult; never raises.
    """
    try:
        # --- guard: missing or empty ----------------------------------------
        if geom_wgs84 is None or geom_wgs84.is_empty:
            return MeasurementResult(
                supported=False,
                area_sq_m=None, length_m=None,
                measurement_crs=None, note="empty geometry",
            )

        # --- guard: self-intersecting / degenerate --------------------------
        if not geom_wgs84.is_valid:
            return MeasurementResult(
                supported=False,
                area_sq_m=None, length_m=None,
                measurement_crs=None,
                # explain_validity gives a human-readable reason (e.g. "Self-intersection")
                note=f"invalid geometry: {explain_validity(geom_wgs84)}",
            )

        gtype = geom_wgs84.geom_type

        # --- points: supported but no numeric measurement -------------------
        if gtype in ("Point", "MultiPoint"):
            return MeasurementResult(
                supported=True,
                area_sq_m=None, length_m=None,
                measurement_crs=None, note="no measurement for points",
            )

        # --- polygons -------------------------------------------------------
        if gtype in ("Polygon", "MultiPolygon"):
            projected, epsg = crs_svc.to_utm(geom_wgs84)
            return MeasurementResult(
                supported=True,
                area_sq_m=projected.area,
                length_m=None,
                measurement_crs=f"EPSG:{epsg}",
                note=None,
            )

        # --- lines ----------------------------------------------------------
        if gtype in ("LineString", "MultiLineString"):
            projected, epsg = crs_svc.to_utm(geom_wgs84)
            return MeasurementResult(
                supported=True,
                area_sq_m=None,
                length_m=projected.length,
                measurement_crs=f"EPSG:{epsg}",
                note=None,
            )

        # --- everything else (GeometryCollection, etc.) ---------------------
        return MeasurementResult(
            supported=False,
            area_sq_m=None, length_m=None,
            measurement_crs=None,
            note=f"unsupported geometry type: {gtype}",
        )

    except ValueError as exc:
        # to_utm raises ValueError for polar coordinates or invalid longitude
        return MeasurementResult(
            supported=False,
            area_sq_m=None, length_m=None,
            measurement_crs=None, note=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 – intentional catch-all
        return MeasurementResult(
            supported=False,
            area_sq_m=None, length_m=None,
            measurement_crs=None, note=f"unexpected error: {exc}",
        )
