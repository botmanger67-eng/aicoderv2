"""
Main entry point for the Telegram bot.
Initializes and runs the bot with comprehensive error handling.
"""

import asyncio
import logging
import sys
from typing import NoReturn

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.error import (
    TelegramError,
    NetworkError,
    TimedOut,
    Conflict,
    InvalidToken,
    RetryAfter,
)

# Local imports
from config import Config
from handlers import (
    start_command,
    help_command,
    settings_command,
    profile_command,
    admin_command,
    language_command,
    handle_message,
    handle_callback_query,
    error_handler,
)
from database import Database
from rate_limiter import RateLimiter
from middleware import setup_middleware

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


class BotInitializationError(Exception):
    """Custom exception for bot initialization failures."""
    pass


async def initialize_components() -> tuple[Database, RateLimiter]:
    """
    Initialize all bot components with proper error handling.
    
    Returns:
        Tuple containing Database and RateLimiter instances.
    
    Raises:
        BotInitializationError: If initialization fails.
    """
    try:
        logger.info("Initializing database...")
        database = Database(Config.DATABASE_PATH)
        await database.initialize()
        logger.info("Database initialized successfully.")
        
        logger.info("Initializing rate limiter...")
        rate_limiter = RateLimiter(
            max_requests=Config.MAX_REQUESTS_PER_MINUTE,
            time_window=60
        )
        logger.info("Rate limiter initialized successfully.")
        
        return database, rate_limiter
        
    except Exception as e:
        error_msg = f"Failed to initialize components: {str(e)}"
        logger.error(error_msg)
        raise BotInitializationError(error_msg) from e


async def post_init(application: Application) -> None:
    """
    Post-initialization callback for the application.
    
    Args:
        application: The Application instance.
    """
    logger.info("Bot application initialized successfully.")
    
    # Set up bot commands
    commands = [
        ("start", "Start the bot"),
        ("help", "Get help information"),
        ("settings", "Configure your settings"),
        ("profile", "View your profile"),
        ("language", "Change language preference"),
        ("admin", "Admin panel (admin only)"),
    ]
    
    try:
        await application.bot.set_my_commands(commands)
        logger.info("Bot commands set successfully.")
    except Exception as e:
        logger.warning(f"Failed to set bot commands: {e}")


async def post_shutdown(application: Application) -> None:
    """
    Post-shutdown callback for cleanup.
    
    Args:
        application: The Application instance.
    """
    logger.info("Shutting down bot...")
    
    # Clean up resources
    if hasattr(application, 'database'):
        await application.database.close()
        logger.info("Database connection closed.")
    
    if hasattr(application, 'rate_limiter'):
        await application.rate_limiter.close()
        logger.info("Rate limiter closed.")


def create_application() -> Application:
    """
    Create and configure the Telegram bot application.
    
    Returns:
        Configured Application instance.
    
    Raises:
        BotInitializationError: If application creation fails.
    """
    try:
        logger.info("Creating bot application...")
        
        # Build application with configuration
        application = (
            ApplicationBuilder()
            .token(Config.BOT_TOKEN)
            .concurrent_updates(True)
            .connection_pool_size(Config.CONNECTION_POOL_SIZE)
            .pool_timeout(Config.POOL_TIMEOUT)
            .read_timeout(Config.READ_TIMEOUT)
            .write_timeout(Config.WRITE_TIMEOUT)
            .connect_timeout(Config.CONNECT_TIMEOUT)
            .post_init(post_init)
            .post_shutdown(post_shutdown)
            .build()
        )
        
        # Register handlers
        register_handlers(application)
        
        # Set up middleware
        setup_middleware(application)
        
        logger.info("Application created successfully.")
        return application
        
    except InvalidToken:
        error_msg = "Invalid bot token provided. Please check your configuration."
        logger.error(error_msg)
        raise BotInitializationError(error_msg)
    except Exception as e:
        error_msg = f"Failed to create application: {str(e)}"
        logger.error(error_msg)
        raise BotInitializationError(error_msg)


def register_handlers(application: Application) -> None:
    """
    Register all command and message handlers.
    
    Args:
        application: The Application instance.
    """
    logger.info("Registering handlers...")
    
    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("language", language_command))
    
    # Message handler for text messages
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )
    
    # Callback query handler for inline keyboards
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    logger.info("Handlers registered successfully.")


async def run_bot() -> NoReturn:
    """
    Main bot execution function with comprehensive error handling.
    
    This function never returns normally; it runs indefinitely or until
    a fatal error occurs.
    """
    application = None
    
    try:
        # Initialize components
        database, rate_limiter = await initialize_components()
        
        # Create application
        application = create_application()
        
        # Store components in application context
        application.database = database
        application.rate_limiter = rate_limiter
        
        # Start the bot
        logger.info("Starting bot polling...")
        
        # Use webhook or polling based on configuration
        if Config.USE_WEBHOOK:
            await application.run_webhook(
                listen=Config.WEBHOOK_HOST,
                port=Config.WEBHOOK_PORT,
                url_path=Config.WEBHOOK_PATH,
                webhook_url=Config.WEBHOOK_URL,
                secret_token=Config.WEBHOOK_SECRET,
                drop_pending_updates=Config.DROP_PENDING_UPDATES,
            )
        else:
            await application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=Config.DROP_PENDING_UPDATES,
                close_loop=False,
            )
            
    except BotInitializationError as e:
        logger.critical(f"Bot initialization failed: {e}")
        sys.exit(1)
    except InvalidToken:
        logger.critical("Invalid bot token. Please check your .env file.")
        sys.exit(1)
    except Conflict as e:
        logger.critical(f"Bot conflict detected: {e}")
        logger.critical("Another instance of this bot is running. Please stop it first.")
        sys.exit(1)
    except NetworkError as e:
        logger.error(f"Network error occurred: {e}")
        logger.info("Retrying connection in 5 seconds...")
        await asyncio.sleep(5)
        await run_bot()  # Retry
    except TimedOut as e:
        logger.error(f"Request timed out: {e}")
        logger.info("Retrying connection in 3 seconds...")
        await asyncio.sleep(3)
        await run_bot()  # Retry
    except RetryAfter as e:
        retry_time = e.retry_after
        logger.warning(f"Rate limited. Retrying after {retry_time} seconds...")
        await asyncio.sleep(retry_time)
        await run_bot()  # Retry
    except TelegramError as e:
        logger.error(f"Telegram API error: {e}")
        logger.info("Restarting bot in 10 seconds...")
        await asyncio.sleep(10)
        await run_bot()  # Retry
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
        if application:
            await application.stop()
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Unexpected fatal error: {e}", exc_info=True)
        if application:
            await application.stop()
        sys.exit(1)
    finally:
        if application:
            await application.shutdown()


def main() -> None:
    """
    Main entry point for the bot application.
    Sets up and runs the bot with proper error handling.
    """
    try:
        # Validate configuration
        Config.validate()
        
        # Run the bot
        asyncio.run(run_bot())
        
    except BotInitializationError as e:
        logger.critical(f"Bot initialization failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Unexpected error in main: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()