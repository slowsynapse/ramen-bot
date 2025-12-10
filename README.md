# CHIP Bot

A Telegram bot that rewards quality BCH content with CHIP points. Built for the BCH-1 Hackcelerator.

## Features

- **Tweet Submissions**: Submit BCH-related tweets for LLM-powered scoring
- **Twitter Verification**: Link your Twitter account 1:1 with Telegram
- **Peer-to-Peer Tipping**: Tip other users with emoji or commands
- **Leaderboard**: Track top contributors
- **IPFS Snapshots**: Transparent ledger published weekly

## Tech Stack

- Django 2.2 + Django REST Framework
- Celery + Redis (async tasks)
- PostgreSQL
- Claude API (LLM scoring)
- Twitter API v2 (verification & tweet fetching)
- Pinata (IPFS snapshots)

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL + Redis
docker-compose up -d db redis

# Run migrations
python manage.py migrate

# Start Django
python manage.py runserver 8000

# Start ngrok (for Telegram webhooks)
ngrok http 8000

# Register webhook
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook?url=https://YOUR_NGROK_URL/webhooks/telegram/"

# Start Celery worker
celery -A ramenbot worker -l info
```

## Environment Variables

Copy `.env_template` to `.env` and configure:

```bash
TELEGRAM_BOT_TOKEN=xxx
TWITTER_BEARER_TOKEN=xxx
ANTHROPIC_API_KEY=xxx
PINATA_API_KEY=xxx
PINATA_SECRET_KEY=xxx
CHIP_SALT=your_secret_salt
POSTGRES_DB=ramenbot
REDIS_HOST=localhost
```

## Adapted From

This project is adapted from [Spicebot](https://github.com/aspect-build-old/spicebot), a cryptocurrency tipping bot.
