"""
app.py — DocuMind RAG Chatbot — main Flask application.

Routes
------
GET  /                  → Chat UI
POST /api/upload        → Upload & process a document
POST /api/chat          → Ask a question about uploaded docs
GET  /api/docs          → List documents in the current session
POST /api/clear         → Clear all documents from the session
GET  /api/health        → Health check
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    session,
)
from flask_cors import CORS
from flask_session import Session
from werkzeug.utils import secure_filename

# ── Local imports ─────────────────────────────────────────────
from config import config
from utils.security import (
    is_allowed_extension,
    safe_path,
    sanitize_filename,
    validate_api_key,
    validate_file_content,
)
from utils.document_processor import process
from utils.rag_engine import embed_and_store, retrieve
from utils.token_manager import check_budget, track_tokens, get_daily_usage

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOGS_DIR / "app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")

# Secret key
app.config["SECRET_KEY"] = config.SECRET_KEY

# ── Flask-Session (server-side, filesystem-based) ─────────────
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = str(config.TEMP_DIR / "flask_sessions")
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=config.SESSION_TIMEOUT_HOURS)
app.config["SESSION_COOKIE_SECURE"] = config.SESSION_COOKIE_SECURE
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

Path(app.config["SESSION_FILE_DIR"]).mkdir(parents=True, exist_ok=True)
Session(app)

# ── CORS ──────────────────────────────────────────────────────
CORS(app, resources={r"/api/*": {"origins": config.CORS_ORIGINS}})


# ── Groq client (lazy) ───────────────────────────────────────
_groq_client = None


def _get_groq():
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        _groq_client = Groq(api_key=config.GROQ_API_KEY)
    return _groq_client


# ── Helpers ───────────────────────────────────────────────────

def _error(message: str, status: int = 400) -> tuple[Response, int]:
    return jsonify({"error": message}), status


def _session_docs() -> list[dict]:
    """Return the list of document metadata stored in the session."""
    return session.get("docs", [])


def _save_session_docs(docs: list[dict]) -> None:
    session["docs"] = docs
    session.modified = True


# ═══════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html", app_name=config.APP_NAME)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "ok",
            "app": config.APP_NAME,
            "version": config.VERSION,
            "environment": config.ENVIRONMENT,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    )


# ── Upload ────────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload():
    """
    Accept a file upload, process it, embed it, and store metadata
    in the session.
    """
    if "file" not in request.files:
        return _error("No file part in the request.")

    file = request.files["file"]
    if not file or file.filename == "":
        return _error("No file selected.")

    original_name = file.filename  # keep for display
    ext = Path(original_name).suffix.lstrip(".").lower()

    if not is_allowed_extension(original_name):
        return _error(
            f"File type '.{ext}' is not supported. "
            f"Allowed: pdf, docx, txt, md, xlsx, csv."
        )

    # Read bytes for content validation
    file_bytes = file.read()
    ok, msg = validate_file_content(file_bytes, original_name)
    if not ok:
        return _error(f"Invalid file: {msg}")

    # Build a unique safe filename
    safe_name = f"{uuid.uuid4().hex}_{sanitize_filename(original_name)}"
    try:
        save_path = safe_path(config.UPLOAD_DIR, safe_name)
    except ValueError as exc:
        return _error(str(exc))

    # Write to disk
    save_path.write_bytes(file_bytes)
    logger.info("Saved upload: %s → %s", original_name, save_path)

    # Process (extract + chunk)
    try:
        chunks = process(save_path, original_name)
    except Exception as exc:
        logger.exception("Document processing failed: %s", exc)
        return _error(f"Could not process file: {exc}", status=500)

    if not chunks:
        return _error("No text could be extracted from this file.")

    # Embed + store
    try:
        collection_name = embed_and_store(
            chunks=chunks,
            file_path=save_path,
            filename=original_name,
            vectorstore_dir=config.VECTORSTORE_DIR,
            model_name=config.EMBEDDING_MODEL,
        )
    except Exception as exc:
        logger.exception("Embedding failed: %s", exc)
        return _error(f"Embedding failed: {exc}", status=500)

    # Update session
    docs = _session_docs()
    # Avoid duplicating the same collection (same file re-uploaded)
    existing_collections = {d["collection"] for d in docs}
    if collection_name not in existing_collections:
        docs.append(
            {
                "name": original_name,
                "collection": collection_name,
                "chunks": len(chunks),
                "uploaded_at": datetime.utcnow().isoformat() + "Z",
            }
        )
        _save_session_docs(docs)

    return jsonify(
        {
            "message": f"'{original_name}' processed successfully.",
            "chunks": len(chunks),
            "collection": collection_name,
            "total_docs": len(docs),
        }
    )


# ── Chat ──────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Retrieve relevant chunks from all session documents and answer
    the user's question using Groq.
    """
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or body.get("message") or "").strip()

    if not question:
        return _error("No question provided.")

    docs = _session_docs()
    if not docs:
        return _error("No documents uploaded yet. Please upload a document first.")

    # ── Token budget check ────────────────────────────────────
    budget_ok, budget_msg, usage = check_budget(estimated_tokens=500)
    if not budget_ok:
        return _error(budget_msg, status=429)

    collection_names = [d["collection"] for d in docs]

    # Retrieve relevant context
    try:
        results = retrieve(
            query=question,
            collection_names=collection_names,
            vectorstore_dir=config.VECTORSTORE_DIR,
            top_k=config.TOP_K_RESULTS,
            model_name=config.EMBEDDING_MODEL,
        )
    except Exception as exc:
        logger.exception("Retrieval error: %s", exc)
        return _error(f"Retrieval failed: {exc}", status=500)

    if not results:
        context_text = "No relevant content found in the uploaded documents."
    else:
        context_parts = []
        for i, r in enumerate(results, 1):
            context_parts.append(
                f"[Source: {r['source']} | relevance: {r['score']}]\n{r['text']}"
            )
        context_text = "\n\n---\n\n".join(context_parts)

    # Build prompt
    system_prompt = (
        "You are DocuMind, an intelligent document assistant. "
        "Answer the user's question using ONLY the context provided below. "
        "If the answer is not in the context, say so honestly. "
        "Be concise, accurate, and cite the source document when possible.\n\n"
        f"Context:\n{context_text}"
    )

    # Call Groq
    try:
        groq = _get_groq()
        response = groq.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            max_tokens=1024,
            temperature=0.2,
        )
        answer = response.choices[0].message.content.strip()
        tokens_used = response.usage.total_tokens if response.usage else 0
    except Exception as exc:
        logger.exception("Groq API error: %s", exc)
        return _error(f"LLM request failed: {exc}", status=500)

    # Track token usage
    if tokens_used:
        track_tokens(config.GROQ_MODEL, tokens_used)

    # Refresh usage stats for response
    daily = get_daily_usage()
    sources = list({r["source"] for r in results})

    response_data = {
        "answer": answer,
        "sources": sources,
        "chunks_used": len(results),
        "tokens_used": tokens_used,
        "token_budget": {
            "daily_used":  daily["daily_total"],
            "daily_limit": daily["daily_limit"],
            "remaining":   daily["remaining"],
            "percent":     daily["percent"],
        },
    }

    # Attach budget warning if near threshold
    if budget_msg:
        response_data["budget_warning"] = budget_msg

    return jsonify(response_data)


# ── Docs list ─────────────────────────────────────────────────

@app.route("/api/docs", methods=["GET"])
def list_docs():
    """Return all documents currently in the session."""
    return jsonify({"docs": _session_docs()})


# ── Token usage ───────────────────────────────────────────────

@app.route("/api/tokens", methods=["GET"])
def token_usage():
    """Return today's token usage statistics."""
    return jsonify(get_daily_usage())


# ── Clear ─────────────────────────────────────────────────────

@app.route("/api/clear", methods=["POST"])
def clear_docs():
    """Remove all documents from the session."""
    _save_session_docs([])
    return jsonify({"message": "Session cleared."})


# ═══════════════════════════════════════════════════════════════
# Entry-point
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("Starting %s v%s on %s:%s", config.APP_NAME, config.VERSION, config.HOST, config.PORT)
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.FLASK_DEBUG,
        use_reloader=False,   # CRITICAL: prevents double-loading embedding model
    )
