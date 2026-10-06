# Geo Measurement API: Plan

FastAPI + SQLAlchemy 2 (SQLite). geopandas (pyogrio), shapely 2, pyproj.
Accepts .kml or .zip (shapefile). Polygon -> area, LineString -> length, Point -> none.

Endpoints:
- POST /api/files/                      upload + process (synchronous), returns 201
- GET  /api/files/{id}/                 id, filename, feature_count, crs, status
- GET  /api/files/{id}/measurements/    per-feature results (?include_geometry=true optional)

## Core rules
- Never measure in degrees. Convert geometry to EPSG:4326, pick the UTM zone from the feature
  centroid, reproject, then measure. Return `measurement_crs` per feature.
- KML is EPSG:4326. Shapefile CRS comes from .prj; if missing -> 422 with a clear message.
- One bad feature must never crash the request: flag it (supported=false + note) and continue.
- MultiPolygon/MultiLineString: shapely sums parts. GeometryCollection: unsupported.
  Drop Z values. Empty or invalid geometry: unsupported with a note. Points: no measurement.
- Security: never use the client filename on disk (use a uuid folder), safe zip extraction
  (zip-slip + total uncompressed size limit), upload size limit (50 MB).
- Known validation errors return 4xx and save nothing (400 wrong type, 413 too large,
  422 bad content/no CRS). Unexpected errors save the file with status FAILED.

## Structure
app/{main,config,db,models,schemas}.py
app/api/files.py
app/services/{ingest,reader,crs,measure,processing}.py
tests/{conftest,test_crs,test_measure,test_reader,test_api}.py
scripts/spike_read.py, NOTES.md, README.md, requirements.txt

## Rules for the AI agent
- Do only the step I ask for. No extra features, no extra dependencies.
- Keep code simple and readable. Comments explain WHY, not what.
- After each step: summarize the change in plain language, then stop.