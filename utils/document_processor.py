"""
utils/document_processor.py — Extract and chunk text from uploaded documents.

Main entry-point: process(file_path, filename) → list[dict]
"""

from __future__ import annotations

import csv
import io
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["process", "chunk_text"]

# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 100,
) -> list[str]:
    """
    Split *text* into overlapping chunks of roughly *chunk_size* characters.

    Parameters
    ----------
    text : str
        Plain text to split.
    chunk_size : int
        Target character count per chunk.
    overlap : int
        Number of characters shared between consecutive chunks.

    Returns
    -------
    list[str]
        Non-empty chunks.
    """
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + chunk_size, length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start += chunk_size - overlap

    return chunks


# ---------------------------------------------------------------------------
# Format-specific extractors
# ---------------------------------------------------------------------------

def _extract_pdf(file_path: Path) -> str:
    try:
        import PyPDF2
        text_parts: list[str] = []
        with open(file_path, "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
        return "\n".join(text_parts)
    except Exception as exc:
        logger.error("PDF extraction failed for %s: %s", file_path, exc)
        return ""


def _extract_docx(file_path: Path) -> str:
    try:
        from docx import Document
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as exc:
        logger.error("DOCX extraction failed for %s: %s", file_path, exc)
        return ""


def _extract_xlsx(file_path: Path) -> str:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
        rows: list[str] = []
        for sheet in wb.worksheets:
            rows.append(f"[Sheet: {sheet.title}]")
            for row in sheet.iter_rows(values_only=True):
                row_text = "\t".join(
                    str(cell) if cell is not None else "" for cell in row
                )
                if row_text.strip():
                    rows.append(row_text)
        return "\n".join(rows)
    except Exception as exc:
        logger.error("XLSX extraction failed for %s: %s", file_path, exc)
        return ""


def _extract_csv(file_path: Path) -> str:
    try:
        with open(file_path, newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(fh)
            rows = ["\t".join(row) for row in reader]
        return "\n".join(rows)
    except Exception as exc:
        logger.error("CSV extraction failed for %s: %s", file_path, exc)
        return ""


def _extract_text(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.error("Text extraction failed for %s: %s", file_path, exc)
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process(
    file_path: str | Path,
    filename: str,
    chunk_size: int = 800,
    overlap: int = 100,
) -> list[dict[str, Any]]:
    """
    Extract text from *file_path* and return a list of chunk dicts.

    Parameters
    ----------
    file_path : str | Path
        Absolute path to the saved file on disk.
    filename : str
        Original filename (used to determine format).
    chunk_size : int
        Target characters per chunk.
    overlap : int
        Overlap between consecutive chunks.

    Returns
    -------
    list[dict]
        Each dict has keys: ``text``, ``chunk_index``, ``source``.
    """
    file_path = Path(file_path)
    ext = file_path.suffix.lstrip(".").lower()

    # Route to the correct extractor
    extractors = {
        "pdf": _extract_pdf,
        "docx": _extract_docx,
        "doc": _extract_docx,
        "xlsx": _extract_xlsx,
        "xls": _extract_xlsx,
        "csv": _extract_csv,
        "txt": _extract_text,
        "md": _extract_text,
    }

    extractor = extractors.get(ext, _extract_text)
    raw_text = extractor(file_path)

    if not raw_text.strip():
        logger.warning("No text extracted from %s", filename)
        return []

    chunks = chunk_text(raw_text, chunk_size=chunk_size, overlap=overlap)

    return [
        {
            "text": chunk,
            "chunk_index": i,
            "source": filename,
        }
        for i, chunk in enumerate(chunks)
    ]
