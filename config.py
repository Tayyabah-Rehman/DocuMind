"""
config.py — Central configuration loader for DocuMind.
Reads from .env and provides typed settings to the rest of the app.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")


class Config:
    # ── App ───────────────────────────────────────────────────
    APP_NAME: str = os.getenv("APP_NAME", "DocuMind")
    VERSION: str = os.getenv("VERSION", "1.0.0")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "5000"))
    FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "True").lower() == "true"

    # ── Security ──────────────────────────────────────────────
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "fallback-secret-key-change-in-production"
    )
    API_KEYS: list = [
        k.strip()
        for k in os.getenv("API_KEYS", "dev-key-12345").split(",")
        if k.strip()
    ]
    CORS_ORIGINS: list = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000"
        ).split(",")
        if o.strip()
    ]

    # ── Groq ──────────────────────────────────────────────────
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_MAX_RETRIES: int = int(os.getenv("GROQ_MAX_RETRIES", "3"))

    # ── Validation bypass ─────────────────────────────────────
    SKIP_CONFIG_VALIDATION: bool = (
        os.getenv("SKIP_CONFIG_VALIDATION", "false").lower() == "true"
    )

    # ── Tokens ────────────────────────────────────────────────
    DAILY_TOKEN_BUDGET: int = int(os.getenv("DAILY_TOKEN_BUDGET", "80000"))
    TOKEN_WARN_THRESHOLD: int = int(os.getenv("TOKEN_WARN_THRESHOLD", "70000"))
    TOKEN_RESET_HOUR: int = int(os.getenv("TOKEN_RESET_HOUR", "0"))

    # ── Rate limits (stored as strings, parsed by Flask-Limiter) ─
    RATE_UPLOAD: str = os.getenv("RATE_UPLOAD", "5 per minute")
    RATE_CHAT: str = os.getenv("RATE_CHAT", "20 per minute")
    RATE_DEFAULT: str = os.getenv("RATE_DEFAULT", "60 per minute")

    # ── Cache ─────────────────────────────────────────────────
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
    MAX_CACHE_ENTRIES: int = int(os.getenv("MAX_CACHE_ENTRIES", "500"))
    CACHE_PERSISTENCE: bool = (
        os.getenv("CACHE_PERSISTENCE", "True").lower() == "true"
    )

    # ── Session ───────────────────────────────────────────────
    SESSION_TIMEOUT_HOURS: int = int(os.getenv("SESSION_TIMEOUT_HOURS", "8"))
    SESSION_COOKIE_SECURE: bool = (
        os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"
    )

    # ── Logging ───────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # ── Paths ─────────────────────────────────────────────────
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    VECTORSTORE_DIR: Path = BASE_DIR / "vectorstore"
    LOGS_DIR: Path = BASE_DIR / "logs"
    CACHE_DIR: Path = BASE_DIR / "cache"
    SUMMARIES_DIR: Path = BASE_DIR / "summaries"
    TEMP_DIR: Path = BASE_DIR / "temp"

    # ── File upload limits ────────────────────────────────────
    MAX_CONTENT_LENGTH: int = 50 * 1024 * 1024  # 50 MB
    ALLOWED_EXTENSIONS: set = {
        "pdf", "txt", "md", "docx", "doc", "xlsx", "xls", "csv"
    }
    EMBEDDING_MODEL: str = "paraphrase-MiniLM-L3-v2"
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 100
    TOP_K_RESULTS: int = 5

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create all required directories if they do not exist."""
        for d in (
            cls.UPLOAD_DIR,
            cls.VECTORSTORE_DIR,
            cls.LOGS_DIR,
            cls.CACHE_DIR,
            cls.SUMMARIES_DIR,
            cls.TEMP_DIR,
        ):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate(cls) -> None:
        """Raise if critical settings are missing (unless skipped)."""
        if cls.SKIP_CONFIG_VALIDATION:
            return
        if not cls.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not set in .env")
        if not cls.SECRET_KEY:
            raise ValueError("SECRET_KEY is not set in .env")


# Convenience singleton
config = Config()
config.ensure_dirs()
