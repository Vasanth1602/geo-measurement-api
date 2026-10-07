"""
File ingestion services: format detection, safe upload streaming, and zip extraction.
Guards against zip-slip and zip-bomb attacks, and enforces upload/unzip size limits.
"""
from pathlib import Path
from typing import Any
import zipfile

import app.config as config
from app.services.errors import FileTooLarge, InvalidFileContent, UnsupportedFileType

CHUNK_SIZE = 1024 * 1024  # 1 MB streaming chunks


def detect_kind(filename: str) -> str:
    """
    Detect the geospatial file kind from the filename extension (case-insensitive).
    Returns 'kml' or 'shapefile_zip'.
    Raises UnsupportedFileType if not recognized.
    """
    if not filename:
        raise UnsupportedFileType("Filename cannot be empty")

    ext = Path(filename).suffix.lower()
    if ext == ".kml":
        return "kml"
    elif ext == ".zip":
        return "shapefile_zip"
    else:
        raise UnsupportedFileType(
            f"Unsupported file type '{ext or filename}'. Only .kml and .zip (shapefile) are supported."
        )


def save_upload(upload_file: Any, dest_dir: Path) -> Path:
    """
    Stream an uploaded file to disk in 1 MB chunks to prevent memory bloat.
    Saves to a fixed internal name ('upload.kml' or 'upload.zip') to prevent path injection.
    Raises FileTooLarge if total bytes exceed config.MAX_UPLOAD_MB and deletes the partial file.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = getattr(upload_file, "filename", "") or ""
    kind = detect_kind(filename)
    internal_name = "upload.kml" if kind == "kml" else "upload.zip"
    dest_path = dest_dir / internal_name

    max_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    total_bytes = 0

    reader = getattr(upload_file, "file", upload_file)
    try:
        with open(dest_path, "wb") as dst:
            while True:
                chunk = reader.read(CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise FileTooLarge(
                        f"Uploaded file exceeds maximum allowed size of {config.MAX_UPLOAD_MB} MB"
                    )
                dst.write(chunk)
    except Exception:
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        raise

    return dest_path


def safe_extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    """
    Safely extract a shapefile zip archive:
    1. Validates zip integrity.
    2. Prevents zip-slip by verifying resolved paths stay within dest_dir.
    3. Prevents zip bombs by counting actual extracted bytes against config.MAX_UNZIPPED_MB.
    4. Ensures exactly one .shp file exists in the archive.
    5. Ensures required companion files (.shx and .dbf) exist alongside the .shp file.
    Returns the Path to the extracted .shp file.
    """
    zip_path = Path(zip_path)
    dest_dir = Path(dest_dir).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    if not zipfile.is_zipfile(zip_path):
        raise InvalidFileContent(f"'{zip_path.name}' is not a valid zip archive")

    max_unzipped_bytes = config.MAX_UNZIPPED_MB * 1024 * 1024
    total_unzipped_bytes = 0

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # 1. Zip-slip pre-check for all members
            for member in zf.infolist():
                target_path = (dest_dir / member.filename).resolve()
                if not target_path.is_relative_to(dest_dir):
                    raise InvalidFileContent(
                        f"Zip-slip detected: member '{member.filename}' resolves outside target directory"
                    )

            # 2. Extract member-by-member tracking actual written bytes
            for member in zf.infolist():
                target_path = (dest_dir / member.filename).resolve()
                if member.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue

                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target_path, "wb") as dst:
                    while True:
                        chunk = src.read(64 * 1024)
                        if not chunk:
                            break
                        total_unzipped_bytes += len(chunk)
                        if total_unzipped_bytes > max_unzipped_bytes:
                            raise InvalidFileContent(
                                f"Uncompressed archive exceeds size limit of {config.MAX_UNZIPPED_MB} MB"
                            )
                        dst.write(chunk)
    except zipfile.BadZipFile as e:
        raise InvalidFileContent(f"Corrupt or invalid zip archive: {e}")

    # 3. Locate .shp files
    shp_files = [p for p in dest_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".shp"]
    if not shp_files:
        raise InvalidFileContent("Zip archive contains no .shp file")
    if len(shp_files) > 1:
        found_names = [p.name for p in shp_files]
        raise InvalidFileContent(
            f"Zip archive contains multiple .shp files ({', '.join(found_names)}). Exactly one is supported."
        )

    shp = shp_files[0]
    parent = shp.parent
    stem_lower = shp.stem.lower()

    # 4. Check companion files (.shx and .dbf)
    parent_files = {p.name.lower() for p in parent.iterdir() if p.is_file()}
    missing = []
    if f"{stem_lower}.shx" not in parent_files:
        missing.append(f"{shp.stem}.shx")
    if f"{stem_lower}.dbf" not in parent_files:
        missing.append(f"{shp.stem}.dbf")

    if missing:
        raise InvalidFileContent(
            f"Shapefile '{shp.name}' is missing required companion file(s): {', '.join(missing)}"
        )

    return shp
