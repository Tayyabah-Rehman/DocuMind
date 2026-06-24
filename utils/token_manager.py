"""
utils/token_manager.py — Persistent Token Management

Handles token tracking with disk persistence across server restarts.
Compatible with the DocuMind config object (config.py).
"""

import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from threading import Lock

from config import config

logger = logging.getLogger(__name__)

# ── Constants pulled from config ──────────────────────────────
DAILY_TOKEN_BUDGET: int = config.DAILY_TOKEN_BUDGET
TOKEN_RESET_HOUR: int   = config.TOKEN_RESET_HOUR
TOKEN_WARN_THRESHOLD: int = config.TOKEN_WARN_THRESHOLD
TOKEN_HISTORY_DAYS: int = 30          # keep 30 days of history

# ── Persistence path ──────────────────────────────────────────
TOKEN_FILE = Path(config.CACHE_DIR) / "token_usage.json"
TOKEN_LOCK = Lock()


class TokenManager:
    """
    Thread-safe token manager with disk persistence.
    Tracks daily usage, history, and auto-resets at configured hour.
    """

    def __init__(self) -> None:
        self._data: Dict = {
            "daily_total": 0,
            "date": "",
            "history": [],
            "last_reset": None,
            "monthly_total": 0,
            "month": "",
        }
        self._loaded = False
        self._load()

    # ── Persistence ───────────────────────────────────────────

    def _load(self) -> None:
        """Load token data from disk (idempotent)."""
        if self._loaded:
            return
        with TOKEN_LOCK:
            try:
                if TOKEN_FILE.exists():
                    with open(TOKEN_FILE, "r", encoding="utf-8") as fh:
                        saved = json.load(fh)
                        self._data.update(saved)
                        logger.info(
                            "Token data loaded: %s tokens used today",
                            f"{self._data['daily_total']:,}",
                        )
                self._loaded = True
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Could not load token data: %s", exc)
                self._loaded = True

    def _save(self) -> None:
        """Persist token data to disk."""
        with TOKEN_LOCK:
            try:
                TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(TOKEN_FILE, "w", encoding="utf-8") as fh:
                    json.dump(self._data, fh, indent=2, ensure_ascii=False)
            except OSError as exc:
                logger.error("Could not save token data: %s", exc)

    # ── Date helpers ──────────────────────────────────────────

    @staticmethod
    def _today() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _current_month() -> str:
        return datetime.now().strftime("%Y-%m")

    def _should_reset_daily(self) -> bool:
        today = self._today()
        if self._data.get("date") != today:
            return True
        if self._data.get("last_reset"):
            try:
                last = datetime.fromisoformat(self._data["last_reset"])
                if last.date() < datetime.now().date():
                    return True
            except (ValueError, TypeError):
                return True
        return False

    def _should_reset_monthly(self) -> bool:
        return self._data.get("month") != self._current_month()

    # ── Core public methods ───────────────────────────────────

    def track(self, model: str, tokens_used: int) -> None:
        """
        Record token usage and persist to disk.
        Auto-resets daily counter when the date rolls over.
        """
        self._load()

        with TOKEN_LOCK:
            # Daily reset
            if self._should_reset_daily():
                self._data["daily_total"] = 0
                self._data["date"] = self._today()
                self._data["last_reset"] = datetime.now().isoformat()
                logger.info("Daily token counter reset.")

            # Monthly reset
            if self._should_reset_monthly():
                self._data["monthly_total"] = 0
                self._data["month"] = self._current_month()
                logger.info("Monthly token counter reset.")

            # Accumulate
            self._data["daily_total"]   += tokens_used
            self._data["monthly_total"] += tokens_used

            # Append history entry
            self._data["history"].append({
                "model":  model,
                "tokens": tokens_used,
                "ts":     time.time(),
                "date":   self._today(),
            })

            # Trim history: keep last 500 entries OR last N days
            cutoff = time.time() - (TOKEN_HISTORY_DAYS * 86400)
            self._data["history"] = [
                h for h in self._data["history"][-500:]
                if h.get("ts", 0) > cutoff
            ]

        self._save()
        logger.info(
            "Tokens: +%d | Daily: %s/%s",
            tokens_used,
            f"{self._data['daily_total']:,}",
            f"{DAILY_TOKEN_BUDGET:,}",
        )

    def get_usage(self) -> Dict:
        """Return current usage statistics as a dict."""
        self._load()

        # Apply reset before reading
        if self._should_reset_daily():
            with TOKEN_LOCK:
                self._data["daily_total"] = 0
                self._data["date"] = self._today()
                self._data["last_reset"] = datetime.now().isoformat()
            self._save()

        with TOKEN_LOCK:
            used      = self._data.get("daily_total", 0)
            remaining = max(0, DAILY_TOKEN_BUDGET - used)
            percent   = round((used / DAILY_TOKEN_BUDGET) * 100, 1) if DAILY_TOKEN_BUDGET else 0

            return {
                "daily_total":   used,
                "daily_limit":   DAILY_TOKEN_BUDGET,
                "remaining":     remaining,
                "percent":       percent,
                "date":          self._data.get("date", self._today()),
                "reset_hour":    TOKEN_RESET_HOUR,
                "warning":       used >= TOKEN_WARN_THRESHOLD,
                "critical":      percent >= 90,
                "exhausted":     percent >= 100,
                "monthly_total": self._data.get("monthly_total", 0),
                "month":         self._data.get("month", self._current_month()),
                "history_count": len(self._data.get("history", [])),
            }

    def check_budget(self, estimated_tokens: int = 500) -> Tuple[bool, str, Dict]:
        """
        Check whether enough budget remains for the next request.

        Returns
        -------
        (ok: bool, message: str, usage: dict)
        """
        usage = self.get_usage()

        if usage["exhausted"] or usage["remaining"] < estimated_tokens:
            msg = (
                f"Daily token budget exhausted "
                f"({usage['daily_total']:,}/{DAILY_TOKEN_BUDGET:,} used). "
                f"Resets at {TOKEN_RESET_HOUR:02d}:00."
            )
            return False, msg, usage

        if usage["critical"]:
            return True, f"⚠️ {usage['percent']}% of daily budget used.", usage

        if usage["warning"]:
            return True, f"⚡ {usage['percent']}% of daily budget used.", usage

        return True, "", usage

    def reset(self) -> None:
        """Force-reset the daily counter (admin use)."""
        with TOKEN_LOCK:
            self._data["daily_total"] = 0
            self._data["date"]        = self._today()
            self._data["last_reset"]  = datetime.now().isoformat()
        self._save()
        logger.info("Token counter manually reset.")

    def get_history(self, days: int = 7) -> List[Dict]:
        """Return raw history entries from the last *days* days."""
        self._load()
        cutoff = time.time() - (days * 86400)
        return [h for h in self._data.get("history", []) if h.get("ts", 0) > cutoff]

    def get_daily_history(self) -> Dict[str, int]:
        """Return per-day aggregated token counts (for charting)."""
        self._load()
        daily: Dict[str, int] = {}
        for entry in self._data.get("history", []):
            date   = entry.get("date", "")
            tokens = entry.get("tokens", 0)
            if date:
                daily[date] = daily.get(date, 0) + tokens
        return daily


# ── Singleton ─────────────────────────────────────────────────
_token_manager: Optional[TokenManager] = None


def get_token_manager() -> TokenManager:
    """Return the global TokenManager singleton."""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager


# ── Convenience wrappers ──────────────────────────────────────

def track_tokens(model: str, tokens_used: int) -> None:
    """Track token usage for *model*."""
    get_token_manager().track(model, tokens_used)


def get_daily_usage() -> Dict:
    """Get today's usage statistics."""
    return get_token_manager().get_usage()


def check_budget(estimated_tokens: int = 500) -> Tuple[bool, str, Dict]:
    """Check whether the budget allows another request."""
    return get_token_manager().check_budget(estimated_tokens)


def reset_tokens() -> None:
    """Force-reset the daily counter."""
    get_token_manager().reset()


def get_token_history(days: int = 7) -> List[Dict]:
    """Return history entries for the last *days* days."""
    return get_token_manager().get_history(days)


__all__ = [
    "TokenManager",
    "get_token_manager",
    "track_tokens",
    "get_daily_usage",
    "check_budget",
    "reset_tokens",
    "get_token_history",
]
