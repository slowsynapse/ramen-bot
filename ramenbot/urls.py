"""ramenbot URL Configuration"""
from django.contrib import admin
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from main.views import (
    TelegramBotView,
    StatsView,
    LeaderboardView,
)


urlpatterns = [
    path('admin/', admin.site.urls),

    # Telegram webhook
    path('webhooks/telegram/', csrf_exempt(TelegramBotView.as_view())),

    # API endpoints
    path('api/stats/', csrf_exempt(StatsView.as_view())),
    path('api/leaderboard/', csrf_exempt(LeaderboardView.as_view())),
]
