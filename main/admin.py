from django.contrib import admin
from main.utils.account import compute_balance
from main.models import (
    User as ChipUser,
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


admin.site.site_header = 'CHIP Bot Administration'


class UserAdmin(admin.ModelAdmin):
    list_display = ['id', 'telegram_display_name', 'twitter_screen_name', 'balance', 'pof']
    search_fields = ['telegram_user_details', 'twitter_user_details']

    def telegram_display_name(self, obj):
        if obj.telegram_user_details:
            return obj.telegram_display_name
        return str(obj.telegram_id)

    def twitter_screen_name(self, obj):
        return obj.twitter_screen_name

    def balance(self, obj):
        return compute_balance(obj)


admin.site.register(ChipUser, UserAdmin)


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
        if obj.user.telegram_id:
            return 'telegram'
        if obj.user.twitter_id:
            return 'twitter'
        return ''

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
        'post_to_chipfeed',
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
