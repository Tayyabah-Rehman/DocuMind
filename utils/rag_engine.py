"""
utils/rag_engine.py — Embedding, storage, and retrieval using ChromaDB.

Key design decisions
--------------------
- Collection names use the first 12 hex chars of the file's MD5 hash
  (prefixed with "doc_") → always 3–63 chars, ChromaDB-safe.
- Duplicate uploads are detected by checking whether the collection already
  exists, so we skip re-embedding silently.
- The embedding model is loaded ONCE at module import time (or lazily on
  first call) — callers must pre-download it via setup.bat / setup.sh.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singletons (lazy-loaded)
# ---------------------------------------------------------------------------
_embedding_model: Optional[SentenceTransformer] = None
_chroma_client: Optional[chromadb.PersistentClient] = None


def _get_embedding_model(model_name: str = "paraphrase-MiniLM-L3-v2") -> SentenceTransformer:
    """Return (and cache) the sentence-transformer model."""
    global _embedding_model
    if _embedding_model is None:
        logger.info("Loading embedding model: %s", model_name)
        _embedding_model = SentenceTransformer(model_name)
        logger.info("Embedding model loaded.")
    return _embedding_model


def _get_chroma_client(persist_dir: str | Path) -> chromadb.PersistentClient:
    """Return (and cache) the ChromaDB persistent client."""
    global _chroma_client
    if _chroma_client is None:
        logger.info("Initialising ChromaDB at: %s", persist_dir)
        _chroma_client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        logger.info("ChromaDB ready.")
    return _chroma_client


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_collection_name(file_hash: str) -> str:
    """
    Return a ChromaDB-safe collection name.

    ChromaDB requirements:
    - 3–63 characters
    - Contains only a-z, A-Z, 0-9, _, -
    - Starts and ends with an alphanumeric character
    """
    # file_hash[:12] gives 12 hex chars → "doc_" + 12 chars = 16 chars total ✓
    return f"doc_{file_hash[:12]}"


def _hash_file(file_path: Path) -> str:
    """Return the MD5 hex digest of the file at *file_path*."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def embed_and_store(
    chunks: list[dict[str, Any]],
    file_path: str | Path,
    filename: str,
    vectorstore_dir: str | Path,
    model_name: str = "paraphrase-MiniLM-L3-v2",
) -> str:
    """
    Embed *chunks* and persist them in ChromaDB.

    Parameters
    ----------
    chunks : list[dict]
        Output of ``document_processor.process()``.
        Each dict must have a ``"text"`` key.
    file_path : str | Path
        Path to the original file (used for dedup hashing).
    filename : str
        Human-readable name stored as metadata.
    vectorstore_dir : str | Path
        Root directory for ChromaDB storage.
    model_name : str
        Sentence-transformer model name.

    Returns
    -------
    str
        The ChromaDB collection name used.
    """
    file_path = Path(file_path)
    file_hash = _hash_file(file_path)
    collection_name = _get_collection_name(file_hash)

    client = _get_chroma_client(vectorstore_dir)

    # ── Deduplication ─────────────────────────────────────────
    existing = [c.name for c in client.list_collections()]
    if collection_name in existing:
        logger.info(
            "Collection '%s' already exists for '%s' — skipping re-embedding.",
            collection_name, filename,
        )
        return collection_name

    if not chunks:
        logger.warning("No chunks to embed for '%s'.", filename)
        return collection_name

    # ── Embed ─────────────────────────────────────────────────
    model = _get_embedding_model(model_name)
    texts = [c["text"] for c in chunks]

    logger.info("Embedding %d chunks for '%s'…", len(texts), filename)
    embeddings = model.encode(texts, show_progress_bar=False).tolist()

    # ── Store ─────────────────────────────────────────────────
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [f"{collection_name}_{i}" for i in range(len(texts))]
    metadatas = [
        {
            "source": filename,
            "chunk_index": c.get("chunk_index", i),
            "file_hash": file_hash,
        }
        for i, c in enumerate(chunks)
    ]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    logger.info(
        "Stored %d embeddings in collection '%s'.", len(texts), collection_name
    )
    return collection_name


def retrieve(
    query: str,
    collection_names: list[str],
    vectorstore_dir: str | Path,
    top_k: int = 5,
    model_name: str = "paraphrase-MiniLM-L3-v2",
) -> list[dict[str, Any]]:
    """
    Retrieve the top-*k* most relevant chunks for *query* across all
    specified collections.

    Parameters
    ----------
    query : str
        The user's question.
    collection_names : list[str]
        ChromaDB collection names to search (one per uploaded document).
    vectorstore_dir : str | Path
        Root directory for ChromaDB storage.
    top_k : int
        Number of results to return per collection.
    model_name : str
        Must match the model used during embedding.

    Returns
    -------
    list[dict]
        Each dict: ``{"text": ..., "source": ..., "score": ...}``.
    """
    if not collection_names or not query.strip():
        return []

    client = _get_chroma_client(vectorstore_dir)
    model = _get_embedding_model(model_name)

    query_embedding = model.encode([query], show_progress_bar=False).tolist()[0]

    existing_collections = {c.name for c in client.list_collections()}
    results: list[dict[str, Any]] = []

    for name in collection_names:
        if name not in existing_collections:
            logger.warning("Collection '%s' not found — skipping.", name)
            continue
        try:
            collection = client.get_collection(name)
            resp = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count()),
                include=["documents", "metadatas", "distances"],
            )
            for doc, meta, dist in zip(
                resp["documents"][0],
                resp["metadatas"][0],
                resp["distances"][0],
            ):
                results.append(
                    {
                        "text": doc,
                        "source": meta.get("source", "unknown"),
                        "score": round(1 - dist, 4),  # cosine similarity
                    }
                )
        except Exception as exc:
            logger.error("Retrieval failed for collection '%s': %s", name, exc)

    # Sort globally by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
