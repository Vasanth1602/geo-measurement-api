"""
API endpoints for file uploads, metadata status, and per-feature measurements.
"""
import json
from pathlib import Path
import shutil
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

import app.config as config
from app.db import get_db
from app.models import FeatureRecord, UploadedFile
from app.schemas import FeatureOut, FileOut, MeasurementsOut
from app.services.errors import (
    FileTooLarge,
    InvalidFileContent,
    MissingCRS,
    UnsupportedFileType,
)
from app.services.ingest import detect_kind, save_upload
from app.services.processing import process_file

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=FileOut)
def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a geospatial file (.kml or shapefile .zip).
    Processes synchronously, validates content, extracts features, and calculates measurements.
    """
    raw_filename = file.filename or ""

    # 1. Pre-validation: detect kind before writing anything to disk
    try:
        kind = detect_kind(raw_filename)
    except UnsupportedFileType as e:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e))

    display_filename = Path(raw_filename).name
    file_id = str(uuid.uuid4())
    dest_dir = Path(config.UPLOAD_DIR) / file_id

    # 2. Stream to disk under uploads/<uuid>/ (cleans up folder on FileTooLarge)
    try:
        saved_path = save_upload(file, dest_dir)
    except FileTooLarge as e:
        if dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))

    # 3. Insert initial PROCESSING record
    record = UploadedFile(
        id=file_id,
        filename=display_filename,
        kind=kind,
        status="PROCESSING",
        feature_count=None,
        crs=None,
        error=None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # 4. Process the file
    try:
        process_file(db, record, saved_path, kind)
    except (InvalidFileContent, MissingCRS) as e:
        # Known client/content errors: clean up disk and remove the DB row
        if dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
        db.delete(record)
        db.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        # Unexpected server-side failures: preserve record with FAILED status for debugging
        record.status = "FAILED"
        record.error = str(e)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error processing file '{file_id}': {e}",
        )

    return record


@router.get("/{id}/", response_model=FileOut)
def get_file(id: str, db: Session = Depends(get_db)):
    """Retrieve file metadata and processing status."""
    record = db.query(UploadedFile).filter(UploadedFile.id == id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with id '{id}' not found",
        )
    return record


@router.get("/{id}/measurements/", response_model=MeasurementsOut)
def get_measurements(
    id: str,
    include_geometry: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    Retrieve measurements for all features in an uploaded file.
    Geometry GeoJSON can be omitted by passing ?include_geometry=false.
    """
    record = db.query(UploadedFile).filter(UploadedFile.id == id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with id '{id}' not found",
        )

    features = (
        db.query(FeatureRecord)
        .filter(FeatureRecord.file_id == id)
        .order_by(FeatureRecord.index.asc())
        .all()
    )

    feature_outs = []
    file_crs = record.crs or "EPSG:4326"
    for f in features:
        geom_dict = None
        if include_geometry and f.geometry_geojson:
            try:
                geom_dict = json.loads(f.geometry_geojson)
            except Exception:
                geom_dict = None

        feature_outs.append(
            FeatureOut(
                index=f.index,
                geometry_type=f.geometry_type,
                crs=file_crs,
                properties=f.properties or {},
                geometry=geom_dict,
                supported=f.supported,
                area_sq_m=f.area_sq_m,
                length_m=f.length_m,
                measurement_crs=f.measurement_crs,
                note=f.note,
            )
        )

    return MeasurementsOut(
        file_id=record.id,
        crs=record.crs,
        feature_count=record.feature_count or len(feature_outs),
        features=feature_outs,
    )
