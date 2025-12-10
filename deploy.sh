#!/bin/bash
# Deploy RAMEN bot to VPS
# Usage: ./deploy.sh [message]

set -e

VPS="root@157.245.152.152"
REMOTE_DIR="/var/www/ramen-bot"

echo "=== Deploying RAMEN Bot ==="

# 1. Commit and push local changes (if message provided)
if [ -n "$1" ]; then
    echo "Committing: $1"
    git add -A
    git commit -m "$1" || echo "Nothing to commit"
    git push origin main
fi

# 2. Pull on VPS and restart services
echo "Pulling changes on VPS..."
ssh $VPS "cd $REMOTE_DIR && git pull"

echo "Installing any new dependencies..."
ssh $VPS "cd $REMOTE_DIR && source venv/bin/activate && pip install -r requirements.txt -q"

echo "Running migrations..."
ssh $VPS "cd $REMOTE_DIR && source venv/bin/activate && python manage.py migrate --noinput"

echo "Collecting static files..."
ssh $VPS "cd $REMOTE_DIR && source venv/bin/activate && python manage.py collectstatic --noinput -q"

echo "Restarting services..."
ssh $VPS "systemctl restart ramenbot ramenbot-celery"

echo "=== Deployment Complete ==="
ssh $VPS "systemctl status ramenbot ramenbot-celery --no-pager | head -20"
