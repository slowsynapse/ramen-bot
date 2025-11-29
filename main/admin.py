from django.contrib import admin
from main.utils.account import compute_balance
from main.models import (
    User as SpiceUser,
    Content,
    Transaction,
    Deposit,
    Withdrawal,
    TelegramGroup,
    Media,
    FaucetDisbursement,
    Account,
    Response,
    Rain
)


admin.site.site_header = 'Spice Bot Administration'


class UserAdmin(admin.ModelAdmin):
    list_display = ['id', 'telegram_display_name', 'twitter_screen_name', 'balance', 'reddit_username', 'pof']
    search_fields = ['telegram_user_details', 'twitter_user_details', 'reddit_user_details']

    def telegram_display_name(self, obj):
        if obj.telegram_user_details:
            return obj.telegram_display_name
        return str(obj.telegram_id)

    def twitter_screen_name(self, obj):
        return obj.twitter_screen_name

    def reddit_username(self, obj):
        if obj.reddit_user_details:
            return obj.reddit_username
        return str(obj.reddit_username)
    def balance(self, obj):
        return compute_balance(obj)


admin.site.register(SpiceUser, UserAdmin)


class ContentAdmin(admin.ModelAdmin):
    list_display = [
        'tip_amount',
        'source',
        'sender',
        'recipient', 
        'date_created',
        'parent'
    ]

    raw_id_fields = ['sender', 'recipient', 'parent']

admin.site.register(Content, ContentAdmin)


class ResponseAdmin(admin.ModelAdmin):
    list_display = [
        'content',
        'botReplied',
        'body',
        'date_created',
        'response_type'
    ]

admin.site.register(Response, ResponseAdmin)


class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'user', 
        'amount', 
        'transaction_type', 
        'date_created'
    ]

    raw_id_fields = ['user']

admin.site.register(Transaction, TransactionAdmin)


class DepositAdmin(admin.ModelAdmin):
    list_display = [
        'user', 
        'amount',
        'date_created',
        'date_swept'
    ]

    raw_id_fields = ['user']

admin.site.register(Deposit, DepositAdmin)


class WithdrawalAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'channel',
        'address',
        'amount',
        'date_created',
        'date_completed',
        'date_failed'
    ]

    raw_id_fields = ['user']

    def channel(self, obj):
        channel = ''
        if obj.user.twitter_id:
            channel = 'twitter'
        if obj.user.telegram_id:
            channel = 'telegram'
        if obj.user.reddit_id:
            channel = 'reddit'
        return channel

admin.site.register(Withdrawal, WithdrawalAdmin)


class MediaAdmin(admin.ModelAdmin):
    list_display = [
        'file_id',
        'url'
    ]

admin.site.register(Media, MediaAdmin)


class TelegramGroupAdmin(admin.ModelAdmin):
    list_display = [
        'title',
        'chat_type',
        'post_to_spicefeed',
        'privacy_set_by'
    ]


admin.site.register(TelegramGroup, TelegramGroupAdmin)


class FaucetDisbursementAdmin(admin.ModelAdmin):
    list_display = [
        'slp_address',
        'amount',
        'ip_address',
        'date_created',
        'date_completed'
    ]


admin.site.register(FaucetDisbursement, FaucetDisbursementAdmin)


class AccountAdmin(admin.ModelAdmin):
    list_display = [
        'username',
        'email_addr'        
    ]

admin.site.register(Account, AccountAdmin)

class RainAdmin(admin.ModelAdmin):    
    list_display = [        
        'sender',
        'rain_amount',
        'get_recipients'
    ]

admin.site.register(Rain, RainAdmin)
