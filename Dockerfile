FROM python:3.12-slim

WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY telegram_bot.py .
COPY enhanced_response_system.py .

# Create data directory for persistence
RUN mkdir -p /app/data

# Volume for persistent data
VOLUME ["/app/data"]

# Run the bot
CMD ["python", "telegram_bot.py"]
