from __future__ import absolute_import, unicode_literals
from subprocess import Popen, PIPE
from celery import shared_task
from celery.signals import task_failure
from main.models import (
    Withdrawal,
    Media,
    Deposit,
    Content,
    FaucetDisbursement,
    User,
    Transaction
)
from main.utils.twitter import TwitterBot
from main.utils.reddit import RedditBot
from main.utils.account import compute_balance
from django.conf import settings
from django.utils import timezone
from random import random
from datetime import datetime, timedelta
from PIL import Image
import requests
import logging
import traceback
import redis
import arrow
import os
import json

from gcloud import storage
from oauth2client.service_account import ServiceAccountCredentials 
from django.core.paginator import Paginator
from requests import *


logger = logging.getLogger(__name__)


    
@task_failure.connect
def handle_task_failure(**kw):
    logger.error(traceback.format_exc())
    return traceback.format_exc()

@shared_task(rate_limit='20/s', queue='telegram')
def send_telegram_message(message, chat_id, update_id):
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }
    url = 'https://api.telegram.org/bot'
    response = requests.post(
        f"{url}{settings.TELEGRAM_BOT_TOKEN}/sendMessage", data=data
    )
    if response.status_code == 200:
        if update_id:
            settings.REDISKV.sadd('telegram_msgs', update_id)
            if settings.REDISKV.scard('telegram_msgs') >= 10000:
                settings.REDISKV.spop('telegram_msgs')


@shared_task(queue='twitter')
def twitter_unreplied_post():
    bot = TwitterBot()
    bot.check_failed_reply()
    


@shared_task(queue='twitter')
def send_twitter_message(message, user_id):
    bot = TwitterBot()
    bot.send_direct_message(user_id, message)


@shared_task(queue='reddit')
def send_reddit_message(message, username):
    from main.models import Response
    bot = RedditBot()
    subject = 'Successful Deposit'
    body = {
        'message':message,
        'subject':subject,
        'sender':username
    }
    resp = Response(
        response_type='direct_message',
        body=body                    
    )
    resp.save()
    bot.send_message(message, subject, username, resp.id)
    

@shared_task(rate_limit='20/s', queue='withdrawal')
def withdraw_spice_tokens(withdrawal_id, chat_id=None, update_id=None, user_id=None, bot='telegram'):
    withdrawal = Withdrawal.objects.get(
        id=withdrawal_id
    )
    if not withdrawal.date_completed and not withdrawal.date_failed:
        balance = compute_balance(withdrawal.user.id)
        if balance >= withdrawal.amount:
            cmd = 'node /code/spiceslp/send-tokens.js {0} {1} withdrawal'.format(
                withdrawal.address,
                withdrawal.amount
            )
            p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
            stdout, _ = p.communicate()
            result = stdout.decode('utf8')
            logger.info(result)
            status = result.splitlines()[-1].strip()
            if status == 'success':
                # Update withdrawal completion and txid
                withdrawal.date_completed = timezone.now()
                txid = result.splitlines()[-2].split('/tx/')[-1]
                withdrawal.transaction_id = txid
                withdrawal.save()
                # Record transaction
                transaction = Transaction(
                    user=withdrawal.user, 
                    amount=withdrawal.amount, 
                    transaction_type='Outgoing'
                )
                transaction.save()
                # Send notifications
                message1 = 'Your withdrawal of %s SPICE tokens has been processed.' % withdrawal.amount
                message1 += '\nhttps://explorer.bitcoin.com/bch/tx/' + txid
                if bot == 'telegram':
                    send_telegram_message.delay(message1, chat_id, update_id)
                elif bot == 'twitter':
                    send_twitter_message.delay(message1, user_id)
                elif bot == 'reddit':
                    send_reddit_message.delay(message1, user_id)

                balance2 = compute_balance(withdrawal.user.id)
                balance2 = '{:0,.2f}'.format(balance2)
                message2 = 'Your updated balance is %s \U0001f336 SPICE.' % balance2
                if bot == 'telegram':
                    send_telegram_message.delay(message2, chat_id, update_id)
                elif bot == 'twitter':
                    send_twitter_message.delay(message2, user_id)
                elif bot == 'reddit':
                    send_reddit_message.delay(message2, user_id)

            elif status == 'failure':
                withdrawal.date_failed = timezone.now()
                withdrawal.save()
                message = 'Processing of your withdrawal request failed:'
                message += '\n' + result.splitlines()[-2].strip()
                if bot == 'telegram':
                    send_telegram_message.delay(message, chat_id, update_id)
                elif bot == 'twitter':
                    send_twitter_message.delay(message, user_id)
                elif bot == 'reddit':
                    send_reddit_message.delay(message, user_id)


@shared_task(queue='reddit')
def check_reddit_mentions():
    bot = RedditBot()
    bot.process_mentions()


@shared_task(queue='reddit')
def check_reddit_messages():
    bot = RedditBot()
    bot.process_messages()


@shared_task(queue='twitter')
def check_twitter_mentions():
    bot = TwitterBot()
    bot.process_mentions()


@shared_task(queue='twitter')
def check_twitter_messages():
    bot = TwitterBot()
    bot.process_direct_messages()


@shared_task(queue='deposit')
def check_confirmations():
    deposits = settings.REDISKV.smembers('big_deposits')
    for key in deposits:
        args = key.decode().split('__')
        if len(args) == 3:
            txn_id, slp_address, amount = args
            proceed = False
            try:
                user = User.objects.get(
                    simple_ledger_address=slp_address
                )
                proceed = True
            except User.DoesNotExist:
                pass
            if proceed:
                url = 'https://rest.bitcoin.com/v2/transaction/details/' + txn_id
                resp = requests.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if data['confirmations'] > 1:
                        deposit, created = Deposit.objects.get_or_create(
                            user=user,
                            transaction_id=txn_id,
                            amount=float(amount)
                        )
                        if created:
                            logger.info('Big deposit: %s, confirmed' % txn_id)
                        # Remove from set
                        settings.REDISKV.srem('big_deposits', key)
                    else:
                        logger.info('Big deposit: %s, waiting for confirmation' % txn_id)
            else:
                settings.REDISKV.srem('big_deposits', key)


@shared_task(queue='deposit')
def user_handlers():
    # Run check confirmations
    check_confirmations.delay()
    # Run checking of individual user's deposit addresses
    threshold = timezone.now() - timedelta(hours=6)
    users = User.objects.filter(
        last_activity__gt=threshold
    ).values('id')[:1000]
    p = Paginator(users, 500)
    for i in p.page_range:
        subvars = p.page(i)
        check_deposits.delay(objList=list(subvars.object_list))


# Disabled this coz it might cause the bot to get flagged for spamming
# @shared_task(queue='twitter')
# def follow_twitter_user():    
#     bot = TwitterBot()
#     bot.follow_user()


def slpsocket_notify(*args, **kwargs):
    from main.models import User, Deposit
    from django.db import IntegrityError
    addr = kwargs['addr']
    txn_id = kwargs['txn_id']
    amt = kwargs['amt']
    user = User.objects.filter(simple_ledger_address=addr)
    if user.exists():
        qs = Deposit.objects.filter(transaction_id=txn_id)
        if not qs.exists():
            usr = user.first()
            deposit = Deposit()
            deposit.amount = amt
            deposit.user = usr
            deposit.transaction_id = txn_id
            try:
                deposit.save()
                send_notif = True
            except IntegrityError as e:
                send_notif = False
            if send_notif:
                amount = '{:0,.2f}'.format(float(deposit.amount))
                message1 = 'Your deposit transaction of %s SPICE has been credited to your account.' % amount
                chat_id = usr.telegram_id
                message1 += '\nhttps://explorer.bitcoin.com/bch/tx/' + txn_id
                if usr.telegram_id:
                    send_telegram_message.delay(message1, chat_id, str(random()).replace('0.', ''))
                if usr.twitter_id:
                    send_twitter_message.delay(message1, usr.twitter_id)
                if usr.reddit_id:
                    send_reddit_message.delay(message1, usr.reddit_username)
                logger.info(f"Deposited {amt} to {addr}")


@shared_task(queue='slpsocket')
def slpsocket_filter(*args, **kwargs):
    #from sseclient import SSEClient
    from django.conf import settings
    import requests
    import json
    url = 'https://slpsocket.fountainhead.cash/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjogewogICAgfQogIH0KfQ==' 
    resp = requests.get(url, stream=True)
    previous = ''
    for content in resp.iter_content(chunk_size=1024*1024):
        loaded_data = None
        try:
            content = content.decode('utf8')
            if '"tx":{"h":"' in previous:
                data = previous + content
                data = data.strip().split('data: ')[-1]
                loaded_data = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            pass
        previous = content
        if loaded_data is not None: 
            if len(loaded_data['data']) > 0: 
                info = loaded_data['data'][0]
                if 'slp' in info.keys():
                    if 'detail' in info['slp'].keys():
                        if 'tokenIdHex' in info['slp']['detail'].keys():
                            if info['slp']['detail']['tokenIdHex'] == settings.SPICE_TOKEN_ID:
                                amt = float(info['slp']['detail']['outputs'][0]['amount'])
                                slp_address = info['slp']['detail']['outputs'][0]['address']
                                if 'tx' in info.keys():
                                    # There are transactions that don't have Id. Weird - Reamon
                                    txn_id = info['tx']['h']
                                    logger.info('<-!-!-!- New Deposit Found [%s] %s -!-!-!->' % (amt , txn_id))
                                    if amt <= 50000:
                                        kwargs = {
                                            'addr':slp_address,
                                            'amt':amt,
                                            'txn_id':txn_id
                                        }
                                        slpsocket_notify(**kwargs)
                                    else:
                                        key = txn_id + '__' + slp_address + '__' + str(amt)
                                        if not settings.REDISKV.sismember('big_deposits', key):

                                            # Add txn_id to big deposits
                                            settings.REDISKV.sadd('big_deposits', key)
                                            
                                            user_check = User.objects.filter(simple_ledger_address=slp_address)
                                            if user_check.exists():
                                                user = user_check.first()
                                                amount = '{:0,.2f}'.format(float(amt))
                                                message1 = 'We detected your deposit of %s SPICE.' % amount
                                                message1 += ' For any amount greater than 50k we only credit it to your account after at least 1 confirmation.'
                                                message1 += ' We will udpate you once your deposit is credited.'
                                                if user.telegram_id:
                                                    chat_id = user.telegram_id
                                                    send_telegram_message.delay(message1, chat_id, str(random()).replace('0.', ''))
                                                if user.twitter_id:
                                                    send_twitter_message.delay(message1, user.twitter_id)
                                                if user.reddit_id:
                                                    send_reddit_message.delay(message1, user.reddit_username)
                                                
                                                # Update last activity timestamp
                                                user.last_activity = timezone.now()
                                                user.save()


@shared_task(queue='deposit')
def check_deposits(*args, **kwargs):
    from main.models import User, Deposit
    from django.conf import settings
    from django.db import IntegrityError
    objList = kwargs['objList']
    all_deposits = []
    for obj in objList:
        id = obj['id']
        user = User.objects.get(id=id)
        spice_addr = user.simple_ledger_address
        if spice_addr:         
            token_id = settings.SPICE_TOKEN_ID
            url = f"https://rest.bitcoin.com/v2/slp/transactions/{token_id}/{spice_addr}"
            
            transaction_data = []
            resp = requests.get(url)
            if resp.status_code == 200:
                transaction_data = resp.json()

            # save transaction to db
            for transaction in transaction_data:
                logger.info(transaction)
                txn_id = transaction['txid']
                txn_type = transaction['tokenDetails']['detail']['transactionType']
                if txn_type == 'SEND':
                    if Deposit.objects.filter(transaction_id=txn_id).exists():
                        continue
                    else:
                        txn_outputs = transaction['tokenDetails']['detail']['outputs']
                        for i, output in enumerate(txn_outputs):
                            slp_address = output['address']
                            if slp_address == spice_addr:
                                deposit = Deposit()
                                deposit.amount = float(output['amount'])
                                deposit.user = user
                                deposit.transaction_id = txn_id
                                try:
                                    deposit.save()
                                    send_notif = True
                                except IntegrityError as e:
                                    send_notif = False
                                if send_notif:
                                    amount = '{:0,.2f}'.format(deposit.amount)
                                    message1 = 'Your deposit transaction of %s SPICE has been credited to your account.' % amount
                                    chat_id = user.telegram_id
                                    message1 += '\nhttps://explorer.bitcoin.com/bch/tx/' + txn_id
                                    if user.telegram_id:
                                        send_telegram_message.delay(message1, chat_id, str(random()).replace('0.', ''))
                                    if user.twitter_id:
                                        send_twitter_message.delay(message1, user.twitter_id)
                                    all_deposits.append('%s - %s' % (chat_id, amount))
    return all_deposits


@shared_task(queue='media', max_retries=10, soft_time_limit=60)
def download_upload_file(file_id, file_type, content_id):
    media_check = Media.objects.filter(file_id=file_id)
    if not media_check.count():
        # Get the download url
        bot_token = settings.TELEGRAM_BOT_TOKEN
        response = requests.get('https://api.telegram.org/bot' + bot_token + '/getFile?file_id=' + file_id)
        
        if response:
            file_path = response.json()['result']['file_path']
            download_url = 'https://api.telegram.org/file/bot' + bot_token + '/' + file_path

            if file_type in ['photo', 'sticker']:
                if file_type == 'photo':
                    # Download photo  
                    r = requests.get(download_url)
                    temp_name = '/tmp/' + file_id + '-temp' + '.jpg'
                    filename = '/tmp/' + file_id + '.jpg'
                    with open(temp_name, 'wb') as f:  
                        f.write(r.content)
                    im = Image.open(temp_name).convert("RGB")
                    im.save(filename,"jpeg")
                    os.remove(temp_name) 
                    fname = file_id + '.jpg'
                if file_type == 'sticker':
                    img = Image.open(requests.get(download_url, stream=True).raw)
                    img.save('/tmp/' + file_id + '.png', 'png')
                    fname = file_id + '.png'
                
            elif file_type in ['animation', 'video', 'video_note']:
                # Download video  
                r = requests.get(download_url)
                with open('/tmp/' + file_id + '.mp4', 'wb') as f:  
                    f.write(r.content)

                fname = file_id + '.mp4'
            elif file_type in ['audio']:
                # Download audio
                ext = file_path.split('.')[-1]
                r = requests.get(download_url)
                with open('/tmp/' + file_id + '.' + ext, 'wb') as f:  
                    f.write(r.content)
                fname = file_id + '.' + ext

            # Upload photo
            json_creds = os.path.join(settings.BASE_DIR, 'spice-slp-token-e17e0c3bb681.json')
            credentials = ServiceAccountCredentials.from_json_keyfile_name(json_creds)  
            client = storage.Client(credentials=credentials, project='spice-slp-token')  
            bucket = client.get_bucket('spice-slp-media')   

            blob = bucket.blob('/tmp/' + fname)   
            blob = bucket.blob(fname)  
            blob.upload_from_filename('/tmp/' + fname)  
            blob.make_public()

            # After uploading delete the file
            os.remove('/tmp/' + fname) 
            
            media = Media(
                file_id=file_id,
                content_id=content_id,
                url=blob.public_url
            )
            media.save()


@shared_task(queue='media')
def check_pending_media():
    media = Media.objects.last()
    start_id = media.content.id
    contents = Content.objects.filter(id__gte=start_id, post_to_spicefeed=True).order_by('-id')
    file_type = ''
    file_id = ''

    for content in contents:                
        data = content.details

        if content.source == 'telegram':
            if 'photo' in data['message']['reply_to_message'].keys():
                file_type = 'photo'
                file_id = data['message']['reply_to_message']['photo'][-1]['file_id']

            elif 'sticker' in data['message']['reply_to_message'].keys():
                file_type = 'sticker'
                file_id = data['message']['reply_to_message']['sticker']['file_id']

            elif 'animation' in data['message']['reply_to_message'].keys():
                file_type = 'animation'
                file_id = data['message']['reply_to_message']['animation']['file_id']

            elif 'video' in data['message']['reply_to_message'].keys():
                file_type = 'animation'
                file_id = data['message']['reply_to_message']['video']['file_id']

            elif 'video_note' in data['message']['reply_to_message'].keys():
                file_type = 'animation'
                file_id = data['message']['reply_to_message']['video_note']['file_id']
                # download_upload_file.delay(file_id, file_type, content.id)
            
            elif 'voice' in data['message']['reply_to_message'].keys():
                file_type = 'audio'
                file_id = data['message']['reply_to_message']['voice']['file_id']

            elif 'document' in data['message']['reply_to_message'].keys():
                file_type = data['message']['reply_to_message']['document']['mime_type']
                if 'image' in file_type:
                    file_type = 'photo'
                file_id = data['message']['reply_to_message']['document']['file_id']
            download_upload_file.delay(file_id, file_type, content.id)


@shared_task(queue='withdrawal')
def check_pending_withdrawals():
    pending_withdrawals = Withdrawal.objects.filter(
        date_completed__isnull=True,
        date_failed__isnull=True
    )
    for withdrawal in pending_withdrawals:
        withdraw_spice_tokens.delay(
            withdrawal.id,
            chat_id=withdrawal.user.telegram_id
        )


@shared_task(queue='withdrawal')
def process_faucet_request(faucet_disbursement_id):
    faucet_tx = FaucetDisbursement.objects.get(
        id=faucet_disbursement_id
    )
    response = {'status': False}
    if not faucet_tx.date_completed:
        if faucet_tx.amount > 0:
            cmd = 'node /code/spiceslp/send-tokens.js {0} {1} faucet'.format(
                faucet_tx.slp_address,
                faucet_tx.amount
            )
            p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
            stdout, _ = p.communicate()
            result = stdout.decode('utf8')
            logger.info(result)     
            status = result.splitlines()[-1].strip()  
            response = {'status': status}
            if status == 'success':
                txid = result.splitlines()[-2].split('/tx/')[-1]
                faucet_tx.transaction_id = txid
                faucet_tx.date_completed = timezone.now()
                faucet_tx.save()
                response['txid'] = txid
            if status == 'failure':            
                response['error'] = 'There was an error in processing your request'
        else:
            faucet_tx.date_completed = timezone.now()
            faucet_tx.save()
    return response