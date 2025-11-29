import json
import os
import logging
import datetime as dt

from django.contrib.auth import authenticate, login
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_200_OK
)

import requests
from celery.result import AsyncResult
from subprocess import Popen, PIPE
from .utils.telegram import TelegramBotHandler
from .utils.twitter import TwitterBot
from .models import Content, User, Media, FaucetDisbursement, Account, TelegramGroup
from django.db.models import Sum, Count, Q
from django.http import JsonResponse, HttpRequest
from django.core.paginator import Paginator, EmptyPage
from django.views import View
from django.utils import timezone
from django.conf import settings
from django.db.models import Sum
from django.utils.crypto import get_random_string
from datetime import timedelta, datetime
from random import randint
from main.tasks import process_faucet_request
from django.shortcuts import render
from difflib import SequenceMatcher


logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes((AllowAny,))
def signup(request):
    username = request.data.get('username')
    password = request.data.get('password')

    if username is None or password is None:
        return Response({'error': 'Please provide both username and password'},
                        status=HTTP_400_BAD_REQUEST)

    new_user = Account.objects.create_user(
        username=username,
        password=password
    )
    new_user.save()

    token, _ =  Token.objects.get_or_create(user=new_user)

    return Response(
        {'success': True, 'token': token.key, 'username': username},
        status=HTTP_200_OK
    )


@api_view(['POST'])
@permission_classes((AllowAny,))
def login(request):
    username = request.data.get("username")
    password = request.data.get("password")

    if username is None or password is None:
        return Response({'error': 'Please provide both username and password'},
                        status=HTTP_400_BAD_REQUEST)
    user = authenticate(username=username,password=password)
    if not user:
        return Response({'error': 'Invalid Credentials'},
                        status=HTTP_404_NOT_FOUND)    
    token, _ = Token.objects.get_or_create(user=user)

    return Response(
        {'success': True, 'token': token.key, 'username':username},
        status=HTTP_200_OK
    )

@api_view(['POST'])
@permission_classes((IsAuthenticated,))
def logout(request):
    request.user.auth_token.delete()    
    return Response({'status': 'success'}, status=HTTP_200_OK)

@api_view(['POST'])
@permission_classes((IsAuthenticated, ))
def connectAccount(request):
    token = request.META.get('HTTP_AUTHORIZATION').replace('Token ', '')
    user = Token.objects.get(key=token).user

    account = Account.objects.get(username=user.username)
    username = request.data.get('username')
    source = request.data.get('source')
    #Generate Random Key
    confirmation_key = get_random_string(length=6)
    users = User.objects.all()
    proceed = False

    status = None
    for u in users:
        #send code to telegram
        if source == 'telegram' and u.telegram_display_name == username:                                    
            details = u.telegram_user_details            
            message = "Your code is %s\n" % confirmation_key
            name = u.telegram_display_name
            url = 'https://api.telegram.org/bot'
            data = {
                "chat_id": details['id'],
                "text": message, 
                "parse_mode": "HTML",
            }            

            response = requests.post(
                f"{url}{settings.TELEGRAM_BOT_TOKEN}/sendMessage", data=data
            )

            status = response.status_code
            if status == 200:
                proceed = True                           
        #send code to twitter
        elif source == 'twitter' and u.twitter_screen_name == username:
            name = u.twitter_screen_name
            message = "Your code is %s\n" % confirmation_key
            bot = TwitterBot()
            bot.send_direct_message(u.twitter_id, message)
            proceed = True

        if proceed:
            confirmation = {
                "key": confirmation_key,
                "source": source,
                "user": name
            }
            account.confirmation = confirmation
            account.save()  

            return Response({"status": "success"}, status=HTTP_200_OK)        

    return Response({"status": "failure"}, status=HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes((IsAuthenticated,))
def confirmAccount(request):
    token = request.META.get('HTTP_AUTHORIZATION').replace('Token ', '')
    user = Token.objects.get(key=token).user
    account = Account.objects.get(username=user.username)
    proceed = False

    code = request.data.get('code')
    code = code.replace(' ', '')     
    if account.confirmation['key'] == code:        
        username = account.confirmation['user']
        source = account.confirmation['source']
        users = User.objects.all()
         
        for u in users:            
            if source == 'telegram' and u.telegram_display_name == username:
                proceed = True
            if source == 'twitter' and u.twitter_screen_name == username:
                proceed = True

            if proceed:
                u.account = account
                u.save()
                
                account.confirmation = None
                account.save()        
                
                return Response({"status": "success"}, status=HTTP_200_OK)
    return Response({"status": "failure"}, status=HTTP_400_BAD_REQUEST)
        
class ProofOfFrensView(View):

    def get(self, request):        
        data = User.objects.all().order_by('pof')[0:50]

        return JsonResponse({'success': True})        


class TelegramBotView(View):

    def post(self, request):
        data = json.loads(request.body)
        logger.info(data)

        handler = TelegramBotHandler(data)
        handler.process_data()
        handler.respond()

        return JsonResponse({"ok": "POST request processed"})

class SpiceFeedStats(View):

    def get(self, request):
        tg_channels = TelegramGroup.objects.all()
        users_received_tips = User.objects.annotate(
            received=Count('tips_received')
        ).filter(
            received__gt=0
        )
        users_sent_tips = User.objects.annotate(
            sent=Count('tips_sent')
        ).filter(
            sent__gt=0
        )
        users = users_received_tips | users_sent_tips
        tips = Content.objects.all()
        disbursements = FaucetDisbursement.objects.all()

        # All time stats
        response = {
            'all_time': {
                'total_telegram_channels': tg_channels.count(),
                'total_tips': tips.count(),
                'total_tip_amount': tips.aggregate(Sum('tip_amount'))['tip_amount__sum'] or 0,
                'total_users': users.count(),
                'faucet_disbursements': disbursements.count(),
                'total_faucet_disbursement': disbursements.aggregate(Sum('amount'))['amount__sum'] or 0
            }
        }

        # Last 24 hours
        data = {}
        dt = timezone.now() - timedelta(hours=24)
        tips_sub = tips.filter(date_created__gte=dt)
        disbursements_sub = disbursements.filter(date_created__gte=dt)
        data['total_telegram_channels'] = tg_channels.filter(date_created__gte=dt).count()
        data['total_tips'] = tips_sub.count()
        data['total_tip_amount'] = tips_sub.aggregate(Sum('tip_amount'))['tip_amount__sum'] or 0
        data['total_users'] = users.filter(date_created__gte=dt).count()
        data['faucet_disbursements'] = disbursements_sub.count()
        data['total_faucet_disbursement'] = disbursements_sub.aggregate(Sum('amount'))['amount__sum'] or 0
        response['last_24_hours'] = data

        return JsonResponse(response)


class SpiceFeedContentView(View):
    
    def get(self, request):
        category = request.GET.get('category', 'latest')
        media_only = request.GET.get('media_only', 'false')
        page = request.GET.get('page', 1)
        per_page = request.GET.get('per_page', 50)
        all_contents = Content.objects.filter(
            post_to_spicefeed=True
        )
        if media_only == 'true':
            all_contents = all_contents.annotate(
                media_count=Count('media')
            ).filter(
                media_count__gte=1
            )
        if category == 'milklist':
            all_contents = Content.objects.filter(
                post_to_spicefeed=True,
                tip_amount__lt=0.000001,
                parent=None
            ).order_by('-last_activity')
        else:
            all_contents = Content.objects.filter(
                post_to_spicefeed=True,
                tip_amount__gte=5,
                parent=None            
            )
            if category == 'latest':
                all_contents = all_contents.order_by('-last_activity')
            elif category == 'hottest':
                last_24_hrs = timezone.now() - timedelta(hours=24)
                all_contents = all_contents.filter(
                    parent=None,
                    last_activity__gte=last_24_hrs
                ).order_by('-total_tips')
        paginator = Paginator(all_contents, per_page)
        response = {}
        page_contents = None
        try:
            page_contents = paginator.page(int(page))
        except EmptyPage:
            response['success'] = False
            response['error'] = 'empty_page'
        contents = []
        if page_contents:
            for content in page_contents.object_list:
                if content.children.count():
                    if category == 'latest':
                        content = content.children.last()
                if content.post_to_spicefeed:
                    int_amount = content.tip_amount * 100000000
                    data = {
                        'created_at': content.date_created.isoformat(),
                        'permalink': content.id,
                        'service': content.source,
                        'int_amount': int_amount,
                        'string_amount': str(int_amount),
                    }                
                    temp_contents = Content.objects.filter(parent=content)                
                    total_tips = content.tip_amount
                    for temp in temp_contents:
                        total_tips+=temp.tip_amount
                    data['total_tips'] = '{0:.10f}'.format(total_tips).rstrip('0').rstrip('.')
                    if content.source == 'telegram':
                        try:
                            original_message = content.details['message']['reply_to_message']['text']
                        except KeyError:
                            original_message = ''
                        data['tipped_user_name'] = content.recipient.telegram_display_name
                        data['tipper_user'] = content.sender.telegram_display_name
                        data['tipper_message'] = content.details['message']['text']
                        data['tipper_message_date'] = content.details['message']['date']
                        data['original_message'] = original_message
                        data['original_message_mediapath'] = content.get_media_url()
                        data['additional_tippers'] = []
                    elif content.source == 'twitter':
                        try:
                            original_message = content.details['replied_to']['text']
                        except KeyError:
                            original_message = ''
                        data['tipped_user_name'] = content.recipient.twitter_screen_name
                        data['tipper_user'] = content.sender.twitter_screen_name
                        data['tipper_message'] = content.details['reply']['text']
                        data['tipper_message_date'] = content.details['reply']['created_at']
                        data['original_message'] = original_message
                        data['original_message_mediapath'] = ''
                        data['additional_tippers'] = []

                    elif content.source == 'reddit':
                        logger.info('in reddit')
                        try:
                            original_message = content.details['submission_details']['text']
                        except KeyError:
                            original_message = ''
                        data['tipped_user_name'] = content.recipient.reddit_username
                        data['tipper_user'] = content.sender.reddit_username
                        data['tipper_message'] = content.details['comment_details']['comment_body']
                        data['tipper_message_date'] = content.details['comment_details']['date_created']
                        data['original_message'] = original_message
                        data['original_message_mediapath'] = content.details['submission_details']['media_url']
                        data['additional_tippers'] = []

                    # For now, exclude reddit content from spicefeed
                    #if content.source != 'reddit':
                        # Second-level filtering for media only
                    if media_only == 'true':
                        if 'original_message_mediapath' in data.keys():
                            if data['original_message_mediapath']:
                                contents.append(data)
                    else:
                        contents.append(data)

        if len(contents):
            response['success'] = True
            try:
                next_page = page_contents.next_page_number()
            except EmptyPage:
                next_page = None
            try:
                previous_page = page_contents.previous_page_number()
            except EmptyPage:
                previous_page = None
            response['pagination'] = {
                'page': page,
                'per_page': per_page,
                'next_page_number': next_page,
                'previous_page_number': previous_page
            }
            response['contents'] = contents
        return JsonResponse(response)


class SpiceFeedLeaderBoardView(View):

    def get(self, request):
        category = request.GET.get('category', 'sent')
        if category == 'sent':
            query = Content.objects.values('sender__id').annotate(
                total_tipped=Sum('tip_amount')).order_by('-total_tipped')[0:50]
        elif category == 'received':
            query = Content.objects.values('recipient__id').annotate(
                total_received=Sum('tip_amount')
            ).order_by('-total_received')[0:50]
        ranking = []
        for item in query:
            if category == 'sent':
                user = User.objects.get(id=item['sender__id'])
                del item['sender__id']
                item['total_tipped'] *= 100000000
            elif category == 'received':
                user = User.objects.get(id=item['recipient__id'])
                del item['recipient__id'] 
                item['total_received'] *= 100000000
            item['username'] = user.telegram_display_name or user.twitter_screen_name or user.reddit_username
            item['mediapath'] = ''
            ranking.append(item)
        response = {
            'ranking': ranking
        }
        return JsonResponse(response)


class SpiceFaucetView(View):

    def post(self, request):
        data = json.loads(request.body)
        slp_address = data.get('slp_address')
        recaptcha_token = data.get('recaptcha_token')
        response = {'success': False}

        url = 'https://www.google.com/recaptcha/api/siteverify'
        payload = {
            'secret': settings.RECAPTCHA_SECRET,
            'response': recaptcha_token
        }
        resp = requests.post(url, payload)
        if resp.status_code == 200 and resp.json()['success']:
            if not slp_address.startswith('simpleledger') and not len(slp_address) == 55:
                response['error'] = "The SLP address is invalid"
            else:
                from_date = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
                to_date = timezone.now()
                total_today = FaucetDisbursement.objects.filter(
                    date_completed__gt=from_date,
                    date_completed__lte=to_date
                ).aggregate(Sum('amount'))
                total_today = total_today['amount__sum'] or 0
                
                if total_today < settings.FAUCET_DAILY_LIMIT:
                    ip_address = request.META.get('HTTP_X_FORWARDED_FOR', None)
                    if not ip_address:
                        ip_address = request.META.get('REMOTE_ADDR', '')
                    cookies = request.META.get('HTTP_COOKIE', '')
                    try:
                        cookies_map = dict([x.split('=') for x in cookies.split(';')])
                        ga_cookie = cookies_map['_ga']
                    except ValueError:
                        ga_cookie = None
                        
                    proceed = False
                    threshold = timezone.now() - timedelta(hours=24)
                    
                    ip_check = FaucetDisbursement.objects.filter(
                        ip_address=ip_address,
                        date_created__gt=threshold
                    )
                    slp_check = FaucetDisbursement.objects.filter(
                        slp_address=slp_address,
                        date_created__gt=threshold
                    )
                    if ip_check.count() == 0 and slp_check.count() == 0:
                        proceed = True
                        if ga_cookie:
                            cookie_check = FaucetDisbursement.objects.filter(
                                ga_cookie=ga_cookie,
                                date_created__gt=threshold
                            )
                            if cookie_check.count():
                                proceed = False
                    if not proceed:
                        response['error'] = 'We detected that you already submitted a request recently. '
                        response['error'] += 'You can only request once every 24 hours. Try again tomorrow!'
                else:
                    proceed = False
                    response['error'] = 'Our daily limit for the amount of SPICE to give out has been reached. Try again tomorrow!'

                if proceed:
                    amount = 20
                    n = randint(19, 76)
                    if n == 19:
                        amount = 0
                    elif n == 76:
                        amount = 500
                    else:
                        amount = n

                    faucet_tx = FaucetDisbursement(
                        slp_address=slp_address,
                        ip_address=ip_address,
                        ga_cookie=ga_cookie,
                        amount=amount
                    )
                    faucet_tx.save()

                    task = process_faucet_request.delay(faucet_tx.id)
                    response['task_id'] = task.task_id
                    response['amount'] = amount
                    response['success'] = True
        else:
            response['error'] = "The captcha system marked you as a potential bot.<br>Either you are a real or you took so long to submit the form and the captcha token just expired.<br>If it's the latter, then just go back to the form and try again."

        return JsonResponse(response)


class SpiceFaucetTaskView(View):

    def post(self, request):
        data = json.loads(request.body)
        task_id = data.get('task_id')        
        res = AsyncResult(task_id)
        response = {'success': False}

        if res.ready():
            result = res.result
            if result['status'] == 'success':               
                tx_url = '\nhttps://explorer.bitcoin.com/bch/tx/' + result['txid']
                response = {
                    'tx_url': tx_url,
                    'success': True
                }
            elif result['status'] == 'failure':
                response['error'] = 'There was an error in processing your request'
        return JsonResponse(response)


class SpiceFeedContentDetailsView(View):
    
    def get(self, request, id):
        response = None
        file_type= None
        post = {}
        top_tipper = {}      
        original_message = ''
        item = Content.objects.get(pk=id)

        if item.post_to_spicefeed:
            chat_name = ''
            original_message = ''
            #Get tipped message
            if item.source == 'telegram':   
                user = item.recipient.telegram_display_name
                date = item.details['message']['reply_to_message']['date']
                date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                if 'text' in item.details['message']['reply_to_message'].keys():
                    original_message = item.details['message']['reply_to_message']['text']
                if 'chat' in item.details['message'].keys():
                    if 'title' in item.details['message']['chat'].keys(): 
                        chat_name = item.details['message']['chat']['title']
            elif item.source == 'twitter':
                user = item.recipient.twitter_screen_name
                date = item.details['replied_to']['created_at']
                date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
                if 'text' in item.details['replied_to'].keys():
                    original_message = item.details['replied_to']['text']
            elif item.source == 'reddit':
                user = item.recipient.reddit_username
                date = item.details['comment_details']['date_created']
                date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                if 'text' in item.details['submission_details'].keys():
                    original_message = item.details['submission_details']['text']
                if 'subreddit' in item.details['submission_details'].keys():
                    chat_name = item.details['submission_details']['subreddit']
            post = {
                'tipped_user_name': user,
                'original_message': original_message,
                'date': date,
                'source': item.source,
                'chat_name': chat_name
            }        

            # Get media URL
            post['original_message_mediapath'] = item.get_media_url()

            #Get first tipper
            first_tipper = {}        
            if item.source == 'telegram':
                first_tipper['tipper_user'] = item.sender.telegram_display_name
                first_tipper['tipper_message'] = item.details['message']['text']            
            elif item.source == 'twitter':
                first_tipper['tipper_user'] = item.sender.twitter_screen_name
                first_tipper['tipper_message'] = item.details['reply']['text']
            elif item.source == 'reddit':
                first_tipper['tipper_user'] = item.sender.reddit_username
                first_tipper['tipper_message'] = item.details['comment_details']['comment_body']
            first_tipper['tip_amount'] = item.tip_amount

            #List of all tippers
            contents={}
            date = None
            contents = Content.objects.filter(parent=item)
            post['total_tips'] = 0

            if item.source == 'telegram':
                date = item.details['message']['date']
                date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                sender = item.sender.telegram_display_name
                message = item.details['message']['text']
            elif item.source == 'twitter':
                date = item.details['reply']['created_at']
                date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
                sender = item.sender.twitter_screen_name
                message = item.details['reply']['text']
            elif item.source == 'reddit':
                date = item.details['comment_details']['date_created']
                date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                sender = item.sender.reddit_username
                message = item.details['comment_details']['comment_body']
            tips = [{
                'tipper': sender,
                'amount': '{0:.10f}'.format(item.tip_amount).rstrip('0').rstrip('.'),
                'date': date,
                'message': message

            }]
            total_tips = item.tip_amount
            for content in contents:                
                if item.source == 'telegram':
                    date = content.details['message']['date']
                    date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                    sender = content.sender.telegram_display_name
                    message = content.details['message']['text']    
                elif item.source == 'twitter':
                    date = content.details['reply']['created_at']
                    date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
                    sender = content.sender.twitter_screen_name
                    message = content.details['reply']['text']
                elif item.source == 'reddit':
                    date = content.details['comment_details']['date_created']
                    date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                    sender = content.sender.reddit_username
                    message = content.details['comment_details']['comment_body']
                tipper = {
                    'tipper': sender,
                    'amount': '{0:.10f}'.format(content.tip_amount).rstrip('0').rstrip('.'),
                    'date': date,
                    'message': message
                }
                total_tips += content.tip_amount
                tips.append(tipper)
            tips = sorted(tips, key = lambda i: i['amount'],reverse=True)
            try:
                cont = Content.objects.get(pk=tips[0]['id'])
            except KeyError:
                pass       

            post['total_tips'] = '{0:.10f}'.format(total_tips).rstrip('0').rstrip('.')
            # Get more from recipient
            more={}
            more_content=[]
            more = Content.objects.filter(
                post_to_spicefeed=True,
                recipient=item.recipient,
                parent=None
            ).exclude(parent=item.parent, pk=item.id)[:5]

            for temp in more:          
                original_message = ''
                chat_name = ''
                if temp.source == 'telegram':
                    tipped_user_name = temp.recipient.telegram_display_name
                    date = temp.details['message']['reply_to_message']['date']
                    date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                    if 'text' in temp.details['message']['reply_to_message'].keys():
                        original_message = temp.details['message']['reply_to_message']['text']
                    if 'chat' in item.details['message'].keys():
                        if 'title' in item.details['message']['chat'].keys(): 
                            chat_name = item.details['message']['chat']['title']
                elif temp.source == 'twitter':
                    tipped_user_name = temp.recipient.twitter_screen_name
                    date = temp.details['replied_to']['created_at']
                    date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
                    if 'text' in temp.details['replied_to'].keys():
                        original_message = temp.details['replied_to']['text']
                elif temp.source == 'reddit':
                    tipped_user_name = temp.recipient.reddit_username
                    date = temp.details['comment_details']['date_created']
                    date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                    if 'text' in temp.details['submission_details'].keys():
                        original_message = temp.details['submission_details']['text']
                    if 'subreddit' in temp.details['submission_details'].keys():
                        chat_name = item.details['submission_details']['subreddit']
                content = { 
                    'date': date,
                    'original_message': original_message,
                    'source': temp.source,
                    'tipped_user_name': tipped_user_name,
                    'id': temp.id,
                    'chat_name': chat_name
                }            
                content['original_message_mediapath'] = ''                        

                #get total tips
                total_tips = temp.tip_amount
                more_contents = Content.objects.filter(parent=temp)
                for more_item in more_contents:
                    total_tips += more_item.tip_amount

                content['total_tips'] = '{0:.10f}'.format(total_tips).rstrip('0').rstrip('.')
                content['original_message_mediapath'] = temp.get_media_url()
                more_content.append(content)

            response = {            
                'post': post,
                'first_tipper': first_tipper,            
                'all_tips': tips,
                'more_content': more_content
            }

        else:
            response = {'success': False, 'error': 'private_content'}           

        return JsonResponse(response)


@api_view(['GET'])
def contentpage(request,id):
    item = Content.objects.get(pk=id)   
    media_type = None    
    try:             
        if item.source == 'telegram':   
            user = item.recipient.telegram_display_name
            date = item.details['message']['reply_to_message']['date']
            date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
            original_message = item.details['message']['reply_to_message']['text']
        elif item.source == 'twitter':
            user = item.recipient.twitter_screen_name
            date = item.details['replied_to']['created_at']
            date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
            original_message = item.details['replied_to']['text']
        elif item.source == 'reddit':
            user = item.recipient.reddit_username
            date = item.details['comment_details']['date_created']
            date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
            original_message = item.details['submission_details']['text']
    except KeyError:
        original_message = ''        
    if 'message' in item.details.keys():
        if 'photo' in item.details['message']['reply_to_message'].keys():
            media_type = 'photo'
        elif 'video' in item.details['message']['reply_to_message'].keys():
            media_type = 'video'
    post = {
        'id': id,
        'tipped_user_name': user,
        'original_message': original_message,
        'date': date,
        'source': item.source,
        'media_type': media_type        
    }        

    post['original_message_mediapath'] = item.get_media_url()

    date = None
    contents = Content.objects.filter(parent=item)
    post['total_tips'] = 0

    if item.source == 'telegram':
        date = item.details['message']['date']
        date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
        sender = item.sender.telegram_display_name
        message = item.details['message']['text']
    elif item.source == 'twitter':
        date = item.details['reply']['created_at']
        date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
        sender = item.sender.twitter_screen_name
        message = item.details['reply']['text']
    elif item.source == 'reddit':
        date = item.details['comment_details']['date_created']
        date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
        sender = item.sender.reddit_username
        message = item.details['comment_details']['comment_body']
    tips = [{
        'tipper': sender,
        'amount': '{0:.10f}'.format(item.tip_amount).rstrip('0').rstrip('.'),
        'date': date,
        'message': message

    }]
    total_tips = item.tip_amount
    for content in contents:                
        if item.source == 'telegram':
            date = content.details['message']['date']
            date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
            sender = content.sender.telegram_display_name
            message = content.details['message']['text']    
        elif item.source == 'twitter':
            date = content.details['reply']['created_at']
            date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
            sender = content.sender.twitter_screen_name
            message = content.details['reply']['text']
        elif item.source == 'reddit':
            date = content.details['comment_details']['date_created']
            date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
            sender = content.sender.reddit_username
            message = content.details['comment_details']['comment_body']
        tipper = {
            'tipper': sender,
            'amount': '{0:.10f}'.format(content.tip_amount).rstrip('0').rstrip('.'),
            'date': date,
            'message': message
        }
        total_tips += content.tip_amount
        tips.append(tipper)
    tips = sorted(tips, key = lambda i: i['amount'],reverse=True)
    try:
        cont = Content.objects.get(pk=tips[0]['id'])
    except KeyError:
        pass       
    post['total_tips'] = '{0:.10f}'.format(total_tips).rstrip('0').rstrip('.')
    return render(request, 'main/index.html', post)


class UserSearchView(View):

    def get(self, request, user):
        item = user.replace('-', ' ')
        #media_only = request.GET.get('media_only', 'false')
        success = False
        response  = {}
        user = None
        user_content = []

        if item.startswith('userid'):
            user_id = item.split('userid')[-1]
            user = User.objects.get(id=user_id)
            success = True
            
        # users = User.objects.all()
        # user = None
        # user_content = []        
        # for u in users:            
        #     if u.telegram_display_name == item or u.twitter_screen_name == item or u.reddit_username == item:                
        #         user = u
        #         success = True
        #         break
        
        if success and user:  
            #user data
            details = {}
            if user.telegram_id:
                details['username'] = user.telegram_display_name
                details['source'] = 'telegram'
            if user.twitter_id:
                details['username'] = user.twitter_screen_name
                details['source'] = 'twitter'
            if user.reddit_id:
                details['username'] = user.reddit_username
                details['source'] = 'reddit'

            total_received = Content.objects.filter(
                recipient=user
            ).aggregate(Sum('tip_amount'))['tip_amount__sum'] or 0
            total_tipped = Content.objects.filter(
                sender=user
            ).aggregate(Sum('tip_amount'))['tip_amount__sum'] or 0

            details['total_tips_received'] = total_received
            details['total_tips_sent'] = total_tipped
            details['pof'] = user.pof_display

            #received            
            try:
                received_contents = Content.objects.filter(
                    recipient=user,
                    post_to_spicefeed=True,
                    parent=None
                ).order_by('-id')                
            except Content.DoesNotExist:
                received_contents = None            

            received = []
            for content in received_contents:
                original_message = ''
                chat_name = ''
                tipper_message = ''
                if content.source == 'telegram':   
                    date = content.details['message']['date']                 
                    sender_username = content.sender.telegram_display_name
                    tipper_message = content.details['message']['text']
                    if 'text' in content.details['message']['reply_to_message'].keys():
                        original_message = content.details['message']['reply_to_message']['text']
                    if 'chat' in content.details['message'].keys():
                        if 'title' in content.details['message']['chat'].keys(): 
                            chat_name = content.details['message']['chat']['title']
                if content.source == 'twitter':            
                    date = content.details['reply']['created_at']       
                    sender_username = content.sender.twitter_screen_name
                    tipper_message = content.details['reply']['text']
                    if 'text' in content.details['replied_to'].keys():
                        original_message = content.details['replied_to']['text']
                if content.source == 'reddit':                   
                    date = content.details['comment_details']['date_created']
                    sender_username = content.sender.reddit_username
                    tipper_message =content.details['comment_details']['comment_body']
                    if 'text' in content.details['submission_details'].keys():
                        original_message = content.details['submission_details']['text']
                    if 'subreddit' in content.details['submission_details'].keys():
                        chat_name = content.details['submission_details']['subreddit']

                #total = Content.objects.filter(recipient_content_id=content.recipient_content_id)
                #total_tips = 0
                #for item in total:
                #    total_tips+=item.tip_amount

                int_amount = content.tip_amount * 100000000
                temp = {
                    'created_at': content.date_created.isoformat(),
                    'permalink': content.id,
                    'service': content.source,
                    'int_amount': int_amount,
                    'string_amount': str(int_amount),                  
                    'total_tips': content.total_tips,                  
                    'tipped_user_name': details['username'],
                    'tipper_user': sender_username,
                    'tipper_message': tipper_message,
                    'tipper_message_date': date,
                    'original_message': original_message,                                           
                    'original_message_mediapath': content.get_media_url(),
                    'additional_tippers': []
                }                
                user_content.append(temp)

            response = {
                'success': True,
                'details': details,
                'contents': user_content
            }

        else:
            response['success'] = False
            possible_user = []
            # User.objects.filter(tips_received)
            combined_qs = User.objects.filter(
                Q(telegram_user_details__username__icontains=item) |
                Q(telegram_user_details__first_name__icontains=item) |
                Q(twitter_user_details__screen_name__icontains=item) |
                Q(reddit_user_details__username__icontains=item)
            )
            if combined_qs.count() > 0:
                first10 = combined_qs.order_by('-id')[0:10]
                possible_user = [{'id': x.id, 'username': x.get_username(), 'source': x.get_source()} for x in first10]

            response['possible_user'] = possible_user

        return JsonResponse(response)
