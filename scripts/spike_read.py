"""
Spike: write a shapefile and a KML, read both back with geopandas.
Purpose: confirm that both drivers work in this environment *before* building
anything that depends on them. A failure here must be fixed first.
"""
import pathlib
import tempfile

import geopandas as gpd
from shapely.geometry import Polygon

# A simple unit square in EPSG:4326 (lon/lat degrees).
SQUARE = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])


def write_shapefile(folder: pathlib.Path) -> pathlib.Path:
    gdf = gpd.GeoDataFrame({"geometry": [SQUARE]}, crs="EPSG:4326")
    shp_path = folder / "test.shp"
    gdf.to_file(shp_path)
    return shp_path


def write_kml(folder: pathlib.Path) -> pathlib.Path:
    # Write KML by hand so this spike doesn't depend on geopandas KML *writing*,
    # which is not the production path. We only need to verify KML *reading*.
    kml_content = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>test</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              0,0,0 1,0,0 1,1,0 0,1,0 0,0,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>
"""
    kml_path = folder / "test.kml"
    kml_path.write_text(kml_content, encoding="utf-8")
    return kml_path


def read_and_report(label: str, path: pathlib.Path, **read_kwargs) -> None:
    try:
        gdf = gpd.read_file(path, **read_kwargs)
        for i, row in gdf.iterrows():
            print(f"[{label}] feature {i}: geom_type={row.geometry.geom_type}, crs={gdf.crs}")
    except Exception as exc:
        print(f"[{label}] READ FAILED: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)

        shp_path = write_shapefile(tmp_path)
        kml_path = write_kml(tmp_path)

        read_and_report("shapefile", shp_path)
        read_and_report("kml",       kml_path, driver="KML")
