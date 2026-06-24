"""
utils/__init__.py — Public API surface for the utils package.
"""

from utils.security import (
    validate_file_content,
    safe_path,
    validate_api_key,
    sanitize_filename,
    is_allowed_extension,
)
from utils.document_processor import process, chunk_text
from utils.rag_engine import embed_and_store, retrieve
from utils.token_manager import (
    track_tokens,
    get_daily_usage,
    check_budget,
    reset_tokens,
    get_token_history,
    get_token_manager,
)

__all__ = [
    # security
    "validate_file_content",
    "safe_path",
    "validate_api_key",
    "sanitize_filename",
    "is_allowed_extension",
    # document_processor
    "process",
    "chunk_text",
    # rag_engine
    "embed_and_store",
    "retrieve",
    # token_manager
    "track_tokens",
    "get_daily_usage",
    "check_budget",
    "reset_tokens",
    "get_token_history",
    "get_token_manager",
]
