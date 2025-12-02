import json
import logging

from django.http import JsonResponse
from django.views import View
from django.utils import timezone
from django.db.models import Sum, Count
from datetime import timedelta

from .utils.telegram import TelegramBotHandler
from .models import Content, User, TelegramGroup, Transaction


logger = logging.getLogger(__name__)


class TelegramBotView(View):
    """Webhook endpoint for Telegram bot updates."""

    def post(self, request):
        data = json.loads(request.body)
        logger.info(data)

        handler = TelegramBotHandler(data)
        handler.process_data()
        handler.respond()

        return JsonResponse({"ok": "POST request processed"})


class StatsView(View):
    """Basic stats endpoint for RAMEN."""

    def get(self, request):
        tg_channels = TelegramGroup.objects.all()
        users = User.objects.filter(telegram_id__isnull=False)
        tips = Content.objects.all()

        # All time stats
        response = {
            'all_time': {
                'total_telegram_channels': tg_channels.count(),
                'total_tips': tips.count(),
                'total_tip_amount': tips.aggregate(Sum('tip_amount'))['tip_amount__sum'] or 0,
                'total_users': users.count(),
            }
        }

        # Last 24 hours
        dt = timezone.now() - timedelta(hours=24)
        tips_24h = tips.filter(date_created__gte=dt)
        response['last_24_hours'] = {
            'total_tips': tips_24h.count(),
            'total_tip_amount': tips_24h.aggregate(Sum('tip_amount'))['tip_amount__sum'] or 0,
            'new_users': users.filter(date_created__gte=dt).count(),
        }

        return JsonResponse(response)


class LeaderboardView(View):
    """Leaderboard endpoint for RAMEN."""

    def get(self, request):
        category = request.GET.get('category', 'sent')
        limit = int(request.GET.get('limit', 10))

        if category == 'sent':
            # Top tippers
            users = User.objects.annotate(
                total=Sum('tips_sent__tip_amount')
            ).filter(total__gt=0).order_by('-total')[:limit]
        else:
            # Top receivers
            users = User.objects.annotate(
                total=Sum('tips_received__tip_amount')
            ).filter(total__gt=0).order_by('-total')[:limit]

        leaderboard = []
        for user in users:
            leaderboard.append({
                'username': user.get_username(),
                'total': user.total or 0,
            })

        return JsonResponse({'leaderboard': leaderboard, 'category': category})
