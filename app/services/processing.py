"""
File processing pipeline: orchestrates extraction, reading, reprojection, and measurement.
Persists feature records and updates file status.
"""
from pathlib import Path
import tempfile
from typing import Union

import shapely
from sqlalchemy.orm import Session

from app.models import FeatureRecord, UploadedFile
from app.services.crs import to_wgs84
from app.services.ingest import safe_extract_zip
from app.services.measure import measure_geometry
from app.services.reader import read_features


def process_file(
    db: Session,
    record: UploadedFile,
    path: Union[str, Path],
    kind: str,
) -> None:
    """
    Process an uploaded geospatial file:
    - Extracts shapefiles into a temporary directory if zipped.
    - Reads features and CRS metadata.
    - Reprojects each geometry to WGS-84 and measures via UTM.
    - Captures per-feature errors without aborting the batch.
    - Persists all FeatureRecords and marks UploadedFile as COMPLETED.
    """
    path = Path(path)

    if kind == "shapefile_zip":
        with tempfile.TemporaryDirectory() as temp_dir:
            shp_path = safe_extract_zip(path, Path(temp_dir))
            result = read_features(shp_path, kind="shapefile")
    elif kind == "kml":
        result = read_features(path, kind="kml")
    else:
        raise ValueError(f"Unsupported kind for processing: {kind}")

    feature_records = []
    for feat in result.features:
        raw_geom = feat.geometry
        geom_type = raw_geom.geom_type if raw_geom else None
        # Original geometry in the file's CRS as GeoJSON
        geojson_str = shapely.to_geojson(raw_geom) if raw_geom else None

        try:
            if raw_geom is not None:
                wgs84_geom = to_wgs84(raw_geom, result.crs_obj)
                meas = measure_geometry(wgs84_geom)
            else:
                meas = measure_geometry(None)

            feature_records.append(
                FeatureRecord(
                    file_id=record.id,
                    index=feat.index,
                    geometry_type=geom_type,
                    geometry_geojson=geojson_str,
                    properties=feat.properties,
                    supported=meas.supported,
                    area_sq_m=meas.area_sq_m,
                    length_m=meas.length_m,
                    measurement_crs=meas.measurement_crs,
                    note=meas.note,
                )
            )
        except Exception as exc:
            feature_records.append(
                FeatureRecord(
                    file_id=record.id,
                    index=feat.index,
                    geometry_type=geom_type,
                    geometry_geojson=geojson_str,
                    properties=feat.properties,
                    supported=False,
                    area_sq_m=None,
                    length_m=None,
                    measurement_crs=None,
                    note=f"Processing error: {exc}",
                )
            )

    db.add_all(feature_records)
    record.feature_count = len(result.features)
    record.crs = result.crs
    record.status = "COMPLETED"
    record.error = None
    db.commit()
    db.refresh(record)
