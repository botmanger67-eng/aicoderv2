"""
AI Chat Module - DeepSeek API integration for AI chat mode with context management.

This module handles all interactions with the DeepSeek API, including:
- Managing conversation contexts for different users
- Sending messages and receiving AI responses
- Handling API errors and rate limits
- Supporting multi-language responses
"""

import json
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

import aiohttp
import asyncio
from dataclasses import dataclass, field, asdict

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Represents a single message in the conversation context."""
    role: str  # 'user', 'assistant', or 'system'
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, str]:
        """Convert message to dictionary format for API request."""
        return {
            "role": self.role,
            "content": self.content
        }


@dataclass
class ConversationContext:
    """Manages conversation history for a specific user."""
    user_id: int
    messages: List[Message] = field(default_factory=list)
    max_context_length: int = 20  # Maximum number of messages to keep
    language: str = "en"
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation context."""
        message = Message(role=role, content=content)
        self.messages.append(message)
        self.last_activity = datetime.now()
        
        # Trim context if it exceeds maximum length
        if len(self.messages) > self.max_context_length:
            # Keep system messages and the most recent messages
            system_messages = [m for m in self.messages if m.role == "system"]
            recent_messages = [m for m in self.messages if m.role != "system"][-self.max_context_length + len(system_messages):]
            self.messages = system_messages + recent_messages

    def get_messages_for_api(self) -> List[Dict[str, str]]:
        """Get messages formatted for API request."""
        return [msg.to_dict() for msg in self.messages]

    def clear(self) -> None:
        """Clear conversation history except system messages."""
        self.messages = [m for m in self.messages if m.role == "system"]
        self.last_activity = datetime.now()

    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """Check if conversation context has expired due to inactivity."""
        return datetime.now() - self.last_activity > timedelta(minutes=timeout_minutes)


class DeepSeekAPIClient:
    """
    Client for interacting with the DeepSeek API.
    
    Handles authentication, request sending, response parsing,
    error handling, and rate limiting.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        rate_limit_rpm: int = 60,
        timeout: int = 30
    ):
        """
        Initialize the DeepSeek API client.

        Args:
            api_key: DeepSeek API key
            base_url: Base URL for API requests
            model: Model name to use
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            rate_limit_rpm: Maximum requests per minute
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        
        # Rate limiting
        self.rate_limit_rpm = rate_limit_rpm
        self.request_timestamps: List[float] = []
        
        # Session management
        self._session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"DeepSeek API client initialized with model: {model}")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting."""
        now = time.time()
        # Remove timestamps older than 1 minute
        self.request_timestamps = [t for t in self.request_timestamps if now - t < 60]
        
        if len(self.request_timestamps) >= self.rate_limit_rpm:
            # Calculate wait time
            oldest = min(self.request_timestamps)
            wait_time = 60 - (now - oldest)
            if wait_time > 0:
                logger.warning(f"Rate limit reached, waiting {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)
        
        self.request_timestamps.append(now)

    async def send_message(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Send a message to the DeepSeek API and get response.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Response creativity (0.0 to 1.0)
            max_tokens: Maximum tokens in response
            stream: Whether to stream the response

        Returns:
            API response dictionary

        Raises:
            aiohttp.ClientError: On network errors
            ValueError: On invalid API responses
            Exception: On other errors
        """
        await self._check_rate_limit()
        
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                session = await self._get_session()
                
                async with session.post(url, json=payload) as response:
                    if response.status == 429:  # Too Many Requests
                        retry_after = int(response.headers.get("Retry-After", self.retry_delay))
                        logger.warning(f"Rate limited, retrying after {retry_after} seconds")
                        await asyncio.sleep(retry_after)
                        continue
                    
                    if response.status == 401:
                        raise ValueError("Invalid API key")
                    
                    if response.status == 400:
                        error_data = await response.json()
                        raise ValueError(f"Bad request: {error_data.get('error', {}).get('message', 'Unknown error')}")
                    
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"API error {response.status}: {error_text}")
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                            continue
                        raise Exception(f"API returned status {response.status}: {error_text}")
                    
                    response_data = await response.json()
                    
                    # Validate response structure
                    if "choices" not in response_data or not response_data["choices"]:
                        raise ValueError("Invalid API response: no choices returned")
                    
                    logger.debug(f"API response received successfully")
                    return response_data

            except aiohttp.ClientError as e:
                last_error = e
                logger.error(f"Network error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise
            except asyncio.TimeoutError:
                last_error = "Request timeout"
                logger.error(f"Timeout on attempt {attempt + 1}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise Exception("Request timed out after all retries")
        
        raise Exception(f"Failed to get API response after {self.max_retries} attempts: {last_error}")

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("API session closed")


class AIChatManager:
    """
    Manages AI chat sessions and conversation contexts for multiple users.
    
    Features:
    - Per-user conversation context management
    - Automatic context expiration
    - Multi-language support
    - Error handling and logging
    """

    def __init__(self, api_client: DeepSeekAPIClient, context_timeout_minutes: int = 30):
        """
        Initialize the AI chat manager.

        Args:
            api_client: DeepSeek API client instance
            context_timeout_minutes: Minutes of inactivity before context expires
        """
        self.api_client = api_client
        self.context_timeout_minutes = context_timeout_minutes
        self.contexts: Dict[int, ConversationContext] = {}
        
        # System prompts for different languages
        self.system_prompts = {
            "en": "You are a helpful AI assistant. Respond in English.",
            "ru": "Вы - полезный AI-ассистент. Отвечайте на русском языке.",
            "es": "Eres un asistente AI útil. Responde en español.",
            "fr": "Vous êtes un assistant AI utile. Répondez en français.",
            "de": "Sie sind ein hilfreicher KI-Assistent. Antworten Sie auf Deutsch.",
            "zh": "你是一个有用的AI助手。请用中文回答。",
            "ja": "あなたは役立つAIアシスタントです。日本語で回答してください。",
            "ar": "أنت مساعد AI مفيد. أجب باللغة العربية.",
            "pt": "Você é um assistente AI útil. Responda em português.",
            "it": "Sei un assistente AI utile. Rispondi in italiano."
        }
        
        logger.info(f"AI Chat Manager initialized with {len(self.system_prompts)} languages")

    def get_or_create_context(self, user_id: int, language: str = "en") -> ConversationContext:
        """
        Get existing context for a user or create a new one.

        Args:
            user_id: Telegram user ID
            language: User's language code

        Returns:
            ConversationContext instance
        """
        # Clean up expired contexts
        self._cleanup_expired_contexts()
        
        if user_id not in self.contexts:
            context = ConversationContext(
                user_id=user_id,
                language=language
            )
            # Add system prompt
            system_prompt = self.system_prompts.get(language, self.system_prompts["en"])
            context.add_message("system", system_prompt)
            self.contexts[user_id] = context
            logger.info(f"Created new context for user {user_id} with language {language}")
        else:
            context = self.contexts[user_id]
            # Update language if changed
            if context.language != language:
                context.language = language
                # Update system prompt
                system_prompt = self.system_prompts.get(language, self.system_prompts["en"])
                # Remove old system messages and add new one
                context.messages = [m for m in context.messages if m.role != "system"]
                context.add_message("system", system_prompt)
                logger.info(f"Updated language for user {user_id} to {language}")
        
        return context

    def _cleanup_expired_contexts(self) -> None:
        """Remove expired conversation contexts."""
        expired_users = [
            user_id for user_id, context in self.contexts.items()
            if context.is_expired(self.context_timeout_minutes)
        ]
        for user_id in expired_users:
            del self.contexts[user_id]
            logger.info(f"Removed expired context for user {user_id}")

    async def process_message(
        self,
        user_id: int,
        message_text: str,
        language: str = "en",
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        Process a user message and get AI response.

        Args:
            user_id: Telegram user ID
            message_text: User's message text
            language: User's language code
            temperature: Response creativity
            max_tokens: Maximum tokens in response

        Returns:
            AI response text

        Raises:
            ValueError: On invalid input
            Exception: On API errors
        """
        if not message_text or not message_text.strip():
            raise ValueError("Message text cannot be empty")

        # Get or create conversation context
        context = self.get_or_create_context(user_id, language)
        
        # Add user message to context
        context.add_message("user", message_text)
        
        try:
            # Get messages for API request
            messages = context.get_messages_for_api()
            
            # Send to API
            response = await self.api_client.send_message(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Extract response text
            if response.get("choices") and len(response["choices"]) > 0:
                ai_response = response["choices"][0].get("message", {}).get("content", "")
                
                if not ai_response:
                    logger.error("Empty AI response received")
                    return "I apologize, but I couldn't generate a response. Please try again."
                
                # Add AI response to context
                context.add_message("assistant", ai_response)
                
                logger.info(f"Successfully processed message for user {user_id}")
                return ai_response
            else:
                logger.error("Invalid API response structure")
                return "I encountered an error processing your request. Please try again later."
                
        except ValueError as e:
            logger.error(f"Value error processing message for user {user_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error processing message for user {user_id}: {e}")
            return "I'm sorry, but I encountered an error. Please try again later."

    def clear_context(self, user_id: int) -> bool:
        """
        Clear conversation context for a user.

        Args:
            user_id: Telegram user ID

        Returns:
            True if context was cleared, False if no context exists
        """
        if user_id in self.contexts:
            self.contexts[user_id].clear()
            logger.info(f"Cleared context for user {user_id}")
            return True
        return False

    def delete_context(self, user_id: int) -> bool:
        """
        Delete conversation context for a user entirely.

        Args:
            user_id: Telegram user ID

        Returns:
            True if context was deleted, False if no context exists
        """
        if user_id in self.contexts:
            del self.contexts[user_id]
            logger.info(f"Deleted context for user {user_id}")
            return True
        return False

    def get_context_stats(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get statistics about a user's conversation context.

        Args:
            user_id: Telegram user ID

        Returns:
            Dictionary with context statistics or None if no context exists
        """
        if user_id not in self.contexts:
            return None
        
        context = self.contexts[user_id]
        return {
            "user_id": context.user_id,
            "language": context.language,
            "message_count": len(context.messages),
            "created_at": context.created_at.isoformat(),
            "last_activity": context.last_activity.isoformat(),
            "is_expired": context.is_expired(self.context_timeout_minutes)
        }

    async def close(self) -> None:
        """Clean up resources."""
        await self.api_client.close()
        self.contexts.clear()
        logger.info("AI Chat Manager closed")


# Factory function for creating AI chat manager
def create_ai_chat_manager(
    api_key: str,
    model: str = "deepseek-chat",
    context_timeout_minutes: int = 30,
    rate_limit_rpm: int = 60
) -> AIChatManager:
    """
    Create and configure an AI chat manager instance.

    Args:
        api_key: DeepSeek API key
        model: Model name to use
        context_timeout_minutes: Minutes of inactivity before context expires
        rate_limit_rpm: Maximum requests per minute

    Returns:
        Configured AIChatManager instance
    """
    api_client = DeepSeekAPIClient(
        api_key=api_key,
        model=model,
        rate_limit_rpm=rate_limit_rpm
    )
    
    return AIChatManager(
        api_client=api_client,
        context_timeout_minutes=context_timeout_minutes
    )