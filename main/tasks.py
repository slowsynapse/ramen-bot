from __future__ import absolute_import, unicode_literals
from celery import shared_task
from celery.signals import task_failure
from main.models import (
    User,
    Transaction
)
from main.utils.account import compute_balance
from django.conf import settings
from django.utils import timezone
import requests
import logging
import traceback

logger = logging.getLogger(__name__)


@task_failure.connect
def handle_task_failure(**kw):
    logger.error(traceback.format_exc())
    return traceback.format_exc()


@shared_task(rate_limit='20/s', queue='telegram')
def send_telegram_message(message, chat_id, update_id, reply_to_message_id=None):
    """Send a message to Telegram chat."""
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }
    # Optionally reply to a specific message (for reaction tips)
    if reply_to_message_id:
        data["reply_to_message_id"] = reply_to_message_id
    url = 'https://api.telegram.org/bot'
    response = requests.post(
        f"{url}{settings.TELEGRAM_BOT_TOKEN}/sendMessage", data=data
    )
    if response.status_code == 200:
        if update_id:
            settings.REDISKV.sadd('telegram_msgs', update_id)
            if settings.REDISKV.scard('telegram_msgs') >= 10000:
                settings.REDISKV.spop('telegram_msgs')
    else:
        logger.error(f"Failed to send Telegram message: {response.text}")


# TODO: Add CHIP-specific tasks
# @shared_task(queue='twitter')
# def verify_twitter_link(user_id, tweet_url):
#     """Verify user's Twitter account via verification tweet"""
#     pass

# @shared_task(queue='twitter')
# def fetch_tweet_data(submission_id):
#     """Fetch tweet metadata before scoring"""
#     pass

# @shared_task(queue='llm')
# def score_tweet(submission_id):
#     """Score tweet using Claude API"""
#     pass

# @shared_task
# def publish_ipfs_snapshot():
#     """Weekly IPFS ledger snapshot"""
#     pass
