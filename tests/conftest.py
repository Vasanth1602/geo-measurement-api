"""
Shared test fixtures generating KML files and Shapefile zip archives in pytest tmp_path.
"""
import datetime
from pathlib import Path
import zipfile

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, Polygon


@pytest.fixture
def kml_single_folder(tmp_path: Path) -> Path:
    """KML with Polygon, LineString, and Point in a single folder with Z coordinates and styling."""
    content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Mixed Layer</name>
      <Placemark>
        <name>Sample Polygon</name>
        <altitudeMode>clampToGround</altitudeMode>
        <tessellate>1</tessellate>
        <Polygon>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                0,0,10 10,0,10 10,10,10 0,10,10 0,0,10
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>
        </Polygon>
      </Placemark>
      <Placemark>
        <name>Sample Line</name>
        <visibility>1</visibility>
        <LineString>
          <coordinates>
            0,0,5 5,5,5 10,10,5
          </coordinates>
        </LineString>
      </Placemark>
      <Placemark>
        <name>Sample Point</name>
        <Point>
          <coordinates>
            5,5,15
          </coordinates>
        </Point>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    file_path = tmp_path / "single_folder.kml"
    file_path.write_text(content, encoding="utf-8")
    return file_path


@pytest.fixture
def kml_two_folders(tmp_path: Path) -> Path:
    """KML with two Folders (layers) each having placemarks."""
    content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Folder 1</name>
      <Placemark>
        <name>Feature F1-A</name>
        <Point><coordinates>1,1,0</coordinates></Point>
      </Placemark>
      <Placemark>
        <name>Feature F1-B</name>
        <Point><coordinates>2,2,0</coordinates></Point>
      </Placemark>
    </Folder>
    <Folder>
      <name>Folder 2</name>
      <Placemark>
        <name>Feature F2-A</name>
        <Point><coordinates>3,3,0</coordinates></Point>
      </Placemark>
      <Placemark>
        <name>Feature F2-B</name>
        <Point><coordinates>4,4,0</coordinates></Point>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    file_path = tmp_path / "two_folders.kml"
    file_path.write_text(content, encoding="utf-8")
    return file_path


@pytest.fixture
def kml_empty(tmp_path: Path) -> Path:
    """Valid KML structure containing no Placemarks."""
    content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Empty Folder</name>
    </Folder>
  </Document>
</kml>
"""
    file_path = tmp_path / "empty.kml"
    file_path.write_text(content, encoding="utf-8")
    return file_path


@pytest.fixture
def make_shapefile_zip(tmp_path: Path):
    """
    Factory fixture to build custom shapefile zips with various configurations:
    - subfolder placement
    - missing companion files (.prj, .dbf, .shx)
    - multiple shapefiles
    - custom properties including dates and NaN
    """
    def _create(
        zip_filename: str = "shapefile.zip",
        subfolder: str = "",
        include_prj: bool = True,
        include_dbf: bool = True,
        include_shx: bool = True,
        extra_shp: bool = False,
        crs: str = "EPSG:4326",
    ) -> Path:
        build_dir = tmp_path / f"build_{zip_filename.replace('.', '_')}"
        build_dir.mkdir(parents=True, exist_ok=True)

        gdf = gpd.GeoDataFrame(
            {
                "Name": ["Area 1", "Area 2"],
                "created": [datetime.date(2025, 1, 15), datetime.date(2025, 2, 20)],
                "score": [98.5, float("nan")],
                "all_null": [None, None],
            },
            geometry=[
                Polygon([(77.5, 12.9), (77.6, 12.9), (77.6, 13.0), (77.5, 13.0), (77.5, 12.9)]),
                Polygon([(78.0, 13.0), (78.1, 13.0), (78.1, 13.1), (78.0, 13.1), (78.0, 13.0)]),
            ],
            crs=crs,
        )

        shp_stem = "parcels"
        shp_path = build_dir / f"{shp_stem}.shp"
        gdf.to_file(shp_path)

        if extra_shp:
            extra_gdf = gpd.GeoDataFrame(
                {"Name": ["Extra"]},
                geometry=[Point(77.5, 12.9)],
                crs=crs,
            )
            extra_gdf.to_file(build_dir / "extra.shp")

        zip_dest = tmp_path / zip_filename
        with zipfile.ZipFile(zip_dest, "w") as zf:
            for p in build_dir.iterdir():
                if not p.is_file():
                    continue
                ext = p.suffix.lower()
                if ext == ".prj" and not include_prj:
                    continue
                if ext == ".dbf" and not include_dbf:
                    continue
                if ext == ".shx" and not include_shx:
                    continue

                arcname = f"{subfolder}/{p.name}" if subfolder else p.name
                zf.write(p, arcname=arcname)

        return zip_dest

    return _create
