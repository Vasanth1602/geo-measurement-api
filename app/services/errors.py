"""
Custom exceptions for the Geo Measurement API.
Each maps to a specific HTTP status code in the API layer.
"""


class UnsupportedFileType(Exception):
    """File extension is not .kml or .zip  ->  HTTP 415."""


class FileTooLarge(Exception):
    """Upload exceeds MAX_UPLOAD_MB  ->  HTTP 413."""


class InvalidFileContent(Exception):
    """File is syntactically wrong or structurally incomplete  ->  HTTP 422."""


class MissingCRS(Exception):
    """Shapefile has no .prj / CRS  ->  HTTP 422."""
