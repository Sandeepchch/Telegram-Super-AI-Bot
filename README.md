# 🤖 Advanced Telegram Bot with AI Intelligence

---

## 🚀 **TRY THE BOT NOW Rising-ChatAI** 

### **[🤖 START BOT - Click Here to Test](https://t.me/Risingstars33_bot?start=_tgr_ZasFsABmZTU1)**

**👉 Test the bot directly on Telegram before setting it up locally!**

---

A powerful, feature-rich Telegram bot powered by **Groq AI** (with Cerebras fallback) that provides intelligent conversations, internet search capabilities, and multi-model support.

## ✨ Key Features

- **🧠 Advanced AI Models**
  - Primary: Groq Kimi K2 (Fast & Intelligent)
  - Fallback 1: OpenAI GPT-OSS 120B
  - Fallback 2: OpenAI GPT-OSS 20B
  - Secondary Provider: Cerebras Llama 3.3 70B

- **🔍 Internet Search Integration**
  - Google Custom Search API
  - Tavily Search API
  - Wikipedia Integration
  - Brave Search (Optional)
  - Real-time information retrieval

- **💬 Smart Conversation**
  - Maintains conversation history
  - Context-aware responses
  - Typing indicators for better UX
  - Rate limiting protection
  - Multi-user support

- **⚡ Performance Optimized**
  - Asynchronous processing
  - Parallel API calls for search
  - Configurable response limits
  - Efficient token usage

- **🛡️ Security**
  - No hardcoded API keys
  - Environment-based configuration
  - Rate limiting
  - User data isolation

## 📋 Requirements

- Python 3.8+
- Telegram Bot Token (from @BotFather)
- API Keys for:
  - Groq AI
  - Cerebras (optional fallback)
  - Google Custom Search
  - Tavily Search (optional)
  - Other search providers (optional)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/Sandeepchch/Telegram-Super-AI-Bot.git
cd Telegram-Super-AI-Bot
```

### 2. Run Setup Script (Recommended)

```bash
bash setup.sh
```

This will:
- Create a Python virtual environment
- Install all dependencies
- Create a .env file from .env.example

### 3. Configure API Keys

Edit the `.env` file with your API keys:

```bash
nano .env
```

Fill in the required values:
- TELEGRAM_BOT_TOKEN
- GROQ_API_KEY
- CEREBRAS_API_KEY
- GOOGLE_SEARCH_API_KEY
- GOOGLE_SEARCH_CX_ID
- TAVILY_API_KEY (optional)

### 4. Run the Bot

```bash
bash run.sh
```

Or manually:

```bash
source venv/bin/activate
python3 telegram_bot.py
```

## 🔑 Getting API Keys

### Telegram Bot Token
1. Open Telegram and search for **@BotFather**
2. Send `/start`
3. Send `/newbot` and follow the steps
4. Copy your bot token

### Groq API Key
1. Visit [Groq Console](https://console.groq.com)
2. Sign up / Log in
3. Create a new API key
4. Copy and save it

### Cerebras API Key
1. Visit [Cerebras Console](https://console.cerebras.com)
2. Sign up / Log in
3. Create a new API key
4. Copy and save it

### Google Custom Search API
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project
3. Enable "Custom Search API"
4. Create API credentials (API key)
5. Create a Custom Search Engine at [Programmable Search Engine](https://programmablesearchengine.google.com/)
6. Get your CX ID from the engine settings

### Tavily Search API
1. Visit [Tavily](https://tavily.com)
2. Sign up for a free account
3. Generate API key from dashboard

## 📁 Project Structure

```
telegram-bot/
├── telegram_bot.py              # Main bot application
├── enhanced_response_system.py   # Response streaming utility
├── requirements.txt              # Python dependencies
├── .env.example                  # Example environment variables
├── .gitignore                    # Git ignore rules
├── Dockerfile                    # Docker configuration
├── docker-compose.yml            # Docker Compose setup
├── setup.sh                      # Setup script
├── run.sh                        # Run script
└── README.md                     # This file
```

## 🤝 Bot Commands

Once the bot is running, send these commands in Telegram:

| Command | Description |
|---------|-------------|
| `/start` | Start the bot & see welcome message |
| `/help` | Show available commands |
| `/settings` | Configure bot settings |
| `/about` | Bot information & model details |
| `/search on` | Enable internet search |
| `/search off` | Disable internet search |
| `Just type` | Send any message for AI response |

## 🐳 Docker Deployment

### Method 1: Docker Compose (Recommended)

```bash
# Create .env file with your API keys
cp .env.example .env
nano .env

# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Method 2: Docker Run

```bash
# Build the image
docker build -t telegram-bot .

# Run the container
docker run -d \
  --name telegram-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN="your_token" \
  -e GROQ_API_KEY="your_key" \
  -e CEREBRAS_API_KEY="your_key" \
  -e GOOGLE_SEARCH_API_KEY="your_key" \
  -e GOOGLE_SEARCH_CX_ID="your_cx_id" \
  -e TAVILY_API_KEY="your_key" \
  telegram-bot

# View logs
docker logs -f telegram-bot

# Stop
docker stop telegram-bot && docker rm telegram-bot
```

## ⚙️ Configuration Options

In `telegram_bot.py`, you can adjust:

```python
TEMPERATURE = 0.6              # Response creativity (0.0-1.0)
MAX_OUTPUT_TOKENS = 6000       # Maximum response length
TOP_P = 0.93                   # Nucleus sampling parameter
TOP_K = 40                     # Top-K sampling parameter
MAX_MESSAGE_LENGTH = 4096      # Telegram message limit
RATE_LIMIT_SECONDS = 3         # Rate limiting per user
MAX_HISTORY = 10               # Conversation history size
```

## 🚨 Security Best Practices

✅ **Do**:
- Use `.env` file for secrets
- Add `.env` to `.gitignore` (already included)
- Rotate API keys regularly
- Use environment variables in production
- Monitor API key usage

❌ **Don't**:
- Commit `.env` to version control
- Share API keys publicly
- Hardcode secrets in code
- Use test tokens in production

## 📊 Performance Tips

1. **Use Groq as primary** - Faster responses
2. **Enable search selectively** - Uses more API calls
3. **Adjust MAX_OUTPUT_TOKENS** - Balance between quality and speed
4. **Monitor API usage** - Check your provider dashboards

## 🐛 Troubleshooting

### Bot doesn't respond
- Check if `.env` file has correct tokens
- Verify internet connection
- Check logs: `tail -f telegram_bot.log`

### Search not working
- Verify Google Custom Search API enabled
- Check CX ID is correct
- Ensure API quota is available

### Slow responses
- Reduce `MAX_OUTPUT_TOKENS`
- Disable search if not needed
- Check API provider status

### Rate limiting errors
- Increase `RATE_LIMIT_SECONDS`
- Use separate API keys for different bots

## 📝 Project Management

Deploying on different platforms:

### Linux VPS (Ubuntu/Debian)
```bash
# Install Python
sudo apt-get install python3 python3-venv python3-pip

# Clone and setup
git clone https://github.com/Sandeepchch/Telegram-Super-AI-Bot.git
cd Telegram-Super-AI-Bot
bash setup.sh
cp .env.example .env
# Edit .env
bash run.sh
```

### Using Systemd Service
Create `/etc/systemd/system/telegram-bot.service`:
```ini
[Unit]
Description=Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/Telegram-Super-AI-Bot
ExecStart=/bin/bash -c 'source venv/bin/activate && python3 telegram_bot.py'
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
sudo systemctl status telegram-bot
```

## 📈 Monitoring

Monitor your bot using logs:

```bash
# Real-time logs
tail -f telegram_bot.log

# Last 100 lines
tail -100 telegram_bot.log

# Search for errors
grep ERROR telegram_bot.log

# Count API calls
grep -c "API" telegram_bot.log
```

## 🔄 Updates & Maintenance

```bash
# Pull latest changes
git pull origin main

# Update dependencies
pip install -r requirements.txt --upgrade

# Restart the bot
bash run.sh
```

## 📞 Support & Help

- Check GitHub Issues for common problems
- Review logs for error messages
- Verify API keys are correct
- Check API provider status pages

## 📄 License

This project is open source. Feel free to use and modify.

## ⭐ Support

If this bot helps you, please:
- Star the repository ⭐
- Share with others
- Report bugs and suggest features

## 🔗 Useful Links

- [Telegram Bot API Documentation](https://core.telegram.org/bots/api)
- [Python Telegram Bot Docs](https://docs.python-telegram-bot.org/)
- [Groq Documentation](https://console.groq.com/docs)
- [Cerebras Documentation](https://docs.cerebras.ai/)
- [Google Custom Search](https://developers.google.com/custom-search)

## ⚡ Quick Commands

```bash
# Clone
git clone https://github.com/Sandeepchch/Telegram-Super-AI-Bot.git && cd Telegram-Super-AI-Bot

# Setup
bash setup.sh

# Configure
cp .env.example .env
nano .env

# Run
bash run.sh

# Docker
docker-compose up -d
docker-compose logs -f
docker-compose down
```

---

**Devloped by Rising-AI🎉**

For questions or issues, please open a GitHub Issue.
