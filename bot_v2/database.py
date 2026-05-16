"""
Database operations for the Telegram bot using SQLite with async connection pooling.
Provides CRUD operations for users, conversations, and admin settings.
"""

import sqlite3
import asyncio
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class DatabasePool:
    """
    Async connection pool for SQLite database.
    Manages a pool of connections to handle concurrent database operations.
    """

    def __init__(self, db_path: str, max_connections: int = 10):
        """
        Initialize the database pool.

        Args:
            db_path: Path to the SQLite database file
            max_connections: Maximum number of connections in the pool
        """
        self.db_path = Path(db_path)
        self.max_connections = max_connections
        self._pool: asyncio.Queue = asyncio.Queue(maxsize=max_connections)
        self._initialized = False

    async def initialize(self):
        """Create the database file and initialize the connection pool."""
        if self._initialized:
            return

        # Ensure the directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create initial connections
        for _ in range(self.max_connections):
            conn = await self._create_connection()
            await self._pool.put(conn)

        self._initialized = True
        logger.info(f"Database pool initialized with {self.max_connections} connections")

    async def _create_connection(self) -> sqlite3.Connection:
        """
        Create a new SQLite connection with optimized settings.

        Returns:
            A configured SQLite connection object
        """
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=30,
            isolation_level=None  # Enable autocommit mode
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @asynccontextmanager
    async def get_connection(self) -> sqlite3.Connection:
        """
        Get a connection from the pool with context manager support.

        Yields:
            A SQLite connection from the pool
        """
        if not self._initialized:
            await self.initialize()

        conn = await self._pool.get()
        try:
            yield conn
        finally:
            await self._pool.put(conn)

    async def close(self):
        """Close all connections in the pool."""
        while not self._pool.empty():
            conn = await self._pool.get()
            conn.close()
        self._initialized = False
        logger.info("Database pool closed")


class Database:
    """
    Main database handler providing CRUD operations for the bot.
    Uses the connection pool for async database access.
    """

    def __init__(self, db_path: str = "data/bot.db"):
        """
        Initialize the database handler.

        Args:
            db_path: Path to the SQLite database file
        """
        self.pool = DatabasePool(db_path)
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize the database and create tables if they don't exist."""
        await self.pool.initialize()
        await self._create_tables()

    async def _create_tables(self):
        """Create all required database tables."""
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()

            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT DEFAULT 'en',
                    is_admin INTEGER DEFAULT 0,
                    is_banned INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Conversations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    tokens_used INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)

            # Admin settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Rate limiting table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    user_id INTEGER NOT NULL,
                    endpoint TEXT NOT NULL,
                    request_count INTEGER DEFAULT 1,
                    window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, endpoint),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)

            # User preferences table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id INTEGER PRIMARY KEY,
                    theme TEXT DEFAULT 'light',
                    notifications_enabled INTEGER DEFAULT 1,
                    auto_translate INTEGER DEFAULT 0,
                    preferred_language TEXT DEFAULT 'en',
                    max_tokens INTEGER DEFAULT 2048,
                    temperature REAL DEFAULT 0.7,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)

            # Create indexes for better performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_user_id 
                ON conversations(user_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_created_at 
                ON conversations(created_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_rate_limits_window 
                ON rate_limits(window_start)
            """)

            conn.commit()
            logger.info("Database tables created successfully")

    # User operations
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a user by their Telegram user ID.

        Args:
            user_id: Telegram user ID

        Returns:
            User data as dictionary or None if not found
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    async def create_or_update_user(self, user_id: int, username: str = None,
                                     first_name: str = None, last_name: str = None,
                                     language_code: str = 'en') -> Dict[str, Any]:
        """
        Create a new user or update existing user information.

        Args:
            user_id: Telegram user ID
            username: Telegram username
            first_name: User's first name
            last_name: User's last name
            language_code: User's language code

        Returns:
            Updated user data as dictionary
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, language_code)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = COALESCE(?, username),
                    first_name = COALESCE(?, first_name),
                    last_name = COALESCE(?, last_name),
                    language_code = COALESCE(?, language_code),
                    updated_at = CURRENT_TIMESTAMP
            """, (user_id, username, first_name, last_name, language_code,
                  username, first_name, last_name, language_code))
            conn.commit()

            # Also create default preferences if not exists
            cursor.execute("""
                INSERT OR IGNORE INTO user_preferences (user_id)
                VALUES (?)
            """, (user_id,))
            conn.commit()

            return await self.get_user(user_id)

    async def get_all_users(self, page: int = 1, per_page: int = 50) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get paginated list of all users.

        Args:
            page: Page number (1-indexed)
            per_page: Number of users per page

        Returns:
            Tuple of (list of users, total count)
        """
        offset = (page - 1) * per_page
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            total = cursor.fetchone()[0]

            cursor.execute("""
                SELECT * FROM users 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """, (per_page, offset))
            rows = cursor.fetchall()
            return [dict(row) for row in rows], total

    async def ban_user(self, user_id: int) -> bool:
        """
        Ban a user from using the bot.

        Args:
            user_id: Telegram user ID

        Returns:
            True if successful, False if user not found
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET is_banned = 1, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (user_id,))
            conn.commit()
            return cursor.rowcount > 0

    async def unban_user(self, user_id: int) -> bool:
        """
        Unban a user.

        Args:
            user_id: Telegram user ID

        Returns:
            True if successful, False if user not found
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET is_banned = 0, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (user_id,))
            conn.commit()
            return cursor.rowcount > 0

    async def set_admin(self, user_id: int, is_admin: bool = True) -> bool:
        """
        Set or remove admin status for a user.

        Args:
            user_id: Telegram user ID
            is_admin: Whether the user should be an admin

        Returns:
            True if successful, False if user not found
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET is_admin = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (1 if is_admin else 0, user_id))
            conn.commit()
            return cursor.rowcount > 0

    # Conversation operations
    async def add_conversation_message(self, user_id: int, role: str,
                                        content: str, tokens_used: int = 0) -> int:
        """
        Add a message to the conversation history.

        Args:
            user_id: Telegram user ID
            role: Message role ('user', 'assistant', or 'system')
            content: Message content
            tokens_used: Number of tokens used (for tracking usage)

        Returns:
            ID of the inserted message
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO conversations (user_id, role, content, tokens_used)
                VALUES (?, ?, ?, ?)
            """, (user_id, role, content, tokens_used))
            conn.commit()
            return cursor.lastrowid

    async def get_conversation_history(self, user_id: int,
                                        limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get conversation history for a user.

        Args:
            user_id: Telegram user ID
            limit: Maximum number of messages to retrieve

        Returns:
            List of conversation messages
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM conversations 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (user_id, limit))
            rows = cursor.fetchall()
            return [dict(row) for row in reversed(rows)]

    async def clear_conversation_history(self, user_id: int) -> int:
        """
        Clear all conversation history for a user.

        Args:
            user_id: Telegram user ID

        Returns:
            Number of deleted messages
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount

    async def get_total_tokens_used(self, user_id: int) -> int:
        """
        Get total tokens used by a user across all conversations.

        Args:
            user_id: Telegram user ID

        Returns:
            Total tokens used
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(SUM(tokens_used), 0) as total_tokens
                FROM conversations WHERE user_id = ?
            """, (user_id,))
            row = cursor.fetchone()
            return row['total_tokens']

    # Admin settings operations
    async def get_setting(self, key: str, default: Any = None) -> Optional[str]:
        """
        Get an admin setting value.

        Args:
            key: Setting key
            default: Default value if setting not found

        Returns:
            Setting value or default
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM admin_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row['value'] if row else default

    async def set_setting(self, key: str, value: str) -> bool:
        """
        Set an admin setting value.

        Args:
            key: Setting key
            value: Setting value

        Returns:
            True if successful
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO admin_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = ?,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, value, value))
            conn.commit()
            return True

    async def get_all_settings(self) -> Dict[str, str]:
        """
        Get all admin settings.

        Returns:
            Dictionary of all settings
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM admin_settings")
            rows = cursor.fetchall()
            return {row['key']: row['value'] for row in rows}

    # Rate limiting operations
    async def check_rate_limit(self, user_id: int, endpoint: str,
                                max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Check if a user has exceeded their rate limit.

        Args:
            user_id: Telegram user ID
            endpoint: API endpoint being accessed
            max_requests: Maximum allowed requests in the time window
            window_seconds: Time window in seconds

        Returns:
            Tuple of (is_allowed, current_request_count)
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()

            # Clean up old rate limit entries
            cursor.execute("""
                DELETE FROM rate_limits 
                WHERE window_start < datetime('now', ? || ' seconds')
            """, (f"-{window_seconds}",))

            # Check current rate limit
            cursor.execute("""
                SELECT request_count, window_start 
                FROM rate_limits 
                WHERE user_id = ? AND endpoint = ?
            """, (user_id, endpoint))
            row = cursor.fetchone()

            if row:
                request_count = row['request_count']
                if request_count >= max_requests:
                    return False, request_count

                # Increment request count
                cursor.execute("""
                    UPDATE rate_limits 
                    SET request_count = request_count + 1 
                    WHERE user_id = ? AND endpoint = ?
                """, (user_id, endpoint))
            else:
                # Create new rate limit entry
                cursor.execute("""
                    INSERT INTO rate_limits (user_id, endpoint, request_count)
                    VALUES (?, ?, 1)
                """, (user_id, endpoint))
                request_count = 1

            conn.commit()
            return True, request_count + 1

    # User preferences operations
    async def get_user_preferences(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user preferences.

        Args:
            user_id: Telegram user ID

        Returns:
            User preferences as dictionary or None
        """
        async with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    async def update_user_preferences(self, user_id: int, **kwargs) -> bool:
        """
        Update user preferences.

        Args:
            user_id: Telegram user ID
            **kwargs: Preference fields to update

        Returns:
            True if successful
        """
        allowed_fields = {'theme', 'notifications_enabled', 'auto_translate',
                         'preferred_language', 'max_tokens', 'temperature'}

        update_fields = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not update_fields:
            return False

        set_clause = ", ".join([f"{k} = ?" for k in update_fields.keys()])
        set_clause += ", updated_at = CURRENT_TIMESTAMP"

        values = list(update_fields.values()) + [user_id]

        async with self.pool.get_connection()