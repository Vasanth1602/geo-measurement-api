"""
Generate realistic sample geospatial datasets for testing and verification:
- sample_data/sample.kml: Mixed feature KML (Polygon, LineString, Point) around Chennai.
- sample_data/sample_polygons.zip: ESRI Shapefile archive containing 2 polygons with EPSG:4326 .prj.
- sample_data/sample_lines.zip: ESRI Shapefile archive containing 2 linestrings with EPSG:4326 .prj.
"""
from pathlib import Path
import tempfile
import zipfile

import geopandas as gpd
from shapely.geometry import LineString, Polygon

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def make_kml(output_path: Path) -> None:
    """Generate sample.kml with a Polygon, LineString, and Point in Chennai (UTM Zone 44N)."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Chennai Landmarks Survey</name>
    <Folder>
      <name>Chennai Central Features</name>
      <Placemark>
        <name>Ripon Building Ground</name>
        <description>Colonial building headquarters of Greater Chennai Corporation</description>
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
        <description>Arterial road connecting central Chennai westwards</description>
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
        <name>Chennai Central Railway Station Landmark</name>
        <description>Major railway terminus in South India</description>
        <Point>
          <coordinates>80.2755,13.0827,0</coordinates>
        </Point>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    output_path.write_text(kml_content.strip(), encoding="utf-8")
    print(f"Created: {output_path}")


def make_polygons_zip(output_path: Path) -> None:
    """Generate sample_polygons.zip containing 2 polygons with EPSG:4326 CRS and attributes."""
    gdf = gpd.GeoDataFrame(
        {
            "name": ["Semmozhi Poonga Park", "Guindy National Park Enclosure"],
            "category": ["Botanical Garden", "Protected Forest"],
            "rating": [4.6, 4.4],
        },
        geometry=[
            Polygon([
                (80.2480, 13.0500),
                (80.2520, 13.0500),
                (80.2520, 13.0535),
                (80.2480, 13.0535),
                (80.2480, 13.0500),
            ]),
            Polygon([
                (80.2200, 13.0050),
                (80.2280, 13.0050),
                (80.2280, 13.0120),
                (80.2200, 13.0120),
                (80.2200, 13.0050),
            ]),
        ],
        crs="EPSG:4326",
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_shp = Path(tmp_dir) / "chennai_parks.shp"
        gdf.to_file(tmp_shp)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in Path(tmp_dir).iterdir():
                if p.is_file():
                    zf.write(p, arcname=p.name)

    print(f"Created: {output_path}")


def make_lines_zip(output_path: Path) -> None:
    """Generate sample_lines.zip containing 2 linestrings with EPSG:4326 CRS and attributes."""
    gdf = gpd.GeoDataFrame(
        {
            "name": ["Marina Beach Promenade", "Kamarajar Salai Coastal Drive"],
            "route_type": ["Walkway", "Highway"],
            "lanes": [0, 4],
        },
        geometry=[
            LineString([
                (80.2810, 13.0450),
                (80.2825, 13.0550),
                (80.2835, 13.0650),
            ]),
            LineString([
                (80.2790, 13.0400),
                (80.2805, 13.0500),
                (80.2818, 13.0600),
                (80.2825, 13.0700),
            ]),
        ],
        crs="EPSG:4326",
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_shp = Path(tmp_dir) / "chennai_routes.shp"
        gdf.to_file(tmp_shp)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in Path(tmp_dir).iterdir():
                if p.is_file():
                    zf.write(p, arcname=p.name)

    print(f"Created: {output_path}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    make_kml(OUTPUT_DIR / "sample.kml")
    make_polygons_zip(OUTPUT_DIR / "sample_polygons.zip")
    make_lines_zip(OUTPUT_DIR / "sample_lines.zip")
    print(f"All sample datasets generated successfully in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
