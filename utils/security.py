"""
utils/security.py — Security helpers for DocuMind.

All functions are exported via __all__.
"""

from __future__ import annotations

import hmac
import hashlib
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional

__all__ = [
    "validate_file_content",
    "safe_path",
    "validate_api_key",
    "sanitize_filename",
    "is_allowed_extension",
]

# ---------------------------------------------------------------------------
# Allowed file extensions (lower-case, no dot)
# ---------------------------------------------------------------------------
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {"pdf", "txt", "md", "docx", "doc", "xlsx", "xls", "csv"}
)

# ---------------------------------------------------------------------------
# Magic bytes for basic file-type validation
# ---------------------------------------------------------------------------
_MAGIC: dict[str, bytes] = {
    "pdf": b"%PDF",
    "docx": b"PK\x03\x04",   # OOXML (zip)
    "xlsx": b"PK\x03\x04",
    "doc": b"\xd0\xcf\x11\xe0",
    "xls": b"\xd0\xcf\x11\xe0",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_file_content(file_bytes: bytes, filename: str) -> tuple[bool, str]:
    """
    Validate uploaded file content.

    Parameters
    ----------
    file_bytes : bytes
        Raw bytes of the uploaded file (or at least the first 512 bytes).
    filename : str
        Original filename (used to derive expected extension).

    Returns
    -------
    (ok: bool, message: str)
        ok=True when the file passes all checks.
    """
    if not file_bytes:
        return False, "File is empty."

    ext = Path(filename).suffix.lstrip(".").lower()
    if not ext:
        return False, "File has no extension."

    if ext not in _ALLOWED_EXTENSIONS:
        return False, f"Extension '.{ext}' is not allowed."

    # Magic-byte check for binary formats
    if ext in _MAGIC:
        expected = _MAGIC[ext]
        if not file_bytes[:len(expected)].startswith(expected):
            return False, f"File content does not match expected format for .{ext}."

    # Basic size check (must have at least a few bytes of content)
    if len(file_bytes) < 4:
        return False, "File is too small to be valid."

    return True, "OK"


def safe_path(base_dir: str | Path, filename: str) -> Path:
    """
    Return a safe absolute path for *filename* inside *base_dir*.

    Raises
    ------
    ValueError
        If the resolved path escapes *base_dir* (path traversal attempt).

    Parameters
    ----------
    base_dir : str | Path
        The directory that must contain the final path.
    filename : str
        The filename (NOT a relative path with subdirectories).
    """
    base = Path(base_dir).resolve()
    # Sanitize first so we don't accidentally allow ".." components
    clean_name = sanitize_filename(filename)
    target = (base / clean_name).resolve()

    # Ensure the target is inside base_dir
    try:
        target.relative_to(base)
    except ValueError:
        raise ValueError(
            f"Path traversal detected: '{filename}' escapes base directory."
        )

    return target


def validate_api_key(provided_key: str, valid_keys: list[str]) -> bool:
    """
    Check *provided_key* against *valid_keys* using constant-time comparison
    to prevent timing attacks.

    Parameters
    ----------
    provided_key : str
        The key sent by the client.
    valid_keys : list[str]
        The list of accepted API keys loaded from config / env.

    Returns
    -------
    bool
        True if *provided_key* matches any entry in *valid_keys*.
    """
    if not provided_key or not valid_keys:
        return False

    key_bytes = provided_key.encode("utf-8")

    for valid in valid_keys:
        if hmac.compare_digest(key_bytes, valid.encode("utf-8")):
            return True

    return False


def sanitize_filename(filename: str) -> str:
    """
    Return a filesystem-safe version of *filename*.

    - Strips directory separators and leading dots.
    - Normalises unicode to ASCII where possible.
    - Collapses whitespace / special characters to underscores.
    - Preserves the original file extension.
    """
    # Normalise unicode
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("ascii", "ignore").decode("ascii")

    # Keep only safe characters
    filename = re.sub(r"[^\w\s\-.]", "_", filename)
    filename = re.sub(r"[\s]+", "_", filename).strip("_.")

    # Never allow empty names
    if not filename:
        filename = "upload"

    return filename


def is_allowed_extension(filename: str) -> bool:
    """Return True if *filename* has an allowed extension."""
    ext = Path(filename).suffix.lstrip(".").lower()
    return ext in _ALLOWED_EXTENSIONS
