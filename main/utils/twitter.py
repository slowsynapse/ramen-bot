from django.conf import settings
from django.utils import timezone
from main.utils.responses import get_response
from main.utils.account import compute_balance
from main.models import User, Content, Transaction, Withdrawal, Response
from celery import current_app

from django.db.models import Sum

import emoji
import twitter
import logging
import time
import redis
import json
import random
import re


logger = logging.getLogger(__name__)

class TwitterBot(object):

    def __init__(self):
        self.authenticate()


    def authenticate(self):
        self.api = twitter.Api(
            consumer_key=settings.TWITTER_CONSUMER_KEY,
            consumer_secret=settings.TWITTER_CONSUMER_SECRET,
            access_token_key=settings.TWITTER_ACCESS_KEY,
            access_token_secret=settings.TWITTER_ACCESS_SECRET
        )    

    def is_valid_tip_pattern(self, text): 
        if '@'+settings.TWITTER_BOT_NAME in text: 
            substrings = text.split(' ') 
            for substring in substrings: 
                if substring == '': 
                    continue 
                if not substring.startswith('@') and not substring[0] in emoji.UNICODE_EMOJI: 
                    return False 
                return True 
        return False 

    def get_tip_amount(self, text):
        tip_value = 0
        bot_name = '%s%s' % ('@',settings.TWITTER_BOT_NAME)
        text = str(text)
        if  bot_name in text:
            pattern = ''
            if bot_name == '@spicetokens':
                pattern = r'\b[^\w*\d*\D*$]?\d*\s*@spicetokens\s*\d*'
            elif bot_name == '@chillbotskysta1':
                pattern = r'\b[^\w*\d*\D*$]?\d*\s*@chillbotskysta1\s*\d*'
            results = re.findall(pattern,text)
            if len(results) > 0:
                for result in results:
                    for item in result.split(' '):
                        if item.strip(' ') and not item.startswith('@'):
                            tip_value+=float(item)
                            break

        if self.is_valid_tip_pattern(text):
            results = re.findall(r'\@\w+',text)
            for r in results: text = text.replace(r, '')
            text = text.lstrip('')
            for char in settings.ALLOWED_SYMBOLS.keys():
                multiplier = text.count(char)
                if char == '\U0001F344':
                    value = random.choice(range(0,1000))
                    text = text.replace(char,"")
                else:   
                    value = settings.ALLOWED_SYMBOLS[char]
                    if value:
                        text = text.replace(char,"")
                tip_value += (value * multiplier)

            text = text.lstrip('')
        # if text.startswith('tip'):
        #     results = re.findall(r'[+-]? *(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', text)
        #     tip_value += sum([ float(r) for r in results])
        if tip_value == 0:
            if not self.has_emoji(text):
                results = re.findall(r'[+-]? *(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', text)
                try:
                    tip_value = float(results[-1])
                except IndexError:
                    pass
        return tip_value

    def has_emoji(self, text):
        for char in text:
            if char in emoji.UNICODE_EMOJI or char == "+":
               return True
        return False
        
    def check_frienship(self, user_id):
        friendship = self.api.LookupFriendship(
            user_id=user_id, 
            return_json=True
        )
        if 'followed_by' in friendship[0]['connections']:
            return True
        else:
            return False

    # def follow_user(self):
    #     temp = self.api.GetFriends()
    #     friends = [str(f.id) for f in temp] 

    #     users = User.objects.exclude(twitter_id='')
    #     for user in users:            
    #         if friends.count(user.twitter_id) == 0:                
    #             try:                    
    #                 follow = self.api.CreateFriendship(
    #                     user_id=user.twitter_id,
    #                     Follow=True,
    #                     retweets=True
    #                 )
    #                 break
    #             except:
    #                 pass 

    def compute_POF(self, user_id, text):
        user = User.objects.get(id=user_id)     
        received = Content.objects.filter(recipient=user).aggregate(Sum('tip_amount'))
        tipped = Content.objects.filter(sender=user).aggregate(Sum('tip_amount'))

        received_amount_full = received['tip_amount__sum']
        tipped_amount = tipped['tip_amount__sum']
        if not received['tip_amount__sum']:
            received_amount_full = 1 # Set to 1 to avoid division by zero error
        if not tipped['tip_amount__sum']:
            tipped_amount = 0

        received_amount_half = received_amount_full / 2
        pof_percentage = (tipped_amount/received_amount_full)*100
        pof_rating = ((tipped_amount/received_amount_half)*100) / 20
        
        if pof_rating > 5:
            pof_rating = 6

        user.pof = {'pof_rating': pof_rating, 'pof_percentage': pof_percentage}
        user.save()

        return round(pof_percentage), round(pof_rating)

    def handle_tipping(self, amount, sender_id, recipient_id, data):        
        sender = User.objects.get(id=sender_id)
        recipient = User.objects.get(id=recipient_id)
        success = False
        content_check = Content.objects.filter(source='twitter',details__reply__id=data['id'])

        proceed = False
        if not content_check.count():            
            one_satoshi = 0.00000001
            if amount >= one_satoshi:
                balance = compute_balance(sender.id)
                if balance >= amount:
                    proceed = True
                else:
                    try:
                        self.send_direct_message(
                            sender.twitter_id,
                            'Hi! You tried to tip but your SPICE balance is insufficient.'
                        )
                        success = True
                    except twitter.error.TwitterError as exc:
                        logger.error(repr(exc))                
            
        if proceed:            
            parent = None
            recipient_content_id = None
            content_id_json = None

            original_status = self.api.GetStatus(data['in_reply_to_status_id'], trim_user=True)
            content_details = {
                'reply': data,
                'replied_to': original_status.AsDict()
            }            
            # Getting parent tipper    
            recipient_content_id = {
                'status_id': content_details['reply']['in_reply_to_status_id']
            }
            
            content_id_json = json.dumps(recipient_content_id)

            if Content.objects.filter(recipient_content_id=content_id_json).exists():
                parent = Content.objects.get(parent=None, recipient_content_id=content_id_json)

            # Save content to database
            content = Content(
                source='twitter',
                sender_id=sender.id,
                recipient=recipient,
                tip_amount=amount,
                details=content_details,
                post_to_spicefeed=sender.post_to_spicefeed,
                parent=parent,
                recipient_content_id=content_id_json
            )
            content.save()

            # Sender outgoing transaction
            transaction = Transaction(
                user_id=sender.id,
                amount=amount,
                transaction_type='Outgoing'
            )
            transaction.save()

            # Recipient incoming transaction
            transaction = Transaction(
                user=recipient,
                amount=amount,
                transaction_type='Incoming'
            )
            transaction.save()

            if amount > 1:
                amount = '{:,}'.format(round(amount, 8))
            else:
                amount = '{:,.8f}'.format(round(amount, 8))
            amount_str = str(amount)
            if amount_str.endswith('.0'):
                amount_str = amount_str[:-2]
            if '.' in amount_str:
                amount_str = amount_str.rstrip('0')
            if amount_str.endswith('.'):
                amount_str = amount_str[:-1]

            # Post update about the tipping
            args = (amount_str, recipient.twitter_screen_name)
            status = 'I have transferred your tip of %s \U0001f336 SPICE \U0001f336 to %s' % args
            # status += '\n\nMessage me for usage instructions: https://twitter.com/messages/compose?recipient_id='
            status += '\n\nhttps://twitter.com/spicetokens/status/1162246727136497664'
            pof_receiver = self.compute_POF(recipient.id, data['text'])
            pof_sender = self.compute_POF(sender.id, data['text'])
            body = {
                'response': status,
                'in_reply_to_status_id': int(data['id']),
                'auto_populate_reply_metadata': True
            }
            try:                          
                self.api.PostUpdate(
                    body['response'],
                    in_reply_to_status_id=body['in_reply_to_status_id'],
                    auto_populate_reply_metadata=body['auto_populate_reply_metadata']
                )
                success = True                 
            except twitter.error.TwitterError as exc:
                logger.error(repr(exc))            
            response = Response(
                response_type='post',
                content=content,
                body=body,
                botReplied=success
            )
            response.save()

        return success

    def check_failed_reply(self):
        responses = Response.objects.filter(response_type='post')
        responses = responses.filter(botReplied=False)
        for response in responses:
            body = response.body
            self.api.PostUpdate(
                body['response'],
                in_reply_to_status_id=body['in_reply_to_status_id'],
                auto_populate_reply_metadata=body['auto_populate_reply_metadata']
            )
            response.botReplied = True
            response.save()

    def process_mentions(self, last_id=None):
        # Fetch the mentions
        mentions = self.api.GetMentions(
            count=200,
            trim_user=True
        )

        mention_ids = [x.id for x in mentions]

        old_mentions = []
        content_check = Content.objects.filter(
            source='twitter',
            details__reply__id__in=mention_ids
        )
        if content_check.count():
            old_mentions = content_check.values_list('details__reply__id', flat=True)
        fresh_mentions = [x for x in mentions if x.id not in old_mentions]

        for mention in fresh_mentions:
            data = mention.AsDict()
            proceed = True
            if 'in_reply_to_screen_name' in data.keys():
                # if data['in_reply_to_screen_name'] == settings.TWITTER_BOT_NAME:
                #     proceed = False
                if data['user']['id'] == data['in_reply_to_user_id']:
                    proceed = False

            if 'in_reply_to_status_id' in data.keys() and proceed:
                # tipped_status = self.api.GetStatus(data['in_reply_to_status_id'], trim_user=True)
                # tipped = str(tipped_status.AsDict()['user_mentions'])
                # if settings.TWITTER_BOT_NAME in tipped:
                #     message_text = data['text'].replace('@'+settings.TWITTER_BOT_NAME,'',1)
                # else:
                #     message_text=data['text']
                message_text = data['text']
                
                # Get tip amount, defaults to 0 if none
                tip_amount = self.get_tip_amount(message_text)
                if tip_amount > 0:
                    # Identify and save the sender
                    sender, _ = User.objects.get_or_create(twitter_id=data['user']['id_str'])
                    
                    if not sender.twitter_user_details:
                        sender_details = self.api.GetUser(data['user']['id'])
                        sender_details = sender_details.AsDict()
                        del sender_details['status']
                        sender.twitter_user_details = sender_details

                    sender.last_activity = timezone.now()
                    sender.save()

                    # Identify and save the recipient
                    recipient, _ = User.objects.get_or_create(twitter_id=data['in_reply_to_user_id'])
                    if not recipient.twitter_user_details:
                        recipient_details = self.api.GetUser(data['in_reply_to_user_id'])
                        recipient_details = recipient_details.AsDict()
                        del recipient_details['status']
                        recipient.twitter_user_details = recipient_details
                        recipient.save()
                    # Call the function that handles the tipping
                    
                    tipping_succeeded = self.handle_tipping(tip_amount, sender.id, recipient.id, data)
                    if not tipping_succeeded:
                        break 

    def send_direct_message(self, user_id, message, message_id=None):
        proceed = False
        if message_id:
            if not settings.REDISKV.sismember('twitter_msgs', message_id):
                proceed = True
        else:
            proceed = True
        body = {
            'text': message,
            'user_id': user_id,
            'return_json':True,
            'message_id': message_id
        }
        if proceed and not Response.objects.filter(body=body).exists():
            send_success = False
            time.sleep(3)  # Delay the sending by a few seconds        
            try:
                self.api.PostDirectMessage(
                    text=body['text'],
                    user_id=body['user_id'],
                    return_json=body['return_json']
                )
                send_success = True
            except twitter.error.TwitterError as exc:
                logger.error(repr(exc))

            if send_success and message_id:
                settings.REDISKV.sadd('twitter_msgs', message_id)
                if settings.REDISKV.scard('twitter_msgs') >= 10000:
                    settings.REDISKV.spop('twitter_msgs')
            response = Response(
                response_type='direct_message',
                body=body,
                botReplied=send_success
            )
            response.save()
            

    def process_direct_messages(self, last_id=None):        
        success_request = False
        try:
            messages = self.api.GetDirectMessages(count=200, return_json=True)
            success_request = True
        except twitter.error.TwitterError as exc:
            logger.error(repr(exc))
        if success_request:
            for message in messages['events']:
                twitter_bot_id = settings.TWITTER_ACCESS_KEY.split('-')[0]
                sender_id = message['message_create']['sender_id']
                if sender_id != twitter_bot_id:
                    if not settings.REDISKV.sismember('twitter_msgs', message['id']):
                        text = message['message_create']['message_data']['text']
                        text = text.lower().lstrip('/').strip()
                        user_id = message['message_create']['sender_id']
                        user, created = User.objects.get_or_create(twitter_id=user_id)
                        if not user.twitter_user_details:
                            user_details = self.api.GetUser(user_id)
                            user_details = user_details.AsDict()
                            try:
                                del user_details['status']
                            except KeyError:
                                pass
                            user.twitter_user_details = user_details
                            user.save()

                        if user.twitter_screen_name == settings.TWITTER_BOT_NAME:
                            user = None
                        user.last_activity = timezone.now()
                        user.save()                    
                        
                        response = None
                        if text == 'deposit':
                            if user:
                                response = 'Send deposit to this address:\n\n%s' % (user.simple_ledger_address)
                        else:
                            response = get_response(text)

                        show_generic_response = True
                        if response:
                            self.send_direct_message(user_id, response, message['id'])
                            show_generic_response = False
                        else:
                            

                            if text == 'balance' and user:
                                amount = compute_balance(user.id)
                                amount = '{:,}'.format(round(amount, 8))
                                amount_str = str(amount)
                                if amount_str.endswith('.0'):
                                    amount_str = amount_str[:-2]
                                if 'e' in amount_str:
                                    amount_str = "{:,.8f}".format(float(amount_str))
                                response = 'You have %s \U0001f336 SPICE \U0001f336!' % amount_str
                                self.send_direct_message(user_id, response, message['id'])
                                show_generic_response = False
                                # Update last activity
                                user.last_activity = timezone.now()
                                user.save()

                            if text.startswith('withdraw ') and user:
                                amount = None
                                addr = None
                                withdraw_error = ''
                                response = None
                                try:
                                    amount_temp = text.split()[1]
                                    try:
                                        amount = float(amount_temp.replace(',', '').strip())
                                    except ValueError:
                                        response = "You have entered an invalid amount!"
                                    addr_temp = text.split()[2].strip()
                                    if  addr_temp.startswith('simpleledger') and len(addr_temp) == 55:
                                        addr = addr_temp.strip()
                                        response = "You have entered an invalid SLP address!"
                                except IndexError:
                                    response = "You have not entered a valid amount or SLP address!"

                                if addr and amount:
                                    balance = compute_balance(user.id)
                                    if amount <= balance:
                                        # Limit withdrawals to 1 withdrawal per hour per user
                                        withdraw_limit = False
                                        latest_withdrawal = None
                                        try:
                                            latest_withdrawal = Withdrawal.objects.filter(
                                                user=user
                                            ).latest('date_created')
                                        except Withdrawal.DoesNotExist:
                                            pass
                                        if latest_withdrawal:
                                            last_withdraw_time = latest_withdrawal.date_created
                                            time_now = timezone.now()
                                            tdiff = time_now - last_withdraw_time
                                            withdraw_time_limit = tdiff.total_seconds()
                                            if withdraw_time_limit < 3600:
                                                withdraw_limit = True
                                                response = 'You have reached your hourly withdrawal limit!'

                                        if not withdraw_limit:
                                            if amount >= 1000:
                                                withdrawal = Withdrawal(
                                                    user=user,
                                                    address=addr,
                                                    amount=amount
                                                )
                                                withdrawal.save()
                                                current_app.send_task(
                                                    'main.tasks.withdraw_spice_tokens',
                                                    args=(withdrawal.id,),
                                                    kwargs={
                                                        'user_id': user_id,
                                                        'bot': 'twitter'
                                                    },
                                                    queue='twitter'
                                                )
                                                response = 'Your \U0001f336 SPICE \U0001f336 withdrawal request is being processed.'
                                            else:
                                                # response = "Only 1000 \U0001f336 and above is allowed to withdraw."
                                                response = "We can’t process your withdrawal request because it is below minimum. The minimum amount allowed is 1000 \U0001f336 SPICE."

                                    else:
                                        response = "You don't have enough \U0001f336 SPICE \U0001f336 to withdraw!"
                                
                                if not addr or not amount:
                                    response = """
                                    Withdrawal can be done by running the following command:
                                    \n/withdraw "amount" "simpleledger_address"
                                    \n\nExample:
                                    \n/withdraw 10 simpleledger:qpgje2ycwhh2rn8v0rg5r7d8lgw2pp84zgpkd6wyer
                                    """
                                if response:
                                    self.send_direct_message(user_id, response, message['id'])
                                    show_generic_response = False

                                if text.startswith('withdraw ') and user:
                                    amount = None
                                    addr = None
                                    withdraw_error = ''
                                    response = None
                                    try:
                                        amount_temp = text.split()[1]
                                        try:
                                            amount = float(amount_temp.replace(',', '').strip())
                                        except ValueError:
                                            response = "You have entered an invalid amount!"
                                        addr_temp = text.split()[2].strip()
                                        if  addr_temp.startswith('simpleledger') and len(addr_temp) == 55:
                                            addr = addr_temp.strip()
                                            response = "You have entered an invalid SLP address!"
                                    except IndexError:
                                        response = "You have not entered a valid amount or SLP address!"

                                    if addr and amount:
                                        balance = compute_balance(user.id)
                                        if amount <= balance:
                                            # Limit withdrawals to 1 withdrawal per hour per user
                                            withdraw_limit = False
                                            latest_withdrawal = None
                                            try:
                                                latest_withdrawal = Withdrawal.objects.filter(
                                                    user=user
                                                ).latest('date_created')
                                            except Withdrawal.DoesNotExist:
                                                pass
                                            if latest_withdrawal:
                                                last_withdraw_time = latest_withdrawal.date_created
                                                time_now = timezone.now()
                                                tdiff = time_now - last_withdraw_time
                                                withdraw_time_limit = tdiff.total_seconds()
                                                if withdraw_time_limit < 3600:
                                                    withdraw_limit = True
                                                    response = 'You have reached your hourly withdrawal limit!'

                                            if not withdraw_limit:
                                                withdrawal = Withdrawal(
                                                    user=user,
                                                    address=addr,
                                                    amount=amount
                                                )
                                                withdrawal.save()
                                                current_app.send_task(
                                                    'main.tasks.withdraw_spice_tokens',
                                                    args=(withdrawal.id,),
                                                    kwargs={
                                                        'user_id': user_id,
                                                        'bot': 'twitter'
                                                    },
                                                    queue='twitter'
                                                )
                                                response = 'Your \U0001f336 SPICE \U0001f336 withdrawal request is being processed.'
                                        else:
                                            response = "You don't have enough \U0001f336 SPICE \U0001f336 to withdraw!"
                                    
                                    if not addr or not amount:
                                        response = """
                                        Withdrawal can be done by running the following command:
                                        \n/withdraw "amount" "simpleledger_address"
                                        \n\nExample:
                                        \n/withdraw 10 simpleledger:qpgje2ycwhh2rn8v0rg5r7d8lgw2pp84zgpkd6wyer
                                        """
                                    if response:
                                        self.send_direct_message(user_id, response, message['id'])
                                        show_generic_response = False

                        if show_generic_response:
                            # Send the message
                            response = """ To learn more about SpiceBot, please visit:
                            \nhttps://spicetoken.org/bot_faq/
                            \nIf you need further assistance, please contact @spicedevs"""
                            self.send_direct_message(user_id, response, message['id'])
