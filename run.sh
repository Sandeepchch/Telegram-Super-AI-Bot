#!/bin/bash

# Telegram Bot Runner Script

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "Please copy .env.example to .env and add your API keys:"
    echo "cp .env.example .env"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d venv ]; then
    echo "⚠️ Virtual environment not found. Running setup..."
    bash setup.sh
fi

# Activate virtual environment
source venv/bin/activate

# Run the bot
echo "🚀 Starting Telegram Bot..."
python3 telegram_bot.py
