"""
Tests for geospatial feature extraction and parsing in app/services/reader.py.
"""
import json
from pathlib import Path

import pytest
from shapely.geometry import LineString, Point, Polygon

from app.services.errors import InvalidFileContent, MissingCRS
from app.services.ingest import safe_extract_zip
from app.services.reader import read_features


def test_read_kml_single_folder(kml_single_folder: Path):
    result = read_features(kml_single_folder, kind="kml")

    assert result.crs == "EPSG:4326"
    assert len(result.features) == 3

    geom_types = [f.geometry.geom_type for f in result.features]
    assert geom_types == ["Polygon", "LineString", "Point"]

    # Continuous indexing
    assert [f.index for f in result.features] == [0, 1, 2]


def test_read_kml_two_folders(kml_two_folders: Path):
    result = read_features(kml_two_folders, kind="kml")

    assert result.crs == "EPSG:4326"
    # Folder 1 has 2 placemarks, Folder 2 has 2 placemarks
    assert len(result.features) == 4
    assert [f.index for f in result.features] == [0, 1, 2, 3]

    names = [f.properties.get("Name") for f in result.features]
    assert names == ["Feature F1-A", "Feature F1-B", "Feature F2-A", "Feature F2-B"]


def test_read_kml_styling_and_z_dropped(kml_single_folder: Path):
    result = read_features(kml_single_folder, kind="kml")

    for f in result.features:
        # Z coordinates must be stripped
        assert not f.geometry.has_z
        # Styling columns must be dropped
        for style_key in ["altitudeMode", "tessellate", "visibility"]:
            assert style_key not in f.properties
            assert style_key.lower() not in f.properties

    # Name column is preserved
    poly_feature = result.features[0]
    assert poly_feature.properties.get("Name") == "Sample Polygon"


def test_read_kml_empty(kml_empty: Path):
    with pytest.raises(InvalidFileContent) as exc_info:
        read_features(kml_empty, kind="kml")

    assert "contains no features" in str(exc_info.value)


def test_read_kml_text_file(tmp_path: Path):
    fake_kml = tmp_path / "corrupt.kml"
    fake_kml.write_text("Hello this is not valid XML or KML content.")

    with pytest.raises(InvalidFileContent):
        read_features(fake_kml, kind="kml")


def test_read_shapefile_valid(make_shapefile_zip, tmp_path: Path):
    zip_path = make_shapefile_zip("valid.zip")
    extract_dir = tmp_path / "ext_valid"
    shp_path = safe_extract_zip(zip_path, extract_dir)

    result = read_features(shp_path, kind="shapefile")
    assert result.crs == "EPSG:4326"
    assert len(result.features) == 2
    assert [f.index for f in result.features] == [0, 1]

    # Check property types and JSON serialization
    for f in result.features:
        # Ensure all properties serialize cleanly to JSON
        serialized = json.dumps(f.properties)
        deserialized = json.loads(serialized)
        assert isinstance(deserialized, dict)
        # All null column dropped
        assert "all_null" not in f.properties

    # Check date serialized to ISO string
    feat1 = result.features[0]
    assert feat1.properties["created"] == "2025-01-15"
    assert feat1.properties["score"] == 98.5

    # Check NaN converted to None -> JSON null
    feat2 = result.features[1]
    assert feat2.properties["created"] == "2025-02-20"
    assert feat2.properties["score"] is None


def test_read_shapefile_in_subfolder(make_shapefile_zip, tmp_path: Path):
    zip_path = make_shapefile_zip("nested.zip", subfolder="nested/inner")
    extract_dir = tmp_path / "ext_nested"
    shp_path = safe_extract_zip(zip_path, extract_dir)

    result = read_features(shp_path, kind="shapefile")
    assert result.crs == "EPSG:4326"
    assert len(result.features) == 2


def test_read_shapefile_missing_prj(make_shapefile_zip, tmp_path: Path):
    zip_path = make_shapefile_zip("no_prj.zip", include_prj=False)
    extract_dir = tmp_path / "ext_no_prj"
    shp_path = safe_extract_zip(zip_path, extract_dir)

    with pytest.raises(MissingCRS) as exc_info:
        read_features(shp_path, kind="shapefile")

    assert "no CRS" in str(exc_info.value)
