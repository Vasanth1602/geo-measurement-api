# Geo Measurement API: Build Guide (work offline with the Antigravity agent)

Goal: a clean, tested FastAPI service that accepts a KML or zipped shapefile, extracts features,
and returns correct area/length using a projected CRS. Lean on purpose: depth you can explain beats
extra features.

## How to use this guide
For every step: **Learn -> Build (agent prompt) -> Verify -> Explain-back -> Commit.**
1. Read the Learn section so you know what the agent is about to do.
2. Paste the prompt into the Antigravity agent (Claude Sonnet 4.6 if available, else any model).
3. Run the Verify commands yourself. Read the diff. Don't commit what you can't explain.
4. Write 2-3 sentences in your own words in `NOTES.md` (these become the README "Learning" section).
5. Commit with the suggested message.

If the agent errors: paste only the error back and say "fix only this error, change nothing else."
If the agent is rate-limited: switch model in the picker; the plan lives in PLAN.md so nothing is lost.
Windows tips: use the terminal inside Antigravity with the venv active. Prefer `python -m uvicorn ...` and
`python -m pytest`. If geopandas fails to install, use Python 3.11-3.13.

---

## Replace PLAN.md with this (the agent reads it every time)

```markdown
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
```

---

## Step 1b: finish Step 1 (the agent only created the skeleton)

**Missing:** requirements.txt, installed packages, `/health`, and the KML/shapefile spike.

**Learn**
- A *feature* is one item in a geo file: a geometry (the shape) plus properties (attributes like name).
- A *driver* is the reader for one format. We test KML and shapefile reading now so we don't discover a
  problem at step 5.
- `uvicorn` is the server that runs the FastAPI app. `/health` is the smallest endpoint, to prove it's wired up.

**Setup (PowerShell, in the project folder, once)**
```powershell
git init
py -m venv .venv
.venv\Scripts\Activate.ps1
```
If activation is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` then retry.

**Agent prompt**
```
Read PLAN.md. The folder skeleton already exists. Do ONLY these:
1. Create requirements.txt: fastapi, uvicorn[standard], sqlalchemy, python-multipart,
   geopandas, shapely, pyproj, pytest, httpx. Install into the active .venv.
2. In app/main.py add a FastAPI app with GET /health returning {"status":"ok"}.
3. Create scripts/spike_read.py that:
   - builds a tiny shapefile (one polygon, EPSG:4326) in a temp folder with geopandas,
   - builds a tiny KML (one polygon Placemark) by writing a hand-written KML string to a file
     (do not rely on writing KML through geopandas),
   - reads both back with geopandas.read_file (driver="KML" for the KML),
   - prints geometry type and CRS for each.
4. Run the spike and tell me exactly whether the KML read worked or failed, with the error if any.
Do not write business logic. Summarize and stop.
```

**Verify**
```powershell
python -m uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/health and http://127.0.0.1:8000/docs. Then `python scripts/spike_read.py`.
Expected: both read OK, geometry type Polygon, CRS EPSG:4326.
If the KML read fails, stop and bring me the error; everything downstream depends on it.

**Explain-back:** What is a feature? Why test the readers before building anything?
**Commit:** `chore: project skeleton, health endpoint and format-read spike`

---

## Step 2: crs.py (the heart of the assignment)

**Learn**
- EPSG:4326 coordinates are degrees. One degree of longitude is about 111 km at the equator and shrinks
  toward the poles, so area/length computed in degrees is wrong.
- A *projected CRS* uses meters. UTM splits the world into 60 zones, each 6 degrees wide. Inside one
  zone, distortion is small (suitable for survey-sized areas like mines and plots).
- Zone number: `int((lon + 180) // 6) + 1`, clamped to 1..60.
  EPSG code: `32600 + zone` in the northern hemisphere, `32700 + zone` in the southern.
- Limits to document: features spanning two zones lose some accuracy; UTM isn't defined near the poles
  (|lat| > 84), so those are flagged as unsupported.

**Agent prompt**
```
Read PLAN.md. Do ONLY step 2: implement app/services/crs.py with:
1. utm_epsg_for(lon: float, lat: float) -> int
   zone = int((lon + 180) // 6) + 1, clamped to 1..60; return 32600+zone if lat >= 0 else 32700+zone.
   Raise ValueError if abs(lat) > 84.
2. to_wgs84(geom, source_crs) -> shapely geometry. If source_crs is already EPSG:4326 return geom unchanged,
   otherwise reproject using pyproj.Transformer.from_crs(source_crs, 4326, always_xy=True)
   with shapely.ops.transform.
3. to_utm(geom_wgs84) -> tuple[shapely geometry, int]: take the centroid, pick the UTM EPSG with
   utm_epsg_for, reproject with always_xy=True, return (projected_geom, epsg).
Add short comments explaining WHY always_xy=True is used (axis order lon/lat vs lat/lon).
Then write tests/test_crs.py:
 - Chennai (80.27, 13.08) -> 32644
 - Sydney (151.2, -33.9) -> 32756
 - New York (-74.0, 40.7) -> 32618
 - lon=180 clamps to zone 60; lon=-180 gives zone 1
 - abs(lat) > 84 raises ValueError
 - to_utm on a small polygon near Chennai returns epsg 32644 and coordinates in a meter-sized range
   (x roughly 100000-900000).
Run pytest and report results. Summarize and stop.
```

**Verify:** `python -m pytest tests/test_crs.py -v` (all green).
**Explain-back:** Why can't we compute area in degrees? How is the UTM zone chosen?
**Commit:** `feat(crs): UTM zone selection and reprojection with tests`

---

## Step 3: measure.py (and prove it's correct)

**Learn**
- After projecting to UTM (meters), shapely's `.area` (m^2) and `.length` (m) are straightforward.
  MultiPolygon area and MultiLineString length are summed by shapely automatically; holes are subtracted.
- To *prove* it's right, cross-check against a different method: `pyproj.Geod(ellps="WGS84")` computes
  area/length directly on the ellipsoid (geodesic). The two should agree within a small tolerance.
  UTM has a scale factor of about 0.9996 to 1.0004 inside a zone, so use roughly 0.5% tolerance for small shapes.

**Agent prompt**
```
Read PLAN.md. Do ONLY step 3: implement app/services/measure.py.
Define a dataclass MeasurementResult with: supported: bool, area_sq_m: float | None,
length_m: float | None, measurement_crs: str | None, note: str | None.
Define measure_geometry(geom_wgs84) -> MeasurementResult (the input is already EPSG:4326):
 - None or empty geometry -> supported=False, note="empty geometry"
 - not geom.is_valid -> supported=False, note="invalid geometry"
 - Point/MultiPoint -> supported=True, no area/length, note="no measurement for points"
 - Polygon/MultiPolygon -> project with crs.to_utm, area_sq_m = projected.area
 - LineString/MultiLineString -> project with crs.to_utm, length_m = projected.length
 - any other type (GeometryCollection etc.) -> supported=False, note="unsupported geometry type: <type>"
 - if to_utm raises ValueError (polar) -> supported=False with the error as note
 - measurement_crs is the string "EPSG:<code>" when a projection was used.
Never let an exception escape: wrap in try/except and return supported=False with a note.
Write tests/test_measure.py:
 - polygon area vs pyproj.Geod(ellps="WGS84").geometry_area_perimeter (use abs of area), rel tolerance 0.5%
 - line length vs Geod.geometry_length, rel tolerance 0.5%
 - MultiPolygon area equals the sum of its parts (within tolerance)
 - polygon with a hole has smaller area than the same polygon without it
 - Point -> supported True, no measurement
 - empty polygon, self-intersecting "bow-tie" polygon, GeometryCollection -> supported False with a note
 - the same shape built near Chennai (northern) and in a southern/other-zone location returns the right
   measurement_crs for each
Run pytest and report. Summarize and stop.
```

**Verify:** `python -m pytest -v`
**Explain-back:** Why compare against Geod? What does `supported=False` protect us from?
**Commit:** `feat(measure): area and length via UTM with geodesic cross-check tests`

---

## Step 4: reading files (ingest.py, reader.py)

**Learn**
- Uploaded zips are untrusted. *Zip-slip*: an entry named `../../evil.py` could be written outside the
  target folder. We check every member's resolved path stays inside the extraction folder, and cap total
  uncompressed size to stop zip bombs.
- Never trust the client's filename for the path on disk. Save into `uploads/<uuid>/` and keep the
  original name only in the database.
- Pandas gives `NaN`/`Timestamp`/numpy types in attribute columns. These aren't JSON-serializable, so we
  clean properties before saving.
- A KML can contain several folders; GDAL exposes them as layers, so we read all of them.

**Agent prompt**
```
Read PLAN.md. Do ONLY step 4.
1. app/config.py: UPLOAD_DIR (default "uploads"), MAX_UPLOAD_MB=50, MAX_UNZIPPED_MB=200.
2. app/services/ingest.py:
   - detect_kind(filename) -> "kml" | "shapefile_zip", raise a custom UnsupportedFileType otherwise
     (match on lowercase extension .kml or .zip).
   - save_upload(upload_file, dest_dir) -> Path: stream to disk in chunks, enforce MAX_UPLOAD_MB
     (raise FileTooLarge). Use a fixed safe name (e.g. "upload.kml" / "upload.zip"), never the client name.
   - safe_extract_zip(zip_path, dest_dir) -> Path of the .shp file: reject if not a valid zip, reject any
     member whose resolved path escapes dest_dir (zip-slip), reject if total uncompressed size exceeds
     MAX_UNZIPPED_MB, require that .shp, .shx and .dbf exist (else raise InvalidFileContent with a message
     listing what is missing). The .shp may be inside a subfolder.
3. app/services/reader.py: read_features(path, kind) -> ReadResult(crs: str, features: list[RawFeature])
   with RawFeature(index: int, geometry, properties: dict).
   - kml: read every layer (pyogrio.list_layers, then geopandas.read_file(path, layer=name, driver="KML")),
     concatenate, CRS "EPSG:4326".
   - shapefile: geopandas.read_file(shp_path); if gdf.crs is None raise MissingCRS("no .prj / CRS found");
     crs string via gdf.crs.to_string().
   - Apply shapely.force_2d to every geometry to drop Z. Keep geometry in the file's original CRS.
   - Clean properties: NaN/None -> None, pandas Timestamp/datetime/date -> isoformat string,
     numpy scalars -> python scalars via .item().
   - index = position in the file (0-based).
   Define the custom exceptions in app/services/errors.py.
Write tests/conftest.py fixtures that build, in tmp_path: a valid KML (polygon, line, point), a valid zipped
shapefile (polygon + attribute), a shapefile zip missing its .prj, a zip containing a "../evil.txt" member,
and a zip missing .dbf. Write tests/test_reader.py covering: KML read gives 3 features with correct geometry
types and crs EPSG:4326; shapefile read gives correct crs and properties; missing .prj raises MissingCRS;
zip-slip and missing-.dbf zips raise InvalidFileContent; properties are JSON-serializable (json.dumps works).
Run pytest and report. Summarize and stop.
```

**Verify:** `python -m pytest -v`
**Explain-back:** What is zip-slip, and what two checks protect us? Why do we clean properties?
**Commit:** `feat(ingest): safe upload/zip handling and feature reader`

---

## Step 5: database, processing, endpoints

**Learn**
- *Models* are Python classes that map to database tables (SQLAlchemy). SQLite is a single file: zero setup.
- *Schemas* (Pydantic) define the exact JSON the API accepts/returns and drive the auto docs at `/docs`.
- The upload endpoint is a normal `def` (not `async def`) because geopandas is blocking; FastAPI runs it in
  a worker thread so it doesn't freeze the server.
- Processing is synchronous on purpose: files are small, it's simpler, and easy to explain. The `status`
  field leaves room for background workers (future scope).

**Agent prompt**
```
Read PLAN.md. Do ONLY step 5.
1. app/db.py: SQLAlchemy 2.0 engine for sqlite:///./app.db (connect_args check_same_thread=False),
   SessionLocal, Base, and a get_db dependency. Create tables on app startup (lifespan) in main.py.
2. app/models.py:
   - UploadedFile: id (uuid4 string, primary key), filename, kind, status
     ("PROCESSING" | "COMPLETED" | "FAILED"), feature_count, crs, error, created_at.
   - Feature: id, file_id (FK, indexed), index, geometry_type, geometry_geojson (text),
     properties (JSON), supported (bool), area_sq_m, length_m, measurement_crs, note.
3. app/services/processing.py: process_file(db, upload_record, path, kind):
   read_features -> for each feature: crs.to_wgs84(geom, file_crs), measure.measure_geometry,
   store a Feature row (geometry as GeoJSON via shapely.to_geojson). Wrap each feature in its own
   try/except so one failure only marks that feature unsupported with a note. Set the file's
   feature_count, crs and status=COMPLETED at the end.
4. app/schemas.py (Pydantic v2): FileOut (id, filename, feature_count, crs, status),
   FeatureMeasurementOut (index, geometry_type, supported, area_sq_m, area_hectares, length_m, length_km,
   measurement_crs, note, properties, geometry optional), MeasurementsOut (file_id, crs, feature_count, features).
5. app/api/files.py with prefix /api/files:
   - POST "/" (201): detect_kind, create UploadedFile(status PROCESSING), save under uploads/<id>/,
     process, return FileOut. Map errors: UnsupportedFileType -> 400, FileTooLarge -> 413,
     InvalidFileContent and MissingCRS -> 422 (with a clear message, and remove the saved folder and
     the record). Any unexpected exception -> record status FAILED with the error and return 500.
   - GET "/{id}/" -> FileOut, 404 if unknown.
   - GET "/{id}/measurements/" -> MeasurementsOut; include geometry only when ?include_geometry=true;
     404 if unknown.
   Register the router in main.py.
Do not add tests in this step. Run the server, upload tests/ fixtures manually with curl or /docs, and
report what you saw. Summarize and stop.
```

**Verify:** `python -m uvicorn app.main:app --reload`, open `/docs`, use "Try it out" to upload a KML and a
zipped shapefile (generate samples with the fixtures or the spike script), then call the two GET endpoints.
Check one area by eye against a known size.
**Explain-back:** What happens, in order, when a file is uploaded? Why a plain `def` endpoint?
**Commit:** `feat(api): database models, processing pipeline and file endpoints`

---

## Step 6: API tests

**Agent prompt**
```
Read PLAN.md. Do ONLY step 6: write tests/test_api.py using FastAPI TestClient and a temporary SQLite
database and temporary upload dir (override get_db and the upload dir in the test setup so tests never
touch real data). Cover:
 - upload valid KML -> 201, then GET file -> COMPLETED with feature_count 3 and crs EPSG:4326
 - upload valid zipped shapefile -> 201, crs matches the file
 - GET measurements for the KML: polygon has area_sq_m > 0 and measurement_crs starts with "EPSG:326";
   line has length_m > 0; point has supported True and no area/length
 - include_geometry=true returns a geometry field, default does not
 - upload a .txt -> 400
 - upload a shapefile zip without .prj -> 422 with a helpful message
 - upload a zip-slip zip -> 422
 - upload a file larger than the limit (monkeypatch MAX_UPLOAD_MB to a tiny number) -> 413
 - unknown id -> 404 on both GET endpoints
 - a file with an invalid (bow-tie) polygon still returns 201 and that feature has supported False
   while the valid features are still measured
Run the full suite and report. Summarize and stop.
```

**Verify:** `python -m pytest -v` (everything green). Then add ruff if you like: `pip install ruff`, `ruff check .`
**Explain-back:** Which test would catch a regression to degree-based area? (Answer: the Geod cross-check.)
**Commit:** `test(api): end-to-end tests for upload, measurements and error handling`

---

## Step 7: README, samples, publish

**Agent prompt**
```
Read PLAN.md and NOTES.md. Do ONLY step 7:
1. Create sample_data/ with a small valid sample.kml (a polygon, a line, a point) and sample_shapefile.zip
   (generated by a script scripts/make_samples.py, which you also create).
2. Write README.md with these sections: Overview; Setup (Windows and Mac/Linux commands, venv, install,
   run uvicorn, open /docs); Running tests; API (each endpoint with a curl example and a real example
   response from sample_data); Architecture (app structure, file-processing flow, measurement flow, CRS
   handling); Design Decisions (each with the alternative considered); Limitations; Learning; Future Scope.
   For Learning, use the sentences from NOTES.md verbatim-ish (they are the author's own words).
Design decisions to document:
 - FastAPI over Django: lighter, typed, auto docs, enough for 3 endpoints
 - Synchronous processing: small files, simpler; alternative is a task queue (Celery/RQ) for large files
 - SQLite: zero setup; alternative Postgres/PostGIS for production and spatial queries
 - UTM zone per feature centroid: accurate for survey-sized features; alternatives: one equal-area CRS
   for the whole file, or direct geodesic math with pyproj.Geod (used here as a test cross-check)
 - Invalid geometry is flagged, not repaired; alternative is shapely.make_valid
 - include_geometry is opt-in to keep responses small
Limitations to state: features spanning two UTM zones lose some accuracy; polar latitudes unsupported;
no pagination; no auth; files stay on local disk.
Future scope: background workers, pagination, auth, PostGIS, geometry repair, GeoJSON/GeoPackage support,
volume/elevation from DEMs (links to what Aereo does), Docker + CI.
Summarize and stop.
```

**Publish**
```powershell
git add .
git commit -m "docs: README, sample data and generator script"
git branch -M main
git remote add origin https://github.com/<your-username>/geo-measurement-api.git
git push -u origin main
```
Before submitting: clone your repo into a fresh folder and follow your own README from scratch. If it
doesn't run cleanly, fix the README.

---

## Optional step 8 (only if time): Docker + CI
```
Add a Dockerfile (python:3.12-slim, install requirements, run uvicorn on 0.0.0.0:8000) and a GitHub
Actions workflow .github/workflows/ci.yml that installs requirements and runs pytest on push.
Add a README "Run with Docker" section. Do not change application code.
```
Check that the image really builds and runs before claiming it in the README (geopandas wheels on slim images
sometimes need extra system libraries; if the build fails, skip this step rather than ship a broken Dockerfile).

---

## What the reviewer sees (checklist)
- [ ] Area/length never computed in degrees; `measurement_crs` visible in responses
- [ ] Tests exist and pass, including the Geod cross-check
- [ ] Bad input returns clear 4xx errors; one bad feature doesn't break the file
- [ ] Safe zip handling, size limit, no client filenames on disk
- [ ] Small commits with meaningful messages (one per step)
- [ ] README: setup, API examples, architecture, design decisions, limitations, learning, future scope
- [ ] You can explain every file and modify it live

## Likely interview questions (practice answering out loud)
1. Why project to UTM before measuring? What goes wrong in EPSG:4326?
2. How do you choose the UTM zone? What if a feature crosses two zones?
3. How do you know your area numbers are right? (Geod cross-check, tolerance reasoning)
4. What happens if a shapefile has no .prj? Why 422 and not a guess?
5. What is zip-slip and how do you prevent it?
6. Why synchronous processing? How would you change it for 2 GB files? (queue + workers + status polling)
7. Why SQLite? What changes with Postgres/PostGIS?
8. A new requirement: also return the perimeter of polygons. Which files change? (measure.py, schemas.py,
   models.py, tests)
9. How would you add pagination to /measurements/?
10. What would you do about invalid geometries instead of skipping them?

## Submission form
Name, email, public repo URL, select "Geospatial File Measurement API", resume link. Submit only after the
fresh-clone test passes.