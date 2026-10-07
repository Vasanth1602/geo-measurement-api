"""
Tests for file ingestion, validation, and extraction security in app/services/ingest.py.
"""
import io
from pathlib import Path
import zipfile

import pytest

import app.config as config
from app.services.errors import FileTooLarge, InvalidFileContent, UnsupportedFileType
from app.services.ingest import detect_kind, safe_extract_zip, save_upload


class DummyUploadFile:
    """Mock upload object mimicking FastAPI UploadFile."""
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.file = io.BytesIO(content)


def test_detect_kind_valid():
    assert detect_kind("survey.kml") == "kml"
    assert detect_kind("SURVEY.KML") == "kml"
    assert detect_kind("parcels.zip") == "shapefile_zip"
    assert detect_kind("boundary.Zip") == "shapefile_zip"


def test_detect_kind_unsupported():
    with pytest.raises(UnsupportedFileType):
        detect_kind("document.txt")

    with pytest.raises(UnsupportedFileType):
        detect_kind("data.geojson")

    with pytest.raises(UnsupportedFileType):
        detect_kind("")


def test_save_upload_success(tmp_path: Path):
    content = b"Mock KML file data content"
    upload = DummyUploadFile("my_client_name.kml", content)
    dest_dir = tmp_path / "uploads" / "id1"

    saved_path = save_upload(upload, dest_dir)
    assert saved_path.exists()
    assert saved_path.name == "upload.kml"  # Fixed internal name, not client name
    assert saved_path.read_bytes() == content


def test_save_upload_oversize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 1)
    # 1.5 MB payload
    oversized_data = b"X" * (int(1.5 * 1024 * 1024))
    upload = DummyUploadFile("huge.zip", oversized_data)
    dest_dir = tmp_path / "uploads" / "id2"

    with pytest.raises(FileTooLarge):
        save_upload(upload, dest_dir)

    # Verify partial file is cleaned up
    assert not (dest_dir / "upload.zip").exists()


def test_safe_extract_zip_valid(make_shapefile_zip, tmp_path: Path):
    zip_path = make_shapefile_zip("valid.zip")
    extract_dir = tmp_path / "extracted_valid"

    shp_path = safe_extract_zip(zip_path, extract_dir)
    assert shp_path.exists()
    assert shp_path.suffix.lower() == ".shp"


def test_safe_extract_zip_in_subfolder(make_shapefile_zip, tmp_path: Path):
    zip_path = make_shapefile_zip("nested.zip", subfolder="nested/folder")
    extract_dir = tmp_path / "extracted_nested"

    shp_path = safe_extract_zip(zip_path, extract_dir)
    assert shp_path.exists()
    assert shp_path.suffix.lower() == ".shp"


def test_safe_extract_zip_slip(tmp_path: Path):
    slip_zip = tmp_path / "slip.zip"
    with zipfile.ZipFile(slip_zip, "w") as zf:
        zf.writestr("../evil.txt", "malicious payload")

    extract_dir = tmp_path / "extract_slip"
    with pytest.raises(InvalidFileContent) as exc_info:
        safe_extract_zip(slip_zip, extract_dir)

    assert "Zip-slip detected" in str(exc_info.value)
    assert not (tmp_path / "evil.txt").exists()


def test_safe_extract_zip_bomb(make_shapefile_zip, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "MAX_UNZIPPED_MB", 0)  # 0 MB threshold
    zip_path = make_shapefile_zip("bomb.zip")
    extract_dir = tmp_path / "extract_bomb"

    with pytest.raises(InvalidFileContent) as exc_info:
        safe_extract_zip(zip_path, extract_dir)

    assert "exceeds size limit" in str(exc_info.value)


def test_safe_extract_corrupt_zip(tmp_path: Path):
    fake_zip = tmp_path / "not_a_zip.zip"
    fake_zip.write_text("This is plain text pretending to be a zip archive.")
    extract_dir = tmp_path / "extract_corrupt"

    with pytest.raises(InvalidFileContent) as exc_info:
        safe_extract_zip(fake_zip, extract_dir)

    assert "not a valid zip archive" in str(exc_info.value)


def test_safe_extract_missing_companion(make_shapefile_zip, tmp_path: Path):
    no_shx = make_shapefile_zip("no_shx.zip", include_shx=False)
    extract_dir1 = tmp_path / "extract_no_shx"
    with pytest.raises(InvalidFileContent) as exc1:
        safe_extract_zip(no_shx, extract_dir1)
    assert "missing required companion file" in str(exc1.value)
    assert ".shx" in str(exc1.value)

    no_dbf = make_shapefile_zip("no_dbf.zip", include_dbf=False)
    extract_dir2 = tmp_path / "extract_no_dbf"
    with pytest.raises(InvalidFileContent) as exc2:
        safe_extract_zip(no_dbf, extract_dir2)
    assert "missing required companion file" in str(exc2.value)
    assert ".dbf" in str(exc2.value)


def test_safe_extract_multiple_shp(make_shapefile_zip, tmp_path: Path):
    two_shp = make_shapefile_zip("two_shp.zip", extra_shp=True)
    extract_dir = tmp_path / "extract_two"

    with pytest.raises(InvalidFileContent) as exc_info:
        safe_extract_zip(two_shp, extract_dir)

    assert "multiple .shp files" in str(exc_info.value)
