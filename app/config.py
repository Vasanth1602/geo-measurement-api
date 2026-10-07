"""
Application-wide configuration.
Other modules must do ``import app.config as config`` and read
``config.UPLOAD_DIR`` etc. at call time so tests can monkeypatch these names.
"""
import os

# Directory where uploaded files are stored (one sub-folder per upload id).
UPLOAD_DIR: str = os.environ.get("UPLOAD_DIR", "uploads")

# Upload size limits (plain int MB so tests can monkeypatch them easily).
MAX_UPLOAD_MB: int = int(os.environ.get("MAX_UPLOAD_MB", "50"))
MAX_UNZIPPED_MB: int = int(os.environ.get("MAX_UNZIPPED_MB", "200"))
