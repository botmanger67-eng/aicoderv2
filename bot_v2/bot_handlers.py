"""
Telegram bot command and message handlers with inline keyboards and pagination.
Handles user interactions, AI chat, admin commands, and multi-language support.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    ChatMember,
    Chat,
    User,
)
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    filters,
)
from telegram.helpers import escape_markdown

from database import Database
from config import Config
from deepseek_client import DeepSeekClient
from rate_limiter import RateLimiter
from i18n import I18n
from models import UserProfile, ChatHistory, AdminAction

# Configure logging
logger = logging.getLogger(__name__)

# Conversation states
(
    SETTING_LANGUAGE,
    SETTING_AI_MODEL,
    SETTING_AI_TEMPERATURE,
    SETTING_AI_MAX_TOKENS,
    ADMIN_BROADCAST_MESSAGE,
    ADMIN_BAN_USER,
    ADMIN_UNBAN_USER,
    ADMIN_SET_WELCOME,
) = range(8)

# Pagination constants
ITEMS_PER_PAGE = 10
MAX_CALLBACK_DATA_LENGTH = 64


class BotHandlers:
    """Main handler class for all Telegram bot interactions."""

    def __init__(
        self,
        db: Database,
        config: Config,
        deepseek_client: DeepSeekClient,
        rate_limiter: RateLimiter,
        i18n: I18n,
    ):
        """Initialize handlers with required dependencies.

        Args:
            db: Database instance for data persistence
            config: Bot configuration
            deepseek_client: DeepSeek API client
            rate_limiter: Rate limiting service
            i18n: Internationalization service
        """
        self.db = db
        self.config = config
        self.deepseek_client = deepseek_client
        self.rate_limiter = rate_limiter
        self.i18n = i18n

        # Store active conversations for context
        self.active_conversations: Dict[int, List[Dict]] = {}

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command - welcome message and registration.

        Args:
            update: Telegram update object
            context: Callback context
        """
        user = update.effective_user
        chat = update.effective_chat

        if not user or not chat:
            return

        # Register user if not exists
        user_profile = await self.db.get_user(user.id)
        if not user_profile:
            user_profile = UserProfile(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code or "en",
                registered_at=datetime.utcnow(),
            )
            await self.db.create_user(user_profile)
            logger.info(f"New user registered: {user.id} ({user.username})")

        # Get localized welcome message
        lang = user_profile.language_code or "en"
        welcome_text = self.i18n.get_text("welcome_message", lang).format(
            first_name=escape_markdown(user.first_name or "User", version=2),
            bot_name=escape_markdown(context.bot.first_name or "Bot", version=2),
        )

        # Create inline keyboard with main menu options
        keyboard = [
            [
                InlineKeyboardButton(
                    self.i18n.get_text("button_chat", lang),
                    callback_data="start_chat",
                ),
                InlineKeyboardButton(
                    self.i18n.get_text("button_profile", lang),
                    callback_data="view_profile",
                ),
            ],
            [
                InlineKeyboardButton(
                    self.i18n.get_text("button_settings", lang),
                    callback_data="settings_menu",
                ),
                InlineKeyboardButton(
                    self.i18n.get_text("button_help", lang),
                    callback_data="help_menu",
                ),
            ],
        ]

        # Add admin button if user is admin
        if user.id in self.config.admin_ids:
            keyboard.append([
                InlineKeyboardButton(
                    self.i18n.get_text("button_admin", lang),
                    callback_data="admin_menu",
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup,
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command - show available commands and features.

        Args:
            update: Telegram update object
            context: Callback context
        """
        user = update.effective_user
        if not user:
            return

        user_profile = await self.db.get_user(user.id)
        lang = user_profile.language_code if user_profile else "en"

        help_text = self.i18n.get_text("help_text", lang)
        commands_text = self.i18n.get_text("available_commands", lang)

        await update.message.reply_text(
            f"{help_text}\n\n{commands_text}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /settings command - show settings menu.

        Args:
            update: Telegram update object
            context: Callback context

        Returns:
            Next conversation state
        """
        user = update.effective_user
        if not user:
            return ConversationHandler.END

        user_profile = await self.db.get_user(user.id)
        lang = user_profile.language_code if user_profile else "en"

        keyboard = [
            [
                InlineKeyboardButton(
                    self.i18n.get_text("button_language", lang),
                    callback_data="set_language",
                ),
                InlineKeyboardButton(
                    self.i18n.get_text("button_ai_model", lang),
                    callback_data="set_ai_model",
                ),
            ],
            [
                InlineKeyboardButton(
                    self.i18n.get_text("button_temperature", lang),
                    callback_data="set_temperature",
                ),
                InlineKeyboardButton(
                    self.i18n.get_text("button_max_tokens", lang),
                    callback_data="set_max_tokens",
                ),
            ],
            [
                InlineKeyboardButton(
                    self.i18n.get_text("button_back", lang),
                    callback_data="main_menu",
                ),
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            self.i18n.get_text("settings_menu", lang),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup,
        )

        return ConversationHandler.END

    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /profile command - show user profile information.

        Args:
            update: Telegram update object
            context: Callback context
        """
        user = update.effective_user
        if not user:
            return

        user_profile = await self.db.get_user(user.id)
        if not user_profile:
            await update.message.reply_text(
                self.i18n.get_text("user_not_found", "en")
            )
            return

        lang = user_profile.language_code or "en"
        stats = await self.db.get_user_stats(user.id)

        profile_text = self.i18n.get_text("profile_info", lang).format(
            user_id=user.id,
            username=escape_markdown(user.username or "N/A", version=2),
            first_name=escape_markdown(user.first_name or "N/A", version=2),
            last_name=escape_markdown(user.last_name or "N/A", version=2),
            language=user_profile.language_code or "en",
            registered_at=user_profile.registered_at.strftime("%Y-%m-%d %H:%M"),
            total_messages=stats.get("total_messages", 0),
            total_tokens=stats.get("total_tokens", 0),
            is_banned=self.i18n.get_text("yes" if user_profile.is_banned else "no", lang),
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    self.i18n.get_text("button_edit_profile", lang),
                    callback_data="edit_profile",
                ),
                InlineKeyboardButton(
                    self.i18n.get_text("button_back", lang),
                    callback_data="main_menu",
                ),
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            profile_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup,
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming text messages - process AI chat requests.

        Args:
            update: Telegram update object
            context: Callback context
        """
        user = update.effective_user
        chat = update.effective_chat
        message = update.message

        if not user or not chat or not message:
            return

        # Check if user is banned
        user_profile = await self.db.get_user(user.id)
        if user_profile and user_profile.is_banned:
            await message.reply_text(
                self.i18n.get_text("user_banned", user_profile.language_code or "en")
            )
            return

        # Rate limiting check
        if not await self.rate_limiter.check_rate_limit(user.id):
            retry_after = await self.rate_limiter.get_retry_after(user.id)
            await message.reply_text(
                self.i18n.get_text("rate_limit_exceeded", user_profile.language_code or "en").format(
                    retry_after=retry_after
                )
            )
            return

        # Get user settings
        lang = user_profile.language_code if user_profile else "en"
        ai_settings = await self.db.get_ai_settings(user.id)

        # Show typing indicator
        await context.bot.send_chat_action(
            chat_id=chat.id,
            action=ChatAction.TYPING,
        )

        try:
            # Get conversation history for context
            conversation_history = self.active_conversations.get(user.id, [])
            
            # Add user message to history
            conversation_history.append({
                "role": "user",
                "content": message.text,
            })

            # Keep only last N messages for context window
            max_history = ai_settings.get("max_history", 10) if ai_settings else 10
            if len(conversation_history) > max_history * 2:
                conversation_history = conversation_history[-(max_history * 2):]

            # Generate AI response
            response = await self.deepseek_client.generate_response(
                messages=conversation_history,
                model=ai_settings.get("model", "deepseek-chat") if ai_settings else "deepseek-chat",
                temperature=ai_settings.get("temperature", 0.7) if ai_settings else 0.7,
                max_tokens=ai_settings.get("max_tokens", 2048) if ai_settings else 2048,
            )

            # Add assistant response to history
            conversation_history.append({
                "role": "assistant",
                "content": response,
            })
            self.active_conversations[user.id] = conversation_history

            # Save chat history to database
            await self.db.save_chat_history(
                ChatHistory(
                    user_id=user.id,
                    message=message.text,
                    response=response,
                    timestamp=datetime.utcnow(),
                    model=ai_settings.get("model", "deepseek-chat") if ai_settings else "deepseek-chat",
                    tokens_used=len(response.split()),  # Approximate token count
                )
            )

            # Send response with action buttons
            keyboard = [
                [
                    InlineKeyboardButton(
                        self.i18n.get_text("button_clear_history", lang),
                        callback_data="clear_history",
                    ),
                    InlineKeyboardButton(
                        self.i18n.get_text("button_new_chat", lang),
                        callback_data="new_chat",
                    ),
                ]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)

            # Split long messages
            if len(response) > 4096:
                for i in range(0, len(response), 4096):
                    await message.reply_text(
                        response[i:i + 4096],
                        parse_mode=ParseMode.MARKDOWN_V2,
                        reply_markup=reply_markup if i + 4096 >= len(response) else None,
                    )
            else:
                await message.reply_text(
                    response,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=reply_markup,
                )

        except Exception as e:
            logger.error(f"Error generating AI response for user {user.id}: {e}")
            await message.reply_text(
                self.i18n.get_text("error_generating_response", lang)
            )

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline keyboard callback queries.

        Args:
            update: Telegram update object
            context: Callback context
        """
        query = update.callback_query
        if not query or not query.data:
            return

        user = query.from_user
        if not user:
            return

        await query.answer()

        # Parse callback data
        data = query.data
        action, *params = data.split(":", 1)

        # Route to appropriate handler
        handlers = {
            "start_chat": self._handle_start_chat,
            "view_profile": self._handle_view_profile,
            "settings_menu": self._handle_settings_menu,
            "help_menu": self._handle_help_menu,
            "admin_menu": self._handle_admin_menu,
            "set_language": self._handle_set_language,
            "set_ai_model": self._handle_set_ai_model,
            "set_temperature": self._handle_set_temperature,
            "set_max_tokens": self._handle_set_max_tokens,
            "clear_history": self._handle_clear_history,
            "new_chat": self._handle_new_chat,
            "main_menu": self._handle_main_menu,
            "edit_profile": self._handle_edit_profile,
            "page": self._handle_pagination,
            "admin_broadcast": self._handle_admin_broadcast,
            "admin_ban": self._handle_admin_ban,
            "admin_unban": self._handle_admin_unban,
            "admin_stats": self._handle_admin_stats,
            "admin_users": self._handle_admin_users,
            "admin_settings": self._handle_admin_settings,
            "language_select": self._handle_language_select,
            "model_select": self._handle_model_select,
            "temperature_set": self._handle_temperature_set,
            "max_tokens_set": self._handle_max_tokens_set,
        }

        handler = handlers.get(action)
        if handler:
            await handler(query, context, params[0] if params else None)

    async def _handle_start_chat(self, query, context, params=None):
        """Handle start chat button - clear history and start fresh."""
        user = query.from_user
        self.active_conversations[user.id] = []
        lang = await self._get_user_lang(user.id)
        
        await query.edit_message_text(
            self.i18n.get_text("chat_started", lang),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _handle_view_profile(self, query, context, params=None):
        """Handle view profile button."""
        user = query.from_user
        user_profile = await self.db.get_user(user.id)
        if not user_profile:
            await query.edit_message_text(
                self.i18n.get_text("user_not_found", "en")
            )
            return

        lang = user_profile.language_code or "en"
        stats = await self.db.get_user_stats(user.id)

        profile_text = self.i18n.get_text("profile_info", lang).format(
            user_id=user.id,
            username=escape_markdown(user.username or "N/A", version=2),
            first_name=escape_markdown(user.first_name or "N/A", version=2),
            last_name=escape_markdown(user.last_name or "N/A", version=2),
            language=user_profile.language_code or "en",
            registered_at=user_profile.registered_at.strftime("%Y-%m-%d %H:%M"),
            total_messages=stats.get("total_messages", 0),
            total_tokens=stats.get("total_tokens", 0),
            is_banned=self.i18n.get_text("yes" if user_profile.is_banned else "no", lang),
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    self.i18n.get_text("button_edit_profile", lang),
                    callback_data="edit_profile",
                ),
                InlineKeyboardButton(
                    self.i18n.get_text("button_back", lang),
                    callback_data="main_menu",
                ),
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            profile_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup,
        )

    async def _handle_settings_menu(self, query, context, params=None):
        """Handle settings menu button."""
        user = query.from_user
        lang = await self._get_user_lang(user.id)

        keyboard = [
            [
                InlineKeyboardButton(
                    self.i18n.get_text("button_language", lang),
                    callback_data="set_language",
                ),
                InlineKeyboardButton(
                    self.i18n.get_text("button_ai_model", lang),
                    callback_data="set_ai_model",
                ),
            ],
            [
                InlineKeyboardButton(
                    self.i18n.get_text("button_temperature", lang),
                    callback