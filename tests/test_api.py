"""
End-to-end API integration tests for Geo Measurement API using FastAPI TestClient.
Tests cover all HTTP status codes (201, 200, 404, 413, 415, 422), unit derivation,
geodesic accuracy checks (pyproj.Geod), resiliency to partial bad features, and disk/db cleanup.
"""
from pathlib import Path
import zipfile

import pytest
import pyproj
from shapely.geometry import shape

import app.config as config
from app.models import UploadedFile


@pytest.fixture
def chennai_kml(tmp_path: Path) -> Path:
    """Self-contained KML fixture with polygon, linestring, and point in Chennai."""
    content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Chennai Survey</name>
      <Placemark>
        <name>Ripon Building Ground</name>
        <Polygon>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                80.2720,13.0820,0
                80.2750,13.0820,0
                80.2750,13.0850,0
                80.2720,13.0850,0
                80.2720,13.0820,0
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>
        </Polygon>
      </Placemark>
      <Placemark>
        <name>Poonamallee High Road Segment</name>
        <LineString>
          <coordinates>
            80.2680,13.0810,0
            80.2720,13.0825,0
            80.2760,13.0835,0
            80.2800,13.0845,0
          </coordinates>
        </LineString>
      </Placemark>
      <Placemark>
        <name>Chennai Central Landmark</name>
        <Point>
          <coordinates>80.2755,13.0827,0</coordinates>
        </Point>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    kml_file = tmp_path / "chennai_survey.kml"
    kml_file.write_text(content.strip(), encoding="utf-8")
    return kml_file


@pytest.fixture
def mixed_bad_kml(tmp_path: Path) -> Path:
    """KML with mixed geometry collection, self-intersecting bow-tie polygon, and valid features."""
    content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Resilience Test</name>
      <Placemark>
        <name>Valid Square Polygon</name>
        <Polygon>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                80.25,13.05,0 80.26,13.05,0 80.26,13.06,0 80.25,13.06,0 80.25,13.05,0
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>
        </Polygon>
      </Placemark>
      <Placemark>
        <name>MultiGeometry Collection</name>
        <MultiGeometry>
          <Point><coordinates>80.255,13.055,0</coordinates></Point>
          <LineString><coordinates>80.25,13.05,0 80.26,13.06,0</coordinates></LineString>
        </MultiGeometry>
      </Placemark>
      <Placemark>
        <name>Self-intersecting Bowtie</name>
        <Polygon>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                80.25,13.05,0 80.27,13.07,0 80.27,13.05,0 80.25,13.07,0 80.25,13.05,0
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>
        </Polygon>
      </Placemark>
      <Placemark>
        <name>Valid Coastal Line</name>
        <LineString>
          <coordinates>
            80.28,13.04,0 80.285,13.05,0 80.29,13.06,0
          </coordinates>
        </LineString>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    kml_file = tmp_path / "mixed_resilience.kml"
    kml_file.write_text(content.strip(), encoding="utf-8")
    return kml_file


# ---------------------------------------------------------------------------
# 1. Successful Uploads & Status
# ---------------------------------------------------------------------------

def test_upload_sample_kml(client, chennai_kml: Path):
    with open(chennai_kml, "rb") as f:
        response = client.post("/api/files/", files={"file": ("survey.kml", f, "application/vnd.google-earth.kml+xml")})

    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "survey.kml"
    assert data["status"] == "COMPLETED"
    assert data["feature_count"] == 3
    assert data["crs"] == "EPSG:4326"
    assert "id" in data


def test_upload_polygon_zip_and_get_info_and_measurements(client, make_shapefile_zip):
    zip_path = make_shapefile_zip("parcels.zip")
    with open(zip_path, "rb") as f:
        post_resp = client.post("/api/files/", files={"file": ("parcels.zip", f, "application/zip")})

    assert post_resp.status_code == 201
    post_data = post_resp.json()
    file_id = post_data["id"]

    # GET file info
    get_resp = client.get(f"/api/files/{file_id}/")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["id"] == file_id
    assert get_data["filename"] == "parcels.zip"
    assert get_data["status"] == "COMPLETED"
    assert get_data["feature_count"] == 2
    assert get_data["crs"] == "EPSG:4326"

    # GET measurements agree
    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    meas_data = meas_resp.json()
    assert meas_data["file_id"] == file_id
    assert meas_data["feature_count"] == 2
    assert len(meas_data["features"]) == 2


# ---------------------------------------------------------------------------
# 2. Measurement Types, Units & Geodesic Validation
# ---------------------------------------------------------------------------

def test_feature_measurement_types_and_units(client, chennai_kml: Path):
    with open(chennai_kml, "rb") as f:
        post_resp = client.post("/api/files/", files={"file": ("chennai.kml", f)})
    file_id = post_resp.json()["id"]

    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    features = meas_resp.json()["features"]

    # 1. Polygon Feature (Ripon Building Ground)
    poly = features[0]
    assert poly["geometry_type"] == "Polygon"
    assert poly["supported"] is True
    assert poly["area_sq_m"] > 0
    assert poly["area_hectares"] == round(poly["area_sq_m"] / 10000.0, 4)
    assert poly["length_m"] is None
    assert poly["length_km"] is None
    assert poly["measurement_crs"].startswith("EPSG:326")  # UTM 44N = EPSG:32644

    # 2. LineString Feature (Poonamallee High Road)
    line = features[1]
    assert line["geometry_type"] == "LineString"
    assert line["supported"] is True
    assert line["length_m"] > 0
    assert line["length_km"] == round(line["length_m"] / 1000.0, 4)
    assert line["area_sq_m"] is None
    assert line["area_hectares"] is None
    assert line["measurement_crs"].startswith("EPSG:326")

    # 3. Point Feature (Landmark)
    point = features[2]
    assert point["geometry_type"] == "Point"
    assert point["supported"] is True
    assert point["area_sq_m"] is None
    assert point["length_m"] is None
    assert point["note"] == "no measurement for points"


def test_measurements_match_pyproj_geod(client, chennai_kml: Path):
    with open(chennai_kml, "rb") as f:
        post_resp = client.post("/api/files/", files={"file": ("chennai.kml", f)})
    file_id = post_resp.json()["id"]

    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    features = meas_resp.json()["features"]

    geod = pyproj.Geod(ellps="WGS84")

    # Polygon area comparison
    poly_feature = features[0]
    poly_geom = shape(poly_feature["geometry"])
    geod_area, _ = geod.geometry_area_perimeter(poly_geom)
    rel_diff_area = abs(poly_feature["area_sq_m"] - abs(geod_area)) / abs(geod_area)
    assert rel_diff_area < 0.005  # Within 0.5%

    # Line length comparison
    line_feature = features[1]
    line_geom = shape(line_feature["geometry"])
    geod_length = geod.geometry_length(line_geom)
    rel_diff_length = abs(line_feature["length_m"] - geod_length) / geod_length
    assert rel_diff_length < 0.005  # Within 0.5%


# ---------------------------------------------------------------------------
# 3. CRS & Geometry Output Flags
# ---------------------------------------------------------------------------

def test_feature_crs_and_include_geometry_flag(client, chennai_kml: Path):
    with open(chennai_kml, "rb") as f:
        post_resp = client.post("/api/files/", files={"file": ("chennai.kml", f)})
    file_id = post_resp.json()["id"]

    # Default: geometry included, every feature carries CRS
    default_resp = client.get(f"/api/files/{file_id}/measurements/")
    for feat in default_resp.json()["features"]:
        assert feat["crs"] == "EPSG:4326"
        assert feat["geometry"] is not None
        assert isinstance(feat["geometry"], dict)

    # include_geometry=false: geometry is omitted (None)
    slim_resp = client.get(f"/api/files/{file_id}/measurements/?include_geometry=false")
    for feat in slim_resp.json()["features"]:
        assert feat["crs"] == "EPSG:4326"
        assert feat["geometry"] is None


# ---------------------------------------------------------------------------
# 4. Resilience: Partial Invalid Geometries Return 201
# ---------------------------------------------------------------------------

def test_resilient_processing_mixed_and_invalid_kml(client, mixed_bad_kml: Path):
    with open(mixed_bad_kml, "rb") as f:
        response = client.post("/api/files/", files={"file": ("mixed.kml", f)})

    assert response.status_code == 201
    file_id = response.json()["id"]

    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    features = meas_resp.json()["features"]
    assert len(features) == 4

    # 1. Valid Square Polygon: measured
    assert features[0]["supported"] is True
    assert features[0]["area_sq_m"] > 0

    # 2. GeometryCollection (MultiGeometry with mixed types): unsupported
    assert features[1]["supported"] is False
    assert "unsupported geometry type" in features[1]["note"]

    # 3. Bow-tie Polygon: unsupported invalid geometry
    assert features[2]["supported"] is False
    assert features[2]["note"].startswith("invalid geometry")

    # 4. Valid Coastal Line: measured
    assert features[3]["supported"] is True
    assert features[3]["length_m"] > 0


# ---------------------------------------------------------------------------
# 5. Error Responses and Cleanup Guarantees (No Leftovers)
# ---------------------------------------------------------------------------

def test_error_unsupported_file_type_415(client, test_db):
    upload_root = Path(config.UPLOAD_DIR)
    resp = client.post("/api/files/", files={"file": ("notes.txt", b"plain text", "text/plain")})
    assert resp.status_code == 415
    assert test_db.query(UploadedFile).count() == 0
    assert list(upload_root.iterdir()) == []


def test_error_corrupt_zip_422(client, test_db, tmp_path: Path):
    upload_root = Path(config.UPLOAD_DIR)
    fake_zip = tmp_path / "fake.zip"
    fake_zip.write_text("not a real zip archive")
    with open(fake_zip, "rb") as f:
        resp = client.post("/api/files/", files={"file": ("fake.zip", f)})
    assert resp.status_code == 422
    assert "not a valid zip archive" in resp.json()["detail"]
    assert test_db.query(UploadedFile).count() == 0
    assert list(upload_root.iterdir()) == []


def test_error_corrupt_kml_422(client, test_db, tmp_path: Path):
    upload_root = Path(config.UPLOAD_DIR)
    fake_kml = tmp_path / "fake.kml"
    fake_kml.write_text("random text not xml")
    with open(fake_kml, "rb") as f:
        resp = client.post("/api/files/", files={"file": ("fake.kml", f)})
    assert resp.status_code == 422
    assert test_db.query(UploadedFile).count() == 0
    assert list(upload_root.iterdir()) == []


def test_error_shapefile_missing_prj_422(client, test_db, make_shapefile_zip):
    upload_root = Path(config.UPLOAD_DIR)
    no_prj_zip = make_shapefile_zip("no_prj.zip", include_prj=False)
    with open(no_prj_zip, "rb") as f:
        resp = client.post("/api/files/", files={"file": ("no_prj.zip", f)})
    assert resp.status_code == 422
    assert "no CRS" in resp.json()["detail"]
    assert test_db.query(UploadedFile).count() == 0
    assert list(upload_root.iterdir()) == []


def test_error_zip_slip_422(client, test_db, tmp_path: Path):
    upload_root = Path(config.UPLOAD_DIR)
    slip_zip = tmp_path / "slip.zip"
    with zipfile.ZipFile(slip_zip, "w") as zf:
        zf.writestr("../evil.txt", "payload")
    with open(slip_zip, "rb") as f:
        resp = client.post("/api/files/", files={"file": ("slip.zip", f)})
    assert resp.status_code == 422
    assert "Zip-slip detected" in resp.json()["detail"]
    assert test_db.query(UploadedFile).count() == 0
    assert list(upload_root.iterdir()) == []


def test_error_empty_kml_422(client, test_db, tmp_path: Path):
    upload_root = Path(config.UPLOAD_DIR)
    empty_kml = tmp_path / "empty.kml"
    empty_kml.write_text("<kml><Document><Folder></Folder></Document></kml>")
    with open(empty_kml, "rb") as f:
        resp = client.post("/api/files/", files={"file": ("empty.kml", f)})
    assert resp.status_code == 422
    assert "contains no features" in resp.json()["detail"]
    assert test_db.query(UploadedFile).count() == 0
    assert list(upload_root.iterdir()) == []


def test_error_oversize_file_413(client, test_db, monkeypatch: pytest.MonkeyPatch):
    upload_root = Path(config.UPLOAD_DIR)
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 1)
    huge_data = b"0" * int(1.2 * 1024 * 1024)
    resp = client.post("/api/files/", files={"file": ("huge.zip", huge_data)})
    assert resp.status_code == 413
    assert test_db.query(UploadedFile).count() == 0
    assert list(upload_root.iterdir()) == []


def test_error_unknown_id_404(client):
    assert client.get("/api/files/unknown-uuid-1234/").status_code == 404
    assert client.get("/api/files/unknown-uuid-1234/measurements/").status_code == 404
