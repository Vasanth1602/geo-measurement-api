# NOTES.md — Learning log (my own words)

These sentences are written as I build each step. Step 7 uses them directly
in the README "Learning" section.

---

## Step 1 — Skeleton, health endpoint, format-read spike

A *feature* is one item inside a geo file: a shape (geometry) plus a set of
named attributes (properties), like a row in a table that also has a location.
We tested both the KML and shapefile readers before writing any business logic
because if a driver is missing or broken, every step that depends on it would
fail silently or with a confusing error — better to find that out on line 1
than on line 500.

`uvicorn` is the ASGI server that actually runs the FastAPI app; FastAPI
itself just defines the routes and validation, it needs a server to listen for
requests.

**Environment note:** `float | None` union syntax requires Python 3.10+.
On Python 3.9 (what this machine runs) you must use `Optional[float]` from
`typing`. Watch for this in every file that uses type hints.

---

## Step 2 — CRS: UTM zone selection and reprojection

Geographic coordinates (EPSG:4326) are in degrees, not meters. One degree of
longitude is about 111 km at the equator but shrinks toward the poles, so any
area or length computed directly in degrees is wrong — the same 1° × 1° box
covers a very different real-world area depending on latitude.

UTM splits the world into 60 zones, each 6° of longitude wide, and uses
meters as its unit. The scale factor is 0.9996 on a zone's central meridian
and grows to about 1.001 at the zone edge, so lengths can be off by up to
roughly 0.1% and areas by up to roughly 0.2%. A test polygon straddling a zone
boundary was off by +0.18% in area compared with the geodesic result, well
inside the 0.5% tolerance used in the tests. That is accurate enough for the
survey-scale features this API handles, and it is a documented limitation for
features that span two zones.

`always_xy=True` is required when using pyproj because some CRSes define
their axis order as (latitude, longitude) — the opposite of what most people
expect. Forcing `always_xy=True` means our code always passes (longitude,
latitude) = (x, y) and always gets back (easting, northing), regardless of
what the CRS authority says.

---

## Step 3 — Measurement: area and length via UTM, geodesic cross-check

After projecting to UTM (meters), shapely's `.area` gives m² and `.length`
gives meters directly. MultiPolygon holes are subtracted automatically, and
MultiLineString segments are summed — shapely handles both correctly with no
extra code.

We cross-check results against `pyproj.Geod`, which computes area and length
directly on the WGS-84 ellipsoid without any projection. If the two methods
agree within 0.5%, we can be confident the UTM projection is being applied
correctly. This cross-check is the test that would catch a regression if
someone accidentally computed area in degrees.

Returning `supported=False` (rather than raising an exception) for invalid or
unsupported geometries means one bad feature in a file never prevents the
rest from being measured — the caller gets a result for every feature, with a
clear note explaining what went wrong.

---

## Step 3b — Hardening crs.py and measure.py (fixes and extra tests)

**Longitude validation added to `utm_epsg_for`.**
Before this fix, passing `lon=190` silently produced zone 60 (clamped) instead
of raising an error. That is wrong: 190° is not a valid WGS-84 longitude.
We now raise `ValueError` containing `"longitude"` for any value outside
`-180..180`. The southern UTM boundary was also corrected from `|lat| > 84`
to the precise limits: `lat > 84` (north) or `lat < -80` (south). The error
message contains `"polar"` in both cases so callers can match on it.

**`from pyproj import CRS` moved to module level.**
It was previously imported inside the function body of `to_wgs84`, which works
but hides the dependency and makes the import run on every call. Moving it to
the top makes the dependency visible and the code faster.

**`explain_validity` added to invalid-geometry notes.**
The old note was just `"invalid geometry"` — not helpful. Shapely's
`explain_validity()` returns a human-readable reason such as
`"Self-intersection [0 0]"`. The note is now
`f"invalid geometry: {explain_validity(geom)}"` so a user who uploads a
self-intersecting polygon gets a meaningful error they can act on.

**Degrees-trap test.**
A 0.01° × 0.01° square has a raw shapely area of `0.0001` (in degree units —
meaningless). After UTM projection the same square near Chennai is
~1,200,000 m². This test exists specifically to catch any future regression
where someone accidentally skips the reprojection step.

**Zone-boundary test.**
A polygon straddling the lon=84 zone boundary (zone 44 / 45 boundary) is
measured against `pyproj.Geod` and must agree within 0.5%. The centroid falls
inside zone 44, so the whole polygon is measured in EPSG:32644. The test
confirms the documented distortion stays inside tolerance.

## Step 4 — Ingestion, Safe Zip Extraction, and File Reading

### Configuration & Errors (`app/config.py`, `app/services/errors.py`)
- Config parameters `UPLOAD_DIR`, `MAX_UPLOAD_MB` (50 MB), and `MAX_UNZIPPED_MB` (200 MB) are imported at the module level (`import app.config as config`) so tests can easily monkeypatch them at runtime.
- Custom exception hierarchy:
  - `UnsupportedFileType`: Raised for non-.kml and non-.zip files (maps to HTTP 415).
  - `FileTooLarge`: Raised when upload streaming exceeds `MAX_UPLOAD_MB` (maps to HTTP 413).
  - `InvalidFileContent`: Raised for corrupt archives, zip-slip attempts, uncompressed size bombs, missing companion files (.shx, .dbf), multiple shapefiles, or empty feature collections (maps to HTTP 422).
  - `MissingCRS`: Raised when a shapefile lacks a CRS or `.prj` file (maps to HTTP 422).

### Safe Ingestion & Extraction (`app/services/ingest.py`)
- `detect_kind(filename)`: Case-insensitively inspects the file extension to distinguish `.kml` and `.zip` files, rejecting all other formats.
- `save_upload(upload_file, dest_dir)`: Streams uploads in 1 MB chunks to prevent memory exhaustion, tracks byte count against `MAX_UPLOAD_MB`, deletes partial files if exceeded, and saves files to a fixed internal name (`upload.kml` or `upload.zip`) to prevent client filename injection.
- `safe_extract_zip(zip_path, dest_dir)`:
  1. Validates zip file integrity.
  2. Pre-validates member paths using `Path.is_relative_to(dest_dir.resolve())` to prevent zip-slip directory traversal vulnerabilities.
  3. Extracts member-by-member tracking actual extracted bytes against `MAX_UNZIPPED_MB` to prevent zip bomb attacks.
  4. Enforces that exactly one `.shp` file exists in the archive (case-insensitive search).
  5. Verifies required companion files (`.shx` and `.dbf`) exist alongside the shapefile.

### Feature Reading & Sanitization (`app/services/reader.py`)
- `read_features(path, kind)`:
  - **KML Multi-Layer Handling:** Uses `pyogrio.list_layers` to discover every Folder/layer, reads each with GeoPandas, concatenates them into a unified dataset with continuous 0-indexed IDs, and assigns `EPSG:4326`.
  - **Shapefile Reading:** Reads via GeoPandas, validates that `df.crs` is present, and resolves the CRS string (e.g. `EPSG:4326`).
  - **Z-Dimension Stripping:** Calls `shapely.force_2d` to ensure all coordinates are 2D planar geometries.
  - **Column Cleaning:** Drops KML styling/camera columns (`altitudeMode`, `tessellate`, `extrude`, `visibility`, `drawOrder`, `icon`, `timestamp`, `begin`, `end`) and any column that is entirely null, while preserving core attributes like `Name`.
  - **JSON Property Sanitization:** Recursively sanitizes row attributes to guarantee clean `json.dumps()` serialization: converts `datetime.date`/`datetime.datetime`/`pd.Timestamp` to ISO strings, floats/np.float NaN and INF to `None` (JSON `null`), and numpy numeric primitives to Python `int`/`float`.
  - **Empty Feature Guard:** Explicitly raises `InvalidFileContent` if the file has 0 placemarks or features.

---

<!-- Steps 5–7 notes will be added here as they are completed. -->