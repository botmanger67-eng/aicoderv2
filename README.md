# Advanced Telegram Bot V2

An advanced, feature-rich Telegram bot powered by AI, designed for seamless user interaction, robust administration, and scalable performance. Built with Python, the bot integrates the DeepSeek API for intelligent conversations, supports multi-language communication, and includes rate limiting to ensure fair usage. Data is stored efficiently using SQLite with asynchronous support via aiosqlite.

## Features

- **AI-Powered Chat** – Engage users with intelligent responses using the DeepSeek API.
- **User Profiles** – Store and manage user-specific data and preferences.
- **Admin Features** – Dedicated commands and controls for bot administrators.
- **Multi-Language Support** – Automatically detect and respond in the user's language.
- **Rate Limiting** – Prevent spam and abuse with configurable rate limits.
- **Asynchronous Performance** – Built with `python-telegram-bot` and `aiosqlite` for non-blocking operations.
- **Persistent Storage** – All data stored locally in SQLite for reliability and simplicity.

## Installation

### Prerequisites

- Python 3.8 or higher
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- DeepSeek API Key

### Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/advanced-telegram-bot-v2.git
   cd advanced-telegram-bot-v2
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   Create a `.env` file in the project root:
   ```env
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   DEEPSEEK_API_KEY=your_deepseek_api_key
   ADMIN_USER_IDS=123456789,987654321  # Comma-separated Telegram user IDs
   RATE_LIMIT_PER_MINUTE=10
   ```

5. **Initialize the database**
   ```bash
   python init_db.py
   ```

6. **Run the bot**
   ```bash
   python bot.py
   ```

## Usage

### Starting the Bot

1. Open Telegram and search for your bot by username.
2. Send `/start` to initialize the conversation.
3. Use `/help` to see available commands.

### Example Commands

| Command | Description |
|---------|-------------|
| `/start` | Initialize the bot and create a user profile |
| `/help` | Display help message with all commands |
| `/profile` | View your user profile and settings |
| `/language <code>` | Change language (e.g., `/language en`, `/language es`) |
| `/admin` | Access admin panel (admin only) |
| `/stats` | View bot statistics (admin only) |

### AI Chat Example

Simply send any message to the bot, and it will respond using the DeepSeek AI model. The bot automatically detects the language of your message and replies accordingly.

```
User: What's the weather like today?
Bot: I don't have real-time weather data, but I can help you find a weather service! Would you like me to search for one?
```

## Project Structure

```
advanced-telegram-bot-v2/
├── bot.py                  # Main bot entry point
├── config.py               # Configuration and environment variables
├── database/
│   ├── __init__.py
│   ├── db.py               # Database connection and initialization
│   └── models.py           # Data models and queries
├── handlers/
│   ├── __init__.py
│   ├── admin.py            # Admin command handlers
│   ├── chat.py             # AI chat handler
│   ├── language.py         # Language selection handler
│   └── profile.py          # User profile handlers
├── utils/
│   ├── __init__.py
│   ├── rate_limiter.py     # Rate limiting logic
│   └── language_detector.py # Language detection utility
├── requirements.txt        # Python dependencies
├── init_db.py              # Database initialization script
├── .env.example            # Example environment file
└── README.md               # Project documentation
```

## Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork the repository** and create your feature branch (`git checkout -b feature/amazing-feature`).
2. **Commit your changes** (`git commit -m 'Add some amazing feature'`).
3. **Push to the branch** (`git push origin feature/amazing-feature`).
4. **Open a Pull Request**.

### Development Setup

- Ensure all tests pass before submitting a PR.
- Follow PEP 8 style guidelines.
- Add appropriate documentation for new features.
- Update the `requirements.txt` if new dependencies are added.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

**Built with ❤️ using Python, python-telegram-bot, and DeepSeek API.**