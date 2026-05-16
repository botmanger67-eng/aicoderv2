# Bot v2 - Advanced Telegram Bot

An advanced Telegram bot with AI chat capabilities, user profiles, admin features, multi-language support, and rate limiting, powered by DeepSeek API and SQLite.

## Features

- 🤖 **AI Chat** - Intelligent conversations using DeepSeek API
- 👤 **User Profiles** - Track user activity and preferences
- 🔧 **Admin Panel** - Manage users, view statistics, and configure settings
- 🌍 **Multi-language** - Support for multiple languages (English, Spanish, French, German, etc.)
- ⚡ **Rate Limiting** - Prevent spam and abuse
- 💾 **SQLite Database** - Lightweight and efficient data storage
- 🔄 **Async Operations** - Non-blocking I/O for better performance

## Prerequisites

- Python 3.8 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- DeepSeek API Key

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/bot_v2.git
cd bot_v2
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the root directory or set environment variables:

```env
# Required
BOT_TOKEN=your_telegram_bot_token_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here

# Optional
ADMIN_IDS=123456789,987654321  # Comma-separated Telegram user IDs
DATABASE_PATH=bot_database.db   # Path to SQLite database file
LOG_LEVEL=INFO                  # DEBUG, INFO, WARNING, ERROR
```

## Replit Deployment

### Setting Up Secrets in Replit

1. Open your Replit project
2. Click on the **Lock icon** (Secrets) in the left sidebar
3. Add the following secrets:

| Key | Value | Description |
|-----|-------|-------------|
| `BOT_TOKEN` | `your_telegram_bot_token` | Your bot token from BotFather |
| `DEEPSEEK_API_KEY` | `your_deepseek_api_key` | Your DeepSeek API key |
| `ADMIN_IDS` | `123456789,987654321` | (Optional) Admin user IDs |
| `DATABASE_PATH` | `bot_database.db` | (Optional) Database file path |
| `LOG_LEVEL` | `INFO` | (Optional) Logging level |

### Running on Replit

1. Click the **Run** button
2. The bot will start automatically
3. Check the console for logs

## Usage

### Starting the Bot

```bash
python main.py
```

### Available Commands

#### User Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and get welcome message |
| `/help` | Show help information |
| `/chat <message>` | Chat with the AI assistant |
| `/profile` | View your user profile |
| `/settings` | Change your preferences |
| `/language` | Change bot language |
| `/stats` | View your usage statistics |

#### Admin Commands

| Command | Description |
|---------|-------------|
| `/admin` | Open admin panel |
| `/broadcast <message>` | Send message to all users |
| `/stats_all` | View global statistics |
| `/users` | List all users |
| `/ban <user_id>` | Ban a user |
| `/unban <user_id>` | Unban a user |
| `/set_language <lang>` | Set default language |
| `/reload_config` | Reload bot configuration |

### Language Support

Currently supported languages:
- English (en)
- Spanish (es)
- French (fr)
- German (de)
- Italian (it)
- Portuguese (pt)
- Russian (ru)
- Chinese (zh)
- Japanese (ja)
- Korean (ko)

To change language, use `/language` command and select from the available options.

## Configuration

### Admin Users

Add admin user IDs in the `ADMIN_IDS` environment variable (comma-separated). Only these users can access admin commands.

### Rate Limiting

The bot implements rate limiting to prevent abuse:
- Default: 10 messages per minute per user
- Configurable in `config.py`

### Database

The bot uses SQLite for data storage. The database file location can be configured via `DATABASE_PATH` environment variable.

## Development

### Project Structure

```
bot_v2/
├── main.py              # Entry point
├── config.py            # Configuration management
├── database.py          # Database operations
├── handlers/            # Command handlers
│   ├── __init__.py
│   ├── start.py
│   ├── chat.py
│   ├── admin.py
│   └── settings.py
├── services/            # Business logic
│   ├── __init__.py
│   ├── ai_service.py
│   └── user_service.py
├── utils/               # Utility functions
│   ├── __init__.py
│   ├── rate_limiter.py
│   └── localization.py
├── locales/             # Translation files
│   ├── en.json
│   ├── es.json
│   └── ...
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

### Adding New Features

1. Create new handler in `handlers/` directory
2. Register the handler in `main.py`
3. Add any new services in `services/`
4. Update translations in `locales/`

## Troubleshooting

### Common Issues

1. **Bot not responding**
   - Check if `BOT_TOKEN` is correct
   - Verify internet connection
   - Check logs for errors

2. **AI not working**
   - Verify `DEEPSEEK_API_KEY` is valid
   - Check API rate limits
   - Ensure DeepSeek service is available

3. **Database errors**
   - Check `DATABASE_PATH` permissions
   - Ensure SQLite is installed
   - Delete and recreate database if corrupted

### Logs

Logs are stored in `bot.log` by default. Set `LOG_LEVEL=DEBUG` for detailed debugging information.

## Security

- Never share your `BOT_TOKEN` or `DEEPSEEK_API_KEY`
- Use environment variables or Replit Secrets for sensitive data
- Regularly update dependencies
- Monitor bot activity for suspicious behavior

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and feature requests, please open an issue on GitHub or contact the maintainers.

---

**Note:** This bot is for educational and personal use. Ensure compliance with Telegram's Terms of Service and applicable laws.