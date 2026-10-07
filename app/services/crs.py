"""
CRS utilities: UTM zone selection and reprojection.
All measurement happens in projected (meter-based) coordinates, never in degrees.
"""
import shapely.ops
from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry


def utm_epsg_for(lon: float, lat: float) -> int:
    """Return the EPSG code of the UTM zone that contains (lon, lat).

    Raises ValueError for:
    - polar latitudes (lat > 84 or lat < -80) where UTM is undefined.
    - longitudes outside -180..180 which are not valid WGS-84 coordinates.
    """
    if lon < -180 or lon > 180:
        raise ValueError(
            f"longitude {lon} is outside -180..180; not a valid WGS-84 coordinate"
        )

    if lat > 84 or lat < -80:
        raise ValueError(
            f"UTM is undefined for polar latitudes (lat={lat}); "
            "valid range is -80..84"
        )

    zone = int((lon + 180) // 6) + 1
    zone = max(1, min(60, zone))  # clamp: lon=180 would give 61 without this

    return 32600 + zone if lat >= 0 else 32700 + zone


def to_wgs84(geom: BaseGeometry, source_crs) -> BaseGeometry:
    """Reproject geom from source_crs to EPSG:4326.

    If the geometry is already in EPSG:4326 we return it unchanged to avoid
    floating-point drift from a no-op transform.
    """
    src = CRS.from_user_input(source_crs)
    if src.equals(CRS.from_epsg(4326)):
        return geom

    # always_xy=True forces (lon, lat) axis order regardless of CRS authority
    # defaults; without it pyproj may expect (lat, lon) for geographic CRSes.
    transformer = Transformer.from_crs(src, 4326, always_xy=True)
    return shapely.ops.transform(transformer.transform, geom)


def to_utm(geom_wgs84: BaseGeometry) -> tuple[BaseGeometry, int]:
    """Project a WGS-84 geometry into its local UTM zone.

    Returns (projected_geometry, utm_epsg_code).
    The centroid is used to pick the zone so that every feature gets one
    consistent CRS even if its edges straddle a zone boundary.
    """
    centroid = geom_wgs84.centroid
    epsg = utm_epsg_for(centroid.x, centroid.y)  # centroid.x = lon, .y = lat

    # always_xy=True: input is (lon, lat), output is (easting, northing) in meters.
    transformer = Transformer.from_crs(4326, epsg, always_xy=True)
    projected = shapely.ops.transform(transformer.transform, geom_wgs84)
    return projected, epsg
