import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()


class Config:
    """
    Configuration class that loads and validates environment variables
    with sensible fallback defaults.
    """

    # Telegram Bot
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "MyAdvancedBot")
    BOT_WEBHOOK_URL: Optional[str] = os.getenv("BOT_WEBHOOK_URL", None)

    # DeepSeek API
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_API_BASE_URL: str = os.getenv(
        "DEEPSEEK_API_BASE_URL", "https://api.deepseek.com/v1"
    )
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_MAX_TOKENS: int = int(os.getenv("DEEPSEEK_MAX_TOKENS", "2048"))
    DEEPSEEK_TEMPERATURE: float = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.7"))

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db")
    DATABASE_POOL_SIZE: int = int(os.getenv("DATABASE_POOL_SIZE", "10"))
    DATABASE_MAX_OVERFLOW: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_MESSAGES: int = int(os.getenv("RATE_LIMIT_MESSAGES", "10"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # Admin
    ADMIN_IDS: list[int] = [
        int(x.strip())
        for x in os.getenv("ADMIN_IDS", "").split(",")
        if x.strip().isdigit()
    ]
    ADMIN_CHAT_ID: Optional[int] = (
        int(os.getenv("ADMIN_CHAT_ID")) if os.getenv("ADMIN_CHAT_ID") else None
    )

    # Multi-language
    DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "en")
    SUPPORTED_LANGUAGES: list[str] = [
        lang.strip()
        for lang in os.getenv("SUPPORTED_LANGUAGES", "en,ru,es,fr,de,zh,ja,ar").split(",")
        if lang.strip()
    ]

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT: str = os.getenv(
        "LOG_FORMAT",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    LOG_FILE: Optional[str] = os.getenv("LOG_FILE", None)

    # Webhook / Polling
    USE_WEBHOOK: bool = os.getenv("USE_WEBHOOK", "false").lower() == "true"
    WEBHOOK_LISTEN: str = os.getenv("WEBHOOK_LISTEN", "0.0.0.0")
    WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8443"))
    WEBHOOK_SECRET_TOKEN: Optional[str] = os.getenv("WEBHOOK_SECRET_TOKEN", None)

    # Other
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    MAX_MESSAGE_LENGTH: int = int(os.getenv("MAX_MESSAGE_LENGTH", "4096"))
    USER_CACHE_TTL: int = int(os.getenv("USER_CACHE_TTL", "300"))  # seconds

    @classmethod
    def validate(cls) -> None:
        """
        Validate critical configuration values.
        Raises ValueError if required settings are missing or invalid.
        """
        errors: list[str] = []

        # Bot token is required
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is not set. Please provide a valid Telegram Bot Token.")

        # DeepSeek API key is required
        if not cls.DEEPSEEK_API_KEY:
            errors.append(
                "DEEPSEEK_API_KEY is not set. Please provide a valid DeepSeek API Key."
            )

        # Validate rate limit values
        if cls.RATE_LIMIT_MESSAGES <= 0:
            errors.append("RATE_LIMIT_MESSAGES must be a positive integer.")
        if cls.RATE_LIMIT_WINDOW_SECONDS <= 0:
            errors.append("RATE_LIMIT_WINDOW_SECONDS must be a positive integer.")

        # Validate database URL
        if not cls.DATABASE_URL.startswith("sqlite"):
            errors.append(
                f"DATABASE_URL must start with 'sqlite'. Current value: {cls.DATABASE_URL}"
            )

        # Validate log level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if cls.LOG_LEVEL not in valid_log_levels:
            errors.append(
                f"LOG_LEVEL must be one of {valid_log_levels}. Got: {cls.LOG_LEVEL}"
            )

        # Validate default language is in supported languages
        if cls.DEFAULT_LANGUAGE not in cls.SUPPORTED_LANGUAGES:
            errors.append(
                f"DEFAULT_LANGUAGE '{cls.DEFAULT_LANGUAGE}' is not in SUPPORTED_LANGUAGES: {cls.SUPPORTED_LANGUAGES}"
            )

        # Validate webhook port if webhook is enabled
        if cls.USE_WEBHOOK:
            if not (1 <= cls.WEBHOOK_PORT <= 65535):
                errors.append(
                    f"WEBHOOK_PORT must be between 1 and 65535. Got: {cls.WEBHOOK_PORT}"
                )

        if errors:
            raise ValueError(
                "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

    @classmethod
    def display(cls) -> str:
        """
        Return a formatted string of the current configuration (excluding secrets).
        """
        config_lines = [
            "=== Bot Configuration ===",
            f"Bot Username: {cls.BOT_USERNAME}",
            f"Webhook Enabled: {cls.USE_WEBHOOK}",
            f"Webhook URL: {cls.BOT_WEBHOOK_URL or 'Not set'}",
            f"DeepSeek Model: {cls.DEEPSEEK_MODEL}",
            f"DeepSeek Max Tokens: {cls.DEEPSEEK_MAX_TOKENS}",
            f"DeepSeek Temperature: {cls.DEEPSEEK_TEMPERATURE}",
            f"Database URL: {cls.DATABASE_URL}",
            f"Rate Limit Enabled: {cls.RATE_LIMIT_ENABLED}",
            f"Rate Limit: {cls.RATE_LIMIT_MESSAGES} msg / {cls.RATE_LIMIT_WINDOW_SECONDS}s",
            f"Admin IDs: {cls.ADMIN_IDS}",
            f"Default Language: {cls.DEFAULT_LANGUAGE}",
            f"Supported Languages: {cls.SUPPORTED_LANGUAGES}",
            f"Log Level: {cls.LOG_LEVEL}",
            f"Debug Mode: {cls.DEBUG}",
            f"Max Message Length: {cls.MAX_MESSAGE_LENGTH}",
            f"User Cache TTL: {cls.USER_CACHE_TTL}s",
        ]
        return "\n".join(config_lines)


# Validate configuration on import
try:
    Config.validate()
except ValueError as e:
    import logging

    logging.basicConfig(level=logging.CRITICAL)
    logging.critical("Configuration error: %s", e)
    raise SystemExit(1) from e