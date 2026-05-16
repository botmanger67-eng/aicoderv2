"""
Utility functions for the Telegram bot.
Provides rate limiting, validation, formatting, and logging setup.
"""

import asyncio
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import aiosqlite
from telegram import Update
from telegram.ext import ContextTypes

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
) -> None:
    """
    Configure logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path to write logs to
        log_format: Custom log format string
    """
    if log_format is None:
        log_format = (
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    handlers: List[logging.Handler] = [logging.StreamHandler()]

    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            handlers.append(file_handler)
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not create log file {log_file}: {e}")

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format=log_format,
        handlers=handlers,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    logger.info(f"Logging configured with level: {log_level}")


# =============================================================================
# Rate Limiter
# =============================================================================

class RateLimiter:
    """
    Token bucket rate limiter with per-user and per-command tracking.

    Supports both global and per-user rate limits with configurable
    burst capacity and refill rates.
    """

    def __init__(
        self,
        max_calls: int = 10,
        period: float = 60.0,
        burst_multiplier: float = 1.5,
    ):
        """
        Initialize rate limiter.

        Args:
            max_calls: Maximum number of calls allowed in the period
            period: Time period in seconds
            burst_multiplier: Multiplier for burst capacity (default 1.5x)
        """
        self.max_calls = max_calls
        self.period = period
        self.burst_capacity = int(max_calls * burst_multiplier)
        self._buckets: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def _get_bucket(self, key: str) -> Dict[str, Any]:
        """Get or create a token bucket for the given key."""
        if key not in self._buckets:
            self._buckets[key] = {
                "tokens": self.burst_capacity,
                "last_refill": time.monotonic(),
                "max_tokens": self.burst_capacity,
            }
        return self._buckets[key]

    def _refill_bucket(self, bucket: Dict[str, Any]) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - bucket["last_refill"]
        refill_rate = self.max_calls / self.period
        tokens_to_add = elapsed * refill_rate

        if tokens_to_add > 0:
            bucket["tokens"] = min(
                bucket["max_tokens"],
                bucket["tokens"] + tokens_to_add,
            )
            bucket["last_refill"] = now

    async def check_rate_limit(
        self,
        user_id: Union[int, str],
        command: Optional[str] = None,
    ) -> Tuple[bool, float]:
        """
        Check if a request is allowed under rate limits.

        Args:
            user_id: User ID to check
            command: Optional command name for per-command limits

        Returns:
            Tuple of (is_allowed, wait_time_seconds)
        """
        key = f"{user_id}:{command}" if command else str(user_id)

        async with self._lock:
            bucket = self._get_bucket(key)
            self._refill_bucket(bucket)

            if bucket["tokens"] >= 1:
                bucket["tokens"] -= 1
                return True, 0.0
            else:
                # Calculate wait time until next token
                wait_time = self.period / self.max_calls
                return False, wait_time

    async def get_remaining_calls(
        self,
        user_id: Union[int, str],
        command: Optional[str] = None,
    ) -> int:
        """
        Get remaining calls for a user.

        Args:
            user_id: User ID
            command: Optional command name

        Returns:
            Number of remaining calls
        """
        key = f"{user_id}:{command}" if command else str(user_id)

        async with self._lock:
            bucket = self._get_bucket(key)
            self._refill_bucket(bucket)
            return int(bucket["tokens"])

    def reset_user(self, user_id: Union[int, str]) -> None:
        """Reset rate limit for a specific user."""
        key = str(user_id)
        self._buckets.pop(key, None)

    def reset_all(self) -> None:
        """Reset all rate limits."""
        self._buckets.clear()


# Global rate limiter instance
rate_limiter = RateLimiter()


# =============================================================================
# Validators
# =============================================================================

def validate_telegram_id(value: Any) -> bool:
    """
    Validate a Telegram user/chat ID.

    Args:
        value: Value to validate

    Returns:
        True if valid Telegram ID, False otherwise
    """
    if isinstance(value, int):
        return True
    if isinstance(value, str):
        try:
            int(value)
            return True
        except (ValueError, TypeError):
            return False
    return False


def validate_username(username: str) -> bool:
    """
    Validate a Telegram username.

    Args:
        username: Username to validate (with or without @)

    Returns:
        True if valid username format
    """
    if not username:
        return False

    # Remove leading @ if present
    clean_username = username.lstrip("@")

    # Telegram usernames: 5-32 chars, alphanumeric and underscore
    pattern = r"^[a-zA-Z][a-zA-Z0-9_]{4,31}$"
    return bool(re.match(pattern, clean_username))


def validate_email(email: str) -> bool:
    """
    Validate an email address.

    Args:
        email: Email to validate

    Returns:
        True if valid email format
    """
    if not email:
        return False

    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_language_code(code: str) -> bool:
    """
    Validate a language code (ISO 639-1).

    Args:
        code: Language code to validate

    Returns:
        True if valid language code
    """
    if not code or len(code) != 2:
        return False
    return code.isalpha() and code.islower()


def validate_message_length(text: str, max_length: int = 4096) -> bool:
    """
    Validate message length for Telegram.

    Args:
        text: Message text
        max_length: Maximum allowed length (default 4096 for Telegram)

    Returns:
        True if within length limit
    """
    return len(text) <= max_length


def sanitize_input(text: str) -> str:
    """
    Sanitize user input by removing potentially harmful characters.

    Args:
        text: Input text to sanitize

    Returns:
        Sanitized text
    """
    if not text:
        return ""

    # Remove control characters except newlines and tabs
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Limit consecutive newlines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # Strip leading/trailing whitespace
    cleaned = cleaned.strip()

    return cleaned


# =============================================================================
# Formatters
# =============================================================================

def format_duration(seconds: Union[int, float]) -> str:
    """
    Format a duration in seconds to a human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string (e.g., "2h 30m", "45s")
    """
    if seconds < 0:
        return "0s"

    seconds = int(seconds)

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


def format_number(number: Union[int, float], decimals: int = 2) -> str:
    """
    Format a number with commas and optional decimal places.

    Args:
        number: Number to format
        decimals: Number of decimal places (default 2)

    Returns:
        Formatted number string
    """
    if isinstance(number, float):
        return f"{number:,.{decimals}f}"
    return f"{number:,}"


def format_percentage(value: float, total: float) -> str:
    """
    Format a percentage value.

    Args:
        value: Current value
        total: Total value

    Returns:
        Formatted percentage string (e.g., "45.5%")
    """
    if total == 0:
        return "0%"

    percentage = (value / total) * 100
    return f"{percentage:.1f}%"


def format_timestamp(timestamp: Union[int, float, datetime]) -> str:
    """
    Format a timestamp to a readable date/time string.

    Args:
        timestamp: Unix timestamp or datetime object

    Returns:
        Formatted date/time string
    """
    if isinstance(timestamp, (int, float)):
        dt = datetime.fromtimestamp(timestamp)
    elif isinstance(timestamp, datetime):
        dt = timestamp
    else:
        return "Invalid timestamp"

    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_user_mention(user_id: int, username: Optional[str] = None) -> str:
    """
    Format a user mention for Telegram.

    Args:
        user_id: Telegram user ID
        username: Optional username

    Returns:
        Formatted mention string
    """
    if username:
        return f"@{username}"
    return f"[User {user_id}](tg://user?id={user_id})"


def truncate_text(text: str, max_length: int = 200, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length with optional suffix.

    Args:
        text: Text to truncate
        max_length: Maximum length (default 200)
        suffix: Suffix to add when truncated (default "...")

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text

    return text[: max_length - len(suffix)] + suffix


def escape_markdown(text: str, version: int = 2) -> str:
    """
    Escape special characters for Telegram Markdown.

    Args:
        text: Text to escape
        version: Markdown version (1 or 2, default 2)

    Returns:
        Escaped text safe for Markdown
    """
    if version == 1:
        escape_chars = r"_*`["
    else:
        escape_chars = r"_*[]()~`>#+-=|{}.!"

    for char in escape_chars:
        text = text.replace(char, f"\\{char}")

    return text


def format_error_message(error: Exception) -> str:
    """
    Format an exception into a user-friendly error message.

    Args:
        error: Exception to format

    Returns:
        Formatted error message
    """
    error_type = type(error).__name__
    error_msg = str(error)

    # Truncate long error messages
    if len(error_msg) > 100:
        error_msg = error_msg[:97] + "..."

    return f"❌ {error_type}: {error_msg}"


# =============================================================================
# Database Helpers
# =============================================================================

async def execute_query(
    db_path: str,
    query: str,
    params: Optional[Tuple[Any, ...]] = None,
) -> List[Dict[str, Any]]:
    """
    Execute a database query and return results as list of dictionaries.

    Args:
        db_path: Path to SQLite database file
        query: SQL query to execute
        params: Optional query parameters

    Returns:
        List of dictionaries representing rows
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params or ())
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except aiosqlite.Error as e:
        logger.error(f"Database query failed: {e}")
        raise


async def execute_write(
    db_path: str,
    query: str,
    params: Optional[Tuple[Any, ...]] = None,
) -> int:
    """
    Execute a write query (INSERT, UPDATE, DELETE) and return affected rows.

    Args:
        db_path: Path to SQLite database file
        query: SQL query to execute
        params: Optional query parameters

    Returns:
        Number of affected rows
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(query, params or ())
            await db.commit()
            return cursor.rowcount
    except aiosqlite.Error as e:
        logger.error(f"Database write failed: {e}")
        raise


# =============================================================================
# Decorators
# =============================================================================

def rate_limit(
    max_calls: int = 10,
    period: float = 60.0,
    per_command: bool = False,
) -> Callable:
    """
    Decorator to apply rate limiting to a handler function.

    Args:
        max_calls: Maximum calls allowed in the period
        period: Time period in seconds
        per_command: If True, rate limit per command (default False)

    Returns:
        Decorated function
    """
    limiter = RateLimiter(max_calls=max_calls, period=period)

    def decorator(func: Callable) -> Callable:
        async def wrapper(
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            user_id = update.effective_user.id if update.effective_user else 0
            command = None

            if per_command and update.message and update.message.text:
                # Extract command name
                text = update.message.text.split()[0]
                if text.startswith("/"):
                    command = text[1:].split("@")[0]

            is_allowed, wait_time = await limiter.check_rate_limit(
                user_id, command
            )

            if not is_allowed:
                if update.effective_message:
                    await update.effective_message.reply_text(
                        f"⏳ Rate limit exceeded. Please wait "
                        f"{format_duration(wait_time)} before trying again."
                    )
                return None

            return await func(update, context, *args, **kwargs)

        return wrapper

    return decorator


def log_execution_time(func: Callable) -> Callable:
    """
    Decorator to log the execution time of a function.

    Args:
        func: Function to wrap

    Returns:
        Wrapped function with timing logs
    """
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.monotonic()
        try:
            result = await func(*args, **kwargs)
            elapsed = time.monotonic() - start_time
            logger.debug(
                f"{func.__name__} executed in {elapsed:.3f}s"
            )
            return result
        except Exception as e:
            elapsed = time.monotonic() - start_time
            logger.error(
                f"{func.__name__} failed after {elapsed:.3f}s: {e}"
            )
            raise

    return wrapper


# =============================================================================
# Miscellaneous Helpers
# =============================================================================

def get_user_info(update: Update) -> Dict[str, Any]:
    """
    Extract user information from a Telegram update.

    Args:
        update: Telegram update object

    Returns:
        Dictionary with user information
    """
    user = update.effective_user
    if not user:
        return {}

    return {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "language_code": user.language_code,
        "is_bot": user.is_bot,
    }


def split_message(text: str, max_length: int = 4096) -> List[str]:
    """
    Split a long message into chunks for Telegram.

    Args:
        text: Message text to split
        max_length: Maximum length per chunk (default 4096)

    Returns:
        List of message chunks