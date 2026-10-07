"""
Geospatial file reader service for KML and Shapefiles.
Extracts raw geometries (forcing 2D), sanitizes properties for JSON serialization,
and resolves coordinate reference systems.
"""
from dataclasses import dataclass
import datetime
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from shapely import force_2d
from shapely.geometry.base import BaseGeometry

from app.services.errors import InvalidFileContent, MissingCRS

# KML styling and visual attributes to drop
STYLING_COLUMNS = {
    "altitudemode",
    "tessellate",
    "extrude",
    "visibility",
    "draworder",
    "icon",
    "timestamp",
    "begin",
    "end",
}


@dataclass
class RawFeature:
    index: int
    geometry: Optional[BaseGeometry]
    properties: Dict[str, Any]


@dataclass
class ReadResult:
    crs: str
    crs_obj: CRS
    features: List[RawFeature]


def sanitize_property_value(val: Any) -> Any:
    """Ensure property values are strictly JSON-serializable."""
    if val is None:
        return None
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat()
    if isinstance(val, pd.Timestamp):
        if pd.isna(val):
            return None
        return val.isoformat()
    if isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val) or pd.isna(val):
            return None
        return float(val)
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    if pd.isna(val):
        return None
    return val


def read_features(path: Union[str, Path], kind: str) -> ReadResult:
    """
    Read spatial features from a KML file or Shapefile (.shp).

    For KML:
      - Reads all layers (Folders) and concatenates them.
      - Fixed to EPSG:4326.

    For Shapefile:
      - Reads via GeoPandas.
      - Requires a valid CRS; raises MissingCRS if absent.

    Common post-processing:
      - Strips Z dimensions via force_2d.
      - Drops styling columns and all-null columns.
      - Sanitizes attribute properties for JSON output.
      - Numbers features continuously (0-indexed).
    """
    path = Path(path)
    if not path.exists():
        raise InvalidFileContent(f"File not found: {path}")

    kind = kind.lower()

    if kind == "kml":
        try:
            import pyogrio
            layer_info = pyogrio.list_layers(str(path))
            if hasattr(layer_info, "ndim") and layer_info.ndim == 2:
                layer_names = [str(row[0]) for row in layer_info]
            elif isinstance(layer_info, (list, tuple, np.ndarray)):
                layer_names = [str(x[0] if isinstance(x, (list, tuple, np.ndarray)) else x) for x in layer_info]
            else:
                layer_names = [str(layer_info)]
        except Exception as e:
            raise InvalidFileContent(f"Failed to read KML file structure: {e}")

        dfs = []
        for layer_name in layer_names:
            try:
                gdf = gpd.read_file(str(path), layer=layer_name)
                if not gdf.empty:
                    dfs.append(gdf)
            except Exception as e:
                raise InvalidFileContent(f"Failed to read KML layer '{layer_name}': {e}")

        if not dfs:
            raise InvalidFileContent("File contains no features")

        df = pd.concat(dfs, ignore_index=True)
        crs_obj = CRS.from_epsg(4326)
        crs_display = "EPSG:4326"

    elif kind in ("shapefile_zip", "shapefile"):
        try:
            df = gpd.read_file(str(path))
        except Exception as e:
            raise InvalidFileContent(f"Failed to read shapefile: {e}")

        if df.crs is None:
            raise MissingCRS("Shapefile has no CRS (.prj file missing or unreadable)")

        crs_obj = CRS.from_user_input(df.crs)
        epsg = crs_obj.to_epsg()
        crs_display = f"EPSG:{epsg}" if epsg is not None else crs_obj.to_string()

    else:
        raise InvalidFileContent(f"Unknown kind '{kind}' for spatial reading")

    if len(df) == 0:
        raise InvalidFileContent("File contains no features")

    # Drop styling columns and columns that are entirely null
    cols_to_drop = [
        c
        for c in df.columns
        if c != "geometry" and (c.lower() in STYLING_COLUMNS or df[c].isna().all())
    ]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    property_cols = [c for c in df.columns if c != "geometry"]

    features: List[RawFeature] = []
    for idx, (_, row) in enumerate(df.iterrows()):
        geom = row.get("geometry")
        if geom is not None and not geom.is_empty:
            geom = force_2d(geom)
        else:
            geom = None

        props = {c: sanitize_property_value(row[c]) for c in property_cols}
        features.append(RawFeature(index=idx, geometry=geom, properties=props))

    if not features:
        raise InvalidFileContent("File contains no features")

    return ReadResult(crs=crs_display, crs_obj=crs_obj, features=features)
