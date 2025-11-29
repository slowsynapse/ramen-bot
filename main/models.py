from django.db import models
from django.contrib.auth.models import User as usr
from django.utils import timezone
from datetime import timedelta, datetime
from django.contrib.postgres.fields import JSONField
from bitcash import Key
from subprocess import Popen, PIPE
from django.conf import settings
import re

import logging
logger = logging.getLogger(__name__)

class Account(usr):
    email_addr = models.CharField(max_length=60)
    confirmation = JSONField(default=None, null=True, unique=True)

    class Meta:
        verbose_name = 'Account'
        verbose_name_plural = 'Accounts'

class User(models.Model):
    reddit_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    reddit_user_details = JSONField(default=dict)
    twitter_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    twitter_user_details = JSONField(default=dict)
    telegram_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    telegram_user_details = JSONField(default=dict)
    post_to_spicefeed = models.BooleanField(default=True)
    simple_ledger_address = models.CharField(max_length=200, null=True, blank=True)
    bitcoincash_address = models.CharField(max_length=200, null=True, blank=True)
    last_activity = models.DateTimeField(default=timezone.now, null=True, blank=True)
    pof = JSONField(default=dict)
    account = models.ForeignKey(Account, null=True, on_delete=models.PROTECT) 
    date_created = models.DateTimeField(default=timezone.now, null=True)
    
    
    @property
    def pof_display(self):
        symbols = settings.POF_SYMBOLS
        if type(self.pof) == dict:
            if "pof_rating" in self.pof.keys():
                val = int(self.pof['pof_rating'])
                return '%s/6 %s' % (val, symbols[val])
        if type(self.pof) == float:
            return None

        return '0/6 %s' % symbols[0]
            
    @property
    def telegram_display_name(self):
        display_name = ''
        if self.telegram_user_details:
            try:
                display_name = self.telegram_user_details['first_name']
                lastname = self.telegram_user_details['last_name']
                display_name = display_name + ' ' + lastname
            except KeyError:
                pass
            if len(display_name) > 20:
                display_name = display_name[0:20]
        return display_name

    @property
    def telegram_username(self):
        try:
            username = self.telegram_user_details['username']
        except KeyError:
            username = ''
        return username
    
    @property
    def twitter_screen_name(self):
        screen_name = ''
        if self.twitter_user_details:
            screen_name = self.twitter_user_details['screen_name']
        return screen_name

    @property
    def twitter_user_id(self):
        if self.twitter_user_details:
            return self.twitter_user_details['id']

    @property
    def reddit_username(self):
        username = ''
        if self.reddit_user_details:
            username = self.reddit_user_details['username']
        return username

    
    def rain(self, text, group_id, balance):
        given = text.lower().strip(' ')

        group = TelegramGroup.objects.get(id=group_id)
        users = group.users.all()

        total_users = 0
        total_spice = 0
        pof = 0
        each_users = False
        message = ''

        scenario_1 = re.compile('^rain\s+\d+\s+people+\s+\d+\s+spice\s+each\s+(?:[0-6]|0[0-6]|6)[\/](?:[1-5]|0[1-5]|5)\s+pof$')
        scenario_2 = re.compile('^rain\s+\d+\s+people+\s+\d+\s+spice\s+total\s+(?:[0-6]|0[0-6]|6)[\/](?:[1-5]|0[1-5]|5)\s+pof$')
        scenario_3 = re.compile('^rain\s+\d+\s+people+\s+\d+\s+spice\s+each$')
        scenario_4 = re.compile('^rain\s+\d+\s+people+\s+\d+\s+spice\s+total$')
        scenario_5 = re.compile('^rain\s+\d+\s+people+\s+\d+\s+spice$')    

        if not scenario_1.match(given) and not scenario_2.match(given) and not scenario_3.match(given) and not scenario_4.match(given) and not scenario_5.match(given):            
            return message

        users = users.filter(
            last_activity__gt=timezone.now() - timedelta(hours=24),
            telegram_id__isnull=False,
            telegram_user_details__is_bot=False
        ).exclude(id=self.id)
        # scene_1
        # rain 5 people 100 spice each 3/5 pof
        # scene_2
        # rain 5 people 500 spice total 3/5 pof
        # scene_3
        # rain 5 people 100 spice each
        # (100 spice to each of 5 people)
        # scene_4
        # rain 5 people 500 spice total
        # (divides 500 spice in total between 5 people)
        # scene_5
        # rain 5 people 100 spice
        # (defaults to **each**. 5 people would get 100 spice each)

        
        text_list = filter(None, given.split(' '))        
        text_list = [x for x in text_list if x]        

        total_users = text_list[text_list.index('people')-1]
        total_spice = text_list[text_list.index('spice')-1]

        if int(total_users) > 10:
            message = "You can only rain \U0001f336 SPICE \U0001f336 to maximum of <b>10</b> people"
            return message
            
        #check scenarios
        if scenario_1.match(given):            
            pof = text_list[text_list.index('pof')-1][0]            
            each_users = True

            #filter user
            users = users.filter(
                pof__pof_rating__gte=float(pof)                
            ).order_by('?')[:int(total_users)]
            logger.info(users)
        elif scenario_2.match(given):
            pof = text_list[text_list.index('pof')-1][0]            
            #filter user
            users = users.filter(
                pof__pof_rating__gte=float(pof)                
            ).order_by('?')[:int(total_users)]
        elif scenario_3.match(given):
            each_users = True            
            #filter user
            users = users.order_by('?')[:int(total_users)]
        elif scenario_4.match(given):            
            #filter user
            users = users.order_by('?')[:int(total_users)]
        elif scenario_5.match(given):
            each_users = True
            #filter_user
            users = users.order_by('?')[:int(total_users)]
        else:
            return ''
        

        if users.count() is 0:
            message = 'Nobody received any spice'
        else:
            if each_users:
                msg_total = float(total_spice) * float(total_users)
                amount_sent = float(total_spice) * users.count()
                amount_received = int(total_spice)
                temp = 'each'
            else:
                msg_total = float(total_spice) 
                amount_sent = float(total_spice) 
                amount_received = float(total_spice) / users.count()
                temp = 'in total'           

            #check rain amount
            from_name = self.telegram_display_name or self.telegram_username
            if balance < msg_total:
                message = f"<b>@{from_name}</b>, you don't have enough \U0001f336 SPICE \U0001f336!"
                return message

            if msg_total < 500:
                message = 'Hi! The minimum amount needed to invoke rain is 500 spice. Please try again.'
                return message

            #Save rain
            rain = Rain(
                sender = self,
                rain_amount=amount_sent,
                message=text          
            )
            rain.save()
            #Transactions
            transaction = Transaction(
                user = self,
                amount = amount_sent,
                transaction_type = 'Outgoing'
            )
            transaction.save()

            users_str = ''            

            first = True
            for u in users:                
                transaction = Transaction(
                    user = u,
                    amount = amount_received,
                    transaction_type = 'Incoming'
                )
                transaction.save()                
                rain.recepients.add(u)
                if first:
                    users_str += u.telegram_display_name
                    first = False
                else:
                    users_str += ', ' + u.telegram_display_name
            message = '<b>%s</b> just rained %s \U0001f336 SPICE \U0001f336 %s to: <b>%s</b>' % (self.telegram_display_name, total_spice, temp, users_str)        

        return message


    def get_username(self):
        return self.telegram_display_name or self.telegram_username or self.twitter_screen_name or self.reddit_username

    def get_source(self):
        if self.twitter_user_details:
            return 'twitter'
        elif self.reddit_user_details:
            return 'reddit'
        elif self.telegram_user_details:
            return 'telegram'
        # return [self.twitter_user_details, self.reddit_user_details, self.telegram_user_details]

    def __str__(self):
        if self.twitter_user_details:
            return self.twitter_user_details['screen_name']
        if self.telegram_user_details:
            return self.telegram_user_details['first_name']
        if self.reddit_user_details:
            return self.reddit_user_details['username']
        else:
            if self.telegram_id:
                return self.telegram_id
            if self.twitter_id:
                return self.twitter_id
            else:
                return self.reddit_id

        
class Withdrawal(models.Model):
    user = models.ForeignKey(
        User,
        related_name='withdrawals',
        on_delete=models.PROTECT
    )
    address = models.CharField(max_length=60)
    transaction_id = models.CharField(max_length=70, blank=True)
    amount = models.FloatField()
    date_created = models.DateTimeField(default=timezone.now)
    date_completed = models.DateTimeField(null=True, blank=True)
    date_failed = models.DateTimeField(null=True, blank=True)


class TelegramGroup(models.Model):
    chat_id = models.CharField(max_length=50, unique=True)
    chat_type = models.CharField(max_length=20)
    title = models.CharField(max_length=70)
    post_to_spicefeed = models.BooleanField(default=True)
    last_privacy_setting = models.DateTimeField(
        default=timezone.now
    )
    privacy_set_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True
    )
    users = models.ManyToManyField(
        User,
        related_name='telegramgroups'
    )
    date_created = models.DateTimeField(default=timezone.now, null=True)

    
class Content(models.Model):
    source = models.CharField(max_length=20, default='telegram')
    tip_amount = models.FloatField()
    sender = models.ForeignKey(
        User,
        related_name='tips_sent',
        on_delete=models.PROTECT
    )
    recipient = models.ForeignKey(
        User,
        related_name='tips_received',
        on_delete=models.PROTECT
    )
    details = JSONField(default=dict)
    post_to_spicefeed = models.BooleanField(default=True)
    date_created = models.DateTimeField(default=timezone.now)
    recipient_content_id = JSONField(default=dict, null=True)
    parent = models.ForeignKey(
        'self',
        null=True,
        related_name='children',
        on_delete=models.PROTECT,
        default=None,
        blank=True
    )

    total_tips = models.FloatField(default=0, null=True)
    last_activity = models.DateTimeField(default=timezone.now)

    def get_media_url(self):
        media_url = None
        if self.source == 'telegram':
            file_id = None
            msg_keys = self.details['message']['reply_to_message'].keys()
            media_types = ('photo', 'sticker', 'animation', 'video', 'video_note', 'voice', 'document')
            for name in media_types:
                if name in msg_keys:
                    if name == 'photo':
                        file_id = self.details['message']['reply_to_message']['photo'][-1]['file_id']
                    else:
                        try:
                            file_id = self.details['message']['reply_to_message'][name]['file_id']
                        except KeyError:
                            file_id = None
                    break
            try:
                media_obj = Media.objects.get(file_id=file_id)
                media_url = media_obj.url
            except Media.DoesNotExist:
                pass                
        elif self.source == 'twitter':
            try:
                media_url = self.details['replied_to']['media'][0]['media_url']
            except KeyError:
                pass
        return media_url


class Response(models.Model):
    response_type= models.CharField(max_length=50)
    content = models.ForeignKey(
        Content,
        related_name='messages',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    body = JSONField(default=None, null=True)
    date_created = models.DateTimeField(default=timezone.now)
    botReplied = models.BooleanField(default=False)

class Transaction(models.Model):
    user = models.ForeignKey(
        User,
        related_name='transactions',
        on_delete=models.PROTECT
    )
    amount = models.FloatField()
    transaction_type = models.CharField(max_length=50)
    date_created = models.DateTimeField(default=timezone.now)


class Deposit(models.Model):
    user = models.ForeignKey(
        User,
        related_name='deposits',
        on_delete=models.PROTECT
    )
    transaction_id = models.CharField(max_length=64, null=True, blank=True,unique=True)
    amount = models.FloatField()
    notes = models.TextField(blank=True)
    date_created = models.DateTimeField(default=timezone.now)
    date_swept = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return 'Deposit: %s SPICE' % self.amount


class Media(models.Model):
    content = models.ForeignKey(
        Content,
        on_delete=models.CASCADE,
        related_name='media',
        null=True
    )
    file_id = models.CharField(max_length=100)
    url = models.CharField(max_length=500)

    class Meta:
        verbose_name_plural = 'Media'


class FaucetDisbursement(models.Model):
    ip_address = models.CharField(max_length=30)
    ga_cookie = models.CharField(max_length=50, null=True, blank=True)
    slp_address = models.CharField(max_length=60)
    transaction_id = models.CharField(max_length=70, blank=True)
    amount = models.FloatField()
    date_created = models.DateTimeField(default=timezone.now)
    date_completed = models.DateTimeField(null=True)

class Rain(models.Model):
    sender = models.ForeignKey(
        User,
        related_name='sender',
        on_delete=models.PROTECT
    )
    recepients = models.ManyToManyField('User')
    rain_amount = models.FloatField()
    date_created = models.DateTimeField(default=timezone.now)
    message = models.TextField()

    def get_recipients(self):
        return "\n".join([r.telegram_display_name for r in self.recepients.all()])