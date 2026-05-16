"""
Admin module for Telegram bot.
Provides administrative features: broadcast, stats, block/unblock, export CSV.
"""

import csv
import io
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

from database import Database
from config import Config
from utils import is_admin, format_number, get_user_language

logger = logging.getLogger(__name__)

# Conversation states
BROADCAST_TEXT = 1
BROADCAST_CONFIRM = 2
BLOCK_USER_ID = 3
UNBLOCK_USER_ID = 4

class AdminHandler:
    """Handler for admin commands and features."""

    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Display bot statistics."""
        if not await is_admin(update, context, self.config):
            return

        try:
            stats = await self.db.get_stats()
            user_lang = await get_user_language(update, context, self.db)
            
            text = (
                f"📊 *Bot Statistics*\n\n"
                f"👥 Total Users: `{format_number(stats['total_users'])}`\n"
                f"✅ Active Users: `{format_number(stats['active_users'])}`\n"
                f"🚫 Blocked Users: `{format_number(stats['blocked_users'])}`\n"
                f"💬 Total Messages: `{format_number(stats['total_messages'])}`\n"
                f"📅 Messages Today: `{format_number(stats['messages_today'])}`\n"
                f"📈 Messages This Week: `{format_number(stats['messages_week'])}`\n"
                f"📊 Messages This Month: `{format_number(stats['messages_month'])}`\n"
                f"⚡ Active Now (24h): `{format_number(stats['active_24h'])}`\n"
                f"🆕 New Users (24h): `{format_number(stats['new_users_24h'])}`\n"
                f"📅 Bot Uptime: `{stats['uptime']}`\n"
                f"💾 Database Size: `{stats['db_size']}`\n"
            )
            
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}", exc_info=True)
            await update.message.reply_text("❌ Failed to retrieve statistics.")

    async def broadcast_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start broadcast conversation."""
        if not await is_admin(update, context, self.config):
            return ConversationHandler.END

        await update.message.reply_text(
            "📢 *Broadcast Message*\n\n"
            "Send me the message you want to broadcast to all users.\n"
            "You can use Markdown formatting.\n\n"
            "Send /cancel to abort.",
            parse_mode=ParseMode.MARKDOWN
        )
        return BROADCAST_TEXT

    async def broadcast_receive_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receive broadcast message text."""
        context.user_data['broadcast_text'] = update.message.text
        context.user_data['broadcast_entities'] = update.message.parse_entities()
        
        # Show preview
        preview = update.message.text[:200] + "..." if len(update.message.text) > 200 else update.message.text
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Send", callback_data="broadcast_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📢 *Broadcast Preview*\n\n"
            f"{preview}\n\n"
            f"*Total characters:* {len(update.message.text)}\n\n"
            f"Do you want to send this message to all users?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        return BROADCAST_CONFIRM

    async def broadcast_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Confirm and execute broadcast."""
        query = update.callback_query
        await query.answer()
        
        if query.data == "broadcast_cancel":
            await query.edit_message_text("❌ Broadcast cancelled.")
            return ConversationHandler.END
        
        if query.data == "broadcast_confirm":
            await query.edit_message_text("📤 Broadcasting message...")
            
            try:
                text = context.user_data.get('broadcast_text', '')
                entities = context.user_data.get('broadcast_entities', {})
                
                # Get all active users
                users = await self.db.get_all_active_users()
                total = len(users)
                success = 0
                failed = 0
                
                for user_id in users:
                    try:
                        if entities:
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=text,
                                entities=entities,
                                parse_mode=ParseMode.MARKDOWN
                            )
                        else:
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=text,
                                parse_mode=ParseMode.MARKDOWN
                            )
                        success += 1
                    except Exception as e:
                        logger.warning(f"Failed to send broadcast to {user_id}: {e}")
                        failed += 1
                    
                    # Rate limiting - small delay to avoid flood
                    if success % 20 == 0:
                        await asyncio.sleep(0.5)
                
                # Log broadcast
                await self.db.log_broadcast(
                    admin_id=update.effective_user.id,
                    message_length=len(text),
                    total_users=total,
                    success_count=success,
                    failed_count=failed
                )
                
                await query.edit_message_text(
                    f"✅ *Broadcast Complete*\n\n"
                    f"📊 Results:\n"
                    f"• Total users: {total}\n"
                    f"• Successfully sent: {success}\n"
                    f"• Failed: {failed}\n"
                    f"• Success rate: {(success/total*100):.1f}%",
                    parse_mode=ParseMode.MARKDOWN
                )
                
            except Exception as e:
                logger.error(f"Broadcast error: {e}", exc_info=True)
                await query.edit_message_text("❌ Broadcast failed. Please try again.")
            
            # Clean up
            context.user_data.pop('broadcast_text', None)
            context.user_data.pop('broadcast_entities', None)
            
            return ConversationHandler.END

    async def broadcast_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel broadcast."""
        await update.message.reply_text("❌ Broadcast cancelled.")
        return ConversationHandler.END

    async def block_user_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start block user conversation."""
        if not await is_admin(update, context, self.config):
            return ConversationHandler.END

        await update.message.reply_text(
            "🚫 *Block User*\n\n"
            "Send me the user ID or username (with @) of the user you want to block.\n\n"
            "Send /cancel to abort.",
            parse_mode=ParseMode.MARKDOWN
        )
        return BLOCK_USER_ID

    async def block_user_receive(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receive user ID/username to block."""
        user_input = update.message.text.strip()
        
        # Extract user ID from input
        user_id = None
        if user_input.startswith('@'):
            # Username provided
            username = user_input[1:]
            user_id = await self.db.get_user_id_by_username(username)
            if not user_id:
                await update.message.reply_text(
                    f"❌ User '{user_input}' not found in database.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ConversationHandler.END
        else:
            try:
                user_id = int(user_input)
            except ValueError:
                await update.message.reply_text(
                    "❌ Invalid input. Please provide a valid user ID or username (with @).",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ConversationHandler.END
        
        # Check if user exists
        user = await self.db.get_user(user_id)
        if not user:
            await update.message.reply_text(
                f"❌ User ID {user_id} not found in database.",
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationHandler.END
        
        # Check if already blocked
        if user.get('is_blocked', False):
            await update.message.reply_text(
                f"ℹ️ User {user_id} is already blocked.",
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationHandler.END
        
        # Block user
        try:
            await self.db.block_user(user_id, blocked_by=update.effective_user.id)
            
            # Notify user if possible
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🚫 You have been blocked from using this bot. If you believe this is a mistake, please contact support."
                )
            except:
                pass
            
            await update.message.reply_text(
                f"✅ User {user_id} has been blocked successfully.\n"
                f"User info: {user.get('first_name', 'N/A')} {user.get('last_name', '')} (@{user.get('username', 'N/A')})",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Error blocking user {user_id}: {e}", exc_info=True)
            await update.message.reply_text("❌ Failed to block user. Please try again.")
        
        return ConversationHandler.END

    async def unblock_user_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start unblock user conversation."""
        if not await is_admin(update, context, self.config):
            return ConversationHandler.END

        await update.message.reply_text(
            "🔓 *Unblock User*\n\n"
            "Send me the user ID or username (with @) of the user you want to unblock.\n\n"
            "Send /cancel to abort.",
            parse_mode=ParseMode.MARKDOWN
        )
        return UNBLOCK_USER_ID

    async def unblock_user_receive(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receive user ID/username to unblock."""
        user_input = update.message.text.strip()
        
        # Extract user ID from input
        user_id = None
        if user_input.startswith('@'):
            # Username provided
            username = user_input[1:]
            user_id = await self.db.get_user_id_by_username(username)
            if not user_id:
                await update.message.reply_text(
                    f"❌ User '{user_input}' not found in database.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ConversationHandler.END
        else:
            try:
                user_id = int(user_input)
            except ValueError:
                await update.message.reply_text(
                    "❌ Invalid input. Please provide a valid user ID or username (with @).",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ConversationHandler.END
        
        # Check if user exists
        user = await self.db.get_user(user_id)
        if not user:
            await update.message.reply_text(
                f"❌ User ID {user_id} not found in database.",
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationHandler.END
        
        # Check if already unblocked
        if not user.get('is_blocked', False):
            await update.message.reply_text(
                f"ℹ️ User {user_id} is not blocked.",
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationHandler.END
        
        # Unblock user
        try:
            await self.db.unblock_user(user_id)
            
            # Notify user
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="✅ You have been unblocked and can now use the bot again."
                )
            except:
                pass
            
            await update.message.reply_text(
                f"✅ User {user_id} has been unblocked successfully.\n"
                f"User info: {user.get('first_name', 'N/A')} {user.get('last_name', '')} (@{user.get('username', 'N/A')})",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Error unblocking user {user_id}: {e}", exc_info=True)
            await update.message.reply_text("❌ Failed to unblock user. Please try again.")
        
        return ConversationHandler.END

    async def export_csv_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Export users data as CSV file."""
        if not await is_admin(update, context, self.config):
            return

        try:
            await update.message.reply_text("📊 Generating CSV export...")
            
            # Get all users
            users = await self.db.get_all_users()
            
            # Create CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                'User ID',
                'Username',
                'First Name',
                'Last Name',
                'Language',
                'Is Blocked',
                'Is Admin',
                'Total Messages',
                'First Seen',
                'Last Active',
                'Registration Date'
            ])
            
            # Write user data
            for user in users:
                writer.writerow([
                    user.get('user_id', ''),
                    user.get('username', ''),
                    user.get('first_name', ''),
                    user.get('last_name', ''),
                    user.get('language', 'en'),
                    'Yes' if user.get('is_blocked', False) else 'No',
                    'Yes' if user.get('is_admin', False) else 'No',
                    user.get('total_messages', 0),
                    user.get('first_seen', ''),
                    user.get('last_active', ''),
                    user.get('registration_date', '')
                ])
            
            # Prepare file for sending
            csv_content = output.getvalue()
            output.close()
            
            # Send as document
            await update.message.reply_document(
                document=io.BytesIO(csv_content.encode('utf-8')),
                filename=f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                caption=f"📊 Users Export - {len(users)} users"
            )
            
            # Log export
            await self.db.log_export(
                admin_id=update.effective_user.id,
                export_type='users',
                total_records=len(users)
            )
            
        except Exception as e:
            logger.error(f"Error exporting CSV: {e}", exc_info=True)
            await update.message.reply_text("❌ Failed to export CSV. Please try again.")

    async def export_messages_csv_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Export messages data as CSV file."""
        if not await is_admin(update, context, self.config):
            return

        try:
            await update.message.reply_text("📊 Generating messages CSV export...")
            
            # Get messages (last 10000 for performance)
            messages = await self.db.get_recent_messages(limit=10000)
            
            # Create CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                'Message ID',
                'User ID',
                'Username',
                'Message Type',
                'Message Content',
                'Token Count',
                'Response Time (s)',
                'Timestamp'
            ])
            
            # Write message data
            for msg in messages:
                writer.writerow([
                    msg.get('message_id', ''),
                    msg.get('user_id', ''),
                    msg.get('username', ''),
                    msg.get('message_type', ''),
                    msg.get('content', '')[:500] if msg.get('content') else '',  # Truncate long messages
                    msg.get('token_count', 0),
                    msg.get('response_time', 0),
                    msg.get('timestamp', '')
                ])
            
            # Prepare file for sending
            csv_content = output.getvalue()
            output.close()
            
            # Send as document
            await update.message.reply_document(
                document=io.BytesIO(csv_content.encode('utf-8')),
                filename=f"messages_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                caption=f"📊 Messages Export - {len(messages)} messages (last 10000)"
            )
            
            # Log export
            await self.db.log_export(
                admin_id=update.effective_user.id,
                export_type='messages',
                total_records=len(messages)
            )
            
        except Exception as e:
            logger.error(f"Error exporting messages CSV: {e}", exc_info=True)
            await update.message.reply_text("❌ Failed to export messages CSV. Please try again.")

    async def admin_help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show admin help."""
        if not await is_admin(update, context, self.config):
            return

        help_text = (
            "🛠 *Admin Commands*\