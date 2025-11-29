"""ramenbot URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from main.views import (
    TelegramBotView,
    SpiceFeedContentView,
    SpiceFeedLeaderBoardView,
    SpiceFaucetView,
    SpiceFaucetTaskView,
    SpiceFeedContentDetailsView,
    ProofOfFrensView,
    UserSearchView,
    SpiceFeedStats,
    signup,
    login,
    logout,
    connectAccount,
    confirmAccount,
    contentpage
)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('<int:id>/', contentpage, name='index'),
    path('webhooks/telegram/', csrf_exempt(TelegramBotView.as_view())),
    path('api/signup/',signup, name='signup'),
    path('api/login/', login, name='login'),
    path('api/logout/', logout, name='logout'),
    path('api/connect-account/', connectAccount, name='connectAccount'),
    path('api/confirm-account/', confirmAccount, name='confirmAccount'),
    path('api/feed/stats/', csrf_exempt(SpiceFeedStats.as_view())),
    path('api/feed/content/', csrf_exempt(SpiceFeedContentView.as_view())),
    path('api/feed/leaderboard/', csrf_exempt(SpiceFeedLeaderBoardView.as_view())),
    path('api/faucet/', csrf_exempt(SpiceFaucetView.as_view())),
    path('api/faucet/task/', csrf_exempt(SpiceFaucetTaskView.as_view())),
    path('api/feed/details/<int:id>/', csrf_exempt(SpiceFeedContentDetailsView.as_view())),
    path('api/feed/pof/', csrf_exempt(ProofOfFrensView.as_view())),
    path('api/feed/search/<slug:user>/', csrf_exempt(UserSearchView.as_view()))
]
