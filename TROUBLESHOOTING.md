# CHIP Bot Troubleshooting Guide

## Quick Setup

```bash
# Start all services
docker compose up -d                    # PostgreSQL + Redis
source venv/bin/activate
python3 manage.py runserver 8000        # Django
celery -A ramenbot worker -l info -Q celery,telegram  # Celery (IMPORTANT: include telegram queue)
ngrok http 8000                         # Tunnel for webhook
```

## Common Issues

### 1. Bot receives messages but doesn't respond

**Symptom**: Django logs show webhook receiving messages, but no replies sent to Telegram.

**Cause**: Celery worker not listening to the `telegram` queue.

**Fix**: Start Celery with `-Q celery,telegram`:
```bash
celery -A ramenbot worker -l info -Q celery,telegram
```

The `send_telegram_message` task is configured with `queue='telegram'` in `main/tasks.py`.

### 2. Webhook returning 500 errors

**Check**:
1. Django server is running
2. ngrok tunnel is active
3. Webhook URL is correctly set

**Verify webhook**:
```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

**Reset webhook**:
```bash
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<ngrok-url>/webhooks/telegram/"
```

### 3. TELEGRAM_BOT_USER mismatch

**Symptom**: Bot doesn't respond to mentions or commands.

**Fix**: Ensure `.env` has the correct bot username (without @):
```
TELEGRAM_BOT_USER=IAMBCH_BOT
```

### 4. Database connection errors

**Check**: PostgreSQL container is running:
```bash
docker compose ps
docker compose logs postgres
```

### 5. Redis connection errors

**Check**: Redis container is running:
```bash
docker compose ps
redis-cli ping  # Should return PONG
```

## Useful Commands

```bash
# Check webhook status
curl -s "https://api.telegram.org/bot<TOKEN>/getWebhookInfo" | python3 -m json.tool

# Test webhook locally
curl -X POST http://localhost:8000/webhooks/telegram/ \
  -H "Content-Type: application/json" \
  -d '{"update_id":1,"message":{"message_id":1,"from":{"id":123},"chat":{"id":123,"type":"private"},"text":"balance"}}'

# Check Celery queues in Redis
redis-cli -n 4 KEYS "*"

# View Django logs
# (check terminal running manage.py runserver)

# View Celery logs
# (check terminal running celery worker)
```

## Service Ports

| Service    | Port |
|------------|------|
| Django     | 8000 |
| PostgreSQL | 5432 |
| Redis      | 6379 |
| ngrok      | 4040 (web UI) |
