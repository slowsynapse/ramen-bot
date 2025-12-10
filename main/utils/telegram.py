import emoji
import requests
import logging
import random
import json
import redis
import os
import re
from datetime import datetime
from django.utils import timezone
from django.conf import settings
from django.db.models import Sum

from main.models import User, Content, Transaction, Withdrawal, TelegramGroup, TelegramMessage
from main.tasks import send_telegram_message
from .responses import get_response
from .account import compute_balance
from django.db import IntegrityError


logger = logging.getLogger(__name__)


def get_chat_admins(chat_id):
    data = {
        "chat_id": chat_id
    }
    url = 'https://api.telegram.org/bot'
    response = requests.post(
        f"{url}{settings.TELEGRAM_BOT_TOKEN}/getChatAdministrators", data=data
    )
    admins = []
    if response.status_code == 200:
        admins = [x['user']['id'] for x in response.json()['result']]
    return admins


def get_chat_members_count(chat_id):
    data = {
        "chat_id": chat_id
    }
    url = 'https://api.telegram.org/bot'
    response = requests.post(
        f"{url}{settings.TELEGRAM_BOT_TOKEN}/getChatMembersCount", data=data
    )
    count = 0
    if response.status_code == 200:
        count = response.json()['result']
    return count

class TelegramBotHandler(object):

    def __init__(self, data):
        self.data = data
        self.update_id = None
        self.message = None
        self.dest_id = None
        self.tip = False
        self.tip_with_emoji = False
        self.reply_to_message_id = None  # For reaction tips to reply to original message


    @staticmethod
    def get_name(details):
        name = details['first_name']
        try:
            name += ' ' + details['last_name']
        except KeyError:
            pass
        if len(name) > 20:
            name = name[0:20]
        return name

    
    def compute_amount(self, text):
        amount = 0
        if text:
            # Check if text only contains the allowed symbol and emoji
            for i in settings.ALLOWED_SYMBOLS.keys():
                if i == "\U0001F344":
                    for x in range(text.count(i)):
                        amount += random.choice(range(0,1000))                        
                else:
                    amount +=  settings.ALLOWED_SYMBOLS[i] * text.count(i)
        return amount

    def validate_address(self, text):
        is_valid = False
        if len(text) == 55 and text.startswith('simpleledger:'):
            is_valid = True
        return is_valid

    def compute_POF(self, user, text):        
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
        

    def handle_tipping(self, message, text, with_pof=False):
        sender_telegram_id = message['from']['id']
        sender, _ = User.objects.get_or_create(
            telegram_id=sender_telegram_id
        )
        group = TelegramGroup.objects.get(chat_id=message["chat"]["id"])
        # Udpate user details, in case of changes
        sender.telegram_user_details = message['from']
        sender.save()
        from_username = sender.telegram_display_name or sender.telegram_username
        to_username = None
        to_firstname = None

        recipient = None
        recipient_content_id = None
        content_id_json = None
        parent = None
        try:
            if not message['reply_to_message']['from']['is_bot']:
                self.recipient_telegram_id = message['reply_to_message']['from']['id']
                recipient, _ = User.objects.get_or_create(
                    telegram_id=self.recipient_telegram_id,
                    telegram_user_details__is_bot=False
                )
                # Udpate user details, in case of changes
                recipient.telegram_user_details = message['reply_to_message']['from']                
                recipient.save()                
                to_username = recipient.telegram_display_name or recipient.telegram_username
                group.users.add(recipient)
                group.save()
            to_firstname = message['reply_to_message']['from']['username']               
        except KeyError:
            pass
        
        recipient_content_id = {
            'chat_id': message['chat']['id'],
            'message_id': message['reply_to_message']['message_id']
        }

        content_id_json = json.dumps(recipient_content_id)

        #Getting parent tipper
        if Content.objects.filter(recipient_content_id=content_id_json).exists():
            content = Content.objects.filter(parent=None, recipient_content_id=content_id_json).first()
            parent = content
        
        self.sender = sender
        self.recipient = recipient

        self.parent = parent
        self.recipient_content_id = content_id_json
        try:
            self.tip_amount = 0
            # Check if to_username is not equal to None         
            if  to_username and to_firstname != settings.TELEGRAM_BOT_USER and from_username != to_username:                
                if text.startswith('tip'):

                    if not self.has_emoji(text):
                        amount = text.split()[1].replace(',', '')
                        if 'e' in amount:
                            self.tip_amount = 0
                        else:
                            self.tip_amount = float(amount)

                    
                    amount = text.split()[1].replace(',', '')
                    if 'e' in amount:
                        self.tip_amount = 0
                    else:
                        self.tip_amount = float(amount)


                elif ' ramen' in text:
                    amount = text.split(' ramen')[0].split()[-1].replace(',', '')
                    self.tip_amount = float(amount)


                # Added plus symbol, hot pepper, thumbs up & fire emoji for tipping
                else:

                    if self.emoji_only(text):
                        for i in settings.ALLOWED_SYMBOLS.keys():
                            if str(i) in text:
                                self.tip_amount = self.compute_amount(text)

                    
                    for i in settings.ALLOWED_SYMBOLS.keys():
                        if str(i) in text:
                            self.tip_amount = self.compute_amount(text)


                one_satoshi = 0.00000001
                if self.tip_amount >= one_satoshi:
                    # Check if user has enough balance to give a tip
                    balance = compute_balance(sender.id)
                    if balance >= self.tip_amount:
                        if self.tip_amount > 0:
                            if self.tip_amount > 1:
                                amount = '{:,}'.format(round(self.tip_amount, 8))
                            else:
                                amount = '{:,.8f}'.format(round(self.tip_amount, 8))
                            amount_str = str(amount)
                            if amount_str.endswith('.0'):
                                amount_str = amount_str[:-2]
                            if '.' in amount_str:
                                amount_str = amount_str.rstrip('0')
                            if amount_str.endswith('.'):
                                amount_str = amount_str[:-1]
                            if 'e' in amount_str:
                                amount_str = "{:,.8f}".format(float(amount_str))

                            self.message = f"<b>{from_username}</b> tipped {amount_str} \U0001F35C RAMEN \U0001F35C to <b>{to_username}</b>"

                            #get pof
                            pct_sender, pof_sender = self.compute_POF(sender, text)
                            pct_receiver, pof_receiver = self.compute_POF(recipient,text)

                            #set of replies
                            if text.count(' pof %') or text.count('pof % '):
                                self.message = f"<b>{from_username}</b> (PoF <b>{pct_sender}</b>% {settings.POF_SYMBOLS[pof_sender]}) tipped {amount_str} \U0001F35C RAMEN \U0001F35C to <b>{to_username}</b> (PoF <b>{pct_receiver}</b>% {settings.POF_SYMBOLS[pof_receiver]})"
                            elif text.count(' pof') or text.count('pof '):
                                self.message = f"<b>{from_username}</b> (PoF <b>{pof_sender}/5 {settings.POF_SYMBOLS[pof_sender]}</b>) tipped {amount_str} \U0001F35C RAMEN \U0001F35C to <b>{to_username}</b> (PoF <b>{pof_receiver}/5 {settings.POF_SYMBOLS[pof_receiver]}</b>)"
                            else:
                                self.message = f"<b>{from_username}</b> tipped {amount_str} \U0001F35C RAMEN \U0001F35C to <b>{to_username}</b>"
                    else:
                        logger.info('Insufficient balance')
                        # if not self.tip_with_emoji:
                        self.message = f"<b>@{from_username}</b>, you don't have enough \U0001F35C RAMEN \U0001F35C!"
                        self.tip = False
                else:
                    self.tip = False
            # Prevent users from sending tips to bot
            elif to_firstname == settings.TELEGRAM_BOT_USER:
                if message['chat']['type']  == 'private':
                    self.message = f"""To tip someone RAMEN points reply to any of their messages with:
                                    \ntip [amount] \nExample: tip 200
                                    \nOR
                                    \n[amount] ramen \nExample: 100 ramen"""
                self.tip = False
        except ValueError:            
            pass

    def emoji_only(self, text):
        has_emoji = False
        has_others = False

        for char in text:
            if emoji.is_emoji(char) or char == "+":
                has_emoji = True
            elif not emoji.is_emoji(char) and char != " ":
                has_others = True

        if has_emoji and not has_others:
            return True
        return False

    def has_emoji(self, text):
        for char in text:
            if emoji.is_emoji(char) or char == "+":
               return True
        return False

    def _store_message_author(self, t_message, user):
        """
        Store message author for reaction-based tipping lookup.
        This is isolated and only runs when REACTION_TIPPING_ENABLED is True.
        """
        if not getattr(settings, 'REACTION_TIPPING_ENABLED', False):
            return

        try:
            chat_id = t_message["chat"]["id"]
            message_id = t_message["message_id"]

            TelegramMessage.objects.get_or_create(
                chat_id=chat_id,
                message_id=message_id,
                defaults={'author': user}
            )
        except Exception as e:
            # Don't let message tracking errors affect normal bot operation
            logger.warning(f"Failed to store message author: {e}")

    def process_reaction(self):
        """
        Handle native Telegram emoji reactions for tipping.
        This method is completely isolated from process_data() for easy removal.
        """
        if not getattr(settings, 'REACTION_TIPPING_ENABLED', False):
            return

        reaction_data = self.data.get('message_reaction', {})
        if not reaction_data:
            return

        try:
            chat = reaction_data.get('chat', {})
            chat_id = chat.get('id')
            message_id = reaction_data.get('message_id')
            reactor_info = reaction_data.get('user', {})
            reactor_id = reactor_info.get('id')
            new_reactions = reaction_data.get('new_reaction', [])
            old_reactions = reaction_data.get('old_reaction', [])

            if not all([chat_id, message_id, reactor_id]):
                return

            # Only process if new reactions were added (not just removed)
            # Compare by converting to sets of emoji strings
            old_emoji_set = {r.get('emoji') for r in old_reactions if r.get('type') == 'emoji'}
            new_emoji_set = {r.get('emoji') for r in new_reactions if r.get('type') == 'emoji'}
            added_emoji = new_emoji_set - old_emoji_set

            if not added_emoji:
                return

            # Look up message author from our stored records
            try:
                msg_record = TelegramMessage.objects.get(
                    chat_id=chat_id,
                    message_id=message_id
                )
                recipient = msg_record.author
            except TelegramMessage.DoesNotExist:
                logger.debug(f"No stored author for message {message_id} in chat {chat_id}")
                return

            # Get reactor (sender of the tip)
            sender, _ = User.objects.get_or_create(telegram_id=reactor_id)
            sender.telegram_user_details = reactor_info
            sender.last_activity = timezone.now()
            sender.save()

            # Prevent self-tipping
            if sender.id == recipient.id:
                return

            # Prevent tipping bots
            if recipient.telegram_user_details.get('is_bot', False):
                return

            # Calculate tip amount from added reaction emoji
            reaction_symbols = getattr(settings, 'REACTION_SYMBOLS', {})
            tip_amount = 0
            for emoji_char in added_emoji:
                if emoji_char in reaction_symbols:
                    tip_amount += reaction_symbols[emoji_char]

            if tip_amount <= 0:
                return

            # Check sender balance
            balance = compute_balance(sender.id)
            if balance < tip_amount:
                logger.info(f"Reaction tip failed: insufficient balance for user {sender.id}")
                return

            # Process the tip
            self.sender = sender
            self.recipient = recipient
            self.tip_amount = tip_amount
            self.tip = True
            self.dest_id = chat_id

            # Get display names
            from_username = sender.telegram_display_name or sender.telegram_username or str(sender.telegram_id)
            to_username = recipient.telegram_display_name or recipient.telegram_username or str(recipient.telegram_id)

            # Format amount string
            if tip_amount > 1:
                amount_str = '{:,}'.format(round(tip_amount, 8))
            else:
                amount_str = '{:,.8f}'.format(round(tip_amount, 8))
            if amount_str.endswith('.0'):
                amount_str = amount_str[:-2]
            if '.' in amount_str:
                amount_str = amount_str.rstrip('0')
            if amount_str.endswith('.'):
                amount_str = amount_str[:-1]

            # Build reaction emoji string for the message
            reaction_emoji_str = ''.join(added_emoji)

            self.message = f"{reaction_emoji_str} <b>{from_username}</b> reacted and tipped {amount_str} \U0001F35C RAMEN \U0001F35C to <b>{to_username}</b>"

            # Store recipient content id for tracking
            self.recipient_content_id = json.dumps({
                'chat_id': chat_id,
                'message_id': message_id
            })
            self.parent = None

            # Store message_id to reply to the original message
            self.reply_to_message_id = message_id

            logger.info(f"Reaction tip: {sender.id} -> {recipient.id}, amount: {tip_amount}")

        except Exception as e:
            logger.error(f"Error processing reaction: {e}")
            return

    def process_data(self):
        text = ''
        amount = None
        addr = None
        t_message = {}
        entities = []
        if 'message' in self.data.keys():
            self.update_id = self.data['update_id']
            t_message = self.data["message"]            
            self.dest_id = t_message["chat"]["id"]
            chat_type = t_message['chat']['type'] 
            from_id = t_message['from']['id']
            try:
                text = t_message['text']
            except KeyError:
                pass
            # Record user last activity
            user, _ = User.objects.get_or_create(
                telegram_id=from_id
            )
            user.last_activity = timezone.now()
            user.save()
            # Create chat/group if doesn't exist yet
            if chat_type != 'private':
                try:
                    group = TelegramGroup.objects.get(chat_id=t_message["chat"]["id"])
                    group.users.add(user)
                    group.save()
                except IntegrityError as exc:                    
                    groups = TelegramGroup.objects.filter(chat_id=t_message["chat"]["id"])
                    group_id = groups.first().id
                    group = TelegramGroup.objects.get(id=group_id)
                    group.users.add(user)
                    group.save()
                    if groups.count > 1:                        
                        TelegramGroup.objects.exclude(id=group_id).delete()                        
                    else:
                        raise IntegrityError(exc)
                except TelegramGroup.DoesNotExist:
                    group, created = TelegramGroup.objects.get_or_create(
                        chat_id=t_message["chat"]["id"]
                    )
                    if created:
                        group.title = t_message["chat"]["title"]
                        group.chat_type = t_message["chat"]["type"]
                        group.save()
                        
                    else:
                        TelegramGroup.objects.filter(id=group.id).update(
                            title=t_message["chat"]["title"],
                            chat_type = t_message["chat"]["type"]
                        )
                    group.users.add(user)
                    group.save()

                # Store message author for reaction-based tipping (isolated feature)
                self._store_message_author(t_message, user)

            if not settings.REDISKV.sismember('telegram_msgs', self.update_id):
                try:
                    if text == '@' + settings.TELEGRAM_BOT_USER:
                        # telegram_bot_id = settings.TELEGRAM_BOT_TOKEN.split(':')[0]
                        # bot_url = 'tg://user?id=' + telegram_bot_id
                        bot_url = 'https://t.me/' + settings.TELEGRAM_BOT_USER
                        messages = array = [
                            'Sup, if you want to learn how to push my buttons <a href="%s">DM me</a> homie.' % bot_url,
                            'I can show you how to play with my doodads, but you have to <a href="%s">private message</a> me first.' % bot_url,
                            'Yo! I heard you wanted to see me. Well here I am homeslice. \n\n<a href="%s">DM Me</a>, Let\'s talk.' % bot_url,
                            'What\'s up? <a href="%s">Message Me</a>. Let\'s talk.' % bot_url,
                            'We frens. <a href="%s">Message Me</a> so the normies aren\'t all up in our business.' % bot_url,
                            'You Rang? <a href="%s">Message me</a> to learn the fun things we can do together!' % bot_url
                        ]
                        self.message = random.choice(messages)

                except KeyError:
                    pass

        #rain feature here
        msg =''
        if text and chat_type != 'private':
            group = TelegramGroup.objects.get(chat_id=t_message["chat"]["id"])
            sender_telegram_id = t_message['from']['id']
            sender, _ = User.objects.get_or_create(
                telegram_id=sender_telegram_id
            )
            # Udpate user details, in case of changes
            sender.telegram_user_details = t_message['from']
            sender.save()

            balance = compute_balance(sender.id)
            msg = sender.rain(text, group.id, balance)

        if msg != '':
            send_telegram_message.delay(msg, self.dest_id, self.update_id)

        if text and msg == '':

            try:
                entities = t_message['entities']
                for entity in entities:
                    if entity['type'] == 'mention':
                        if entity['offset'] == 0:
                            mention = text[:entity['length']]
                            text = text.replace(mention, '').strip()
                            break
                    elif entity['type'] == 'bot_command':
                        if text.startswith('/'):
                            bot_user = '@' + settings.TELEGRAM_BOT_USER
                            text = text.replace(bot_user, '').strip()
            except KeyError:
                pass
            text = text.lower().lstrip('/').strip()
            user, _ = User.objects.get_or_create(
                telegram_id=t_message['from']['id']
            )
            # Update user details
            user.telegram_user_details = t_message['from']
            user.save()

            if text == 'greet':
                user = self.get_name(t_message['from'])
                msg = f"Hello {user}!"
                self.message = msg
            
            elif text == 'rain' and chat_type == 'private':
                self.message = get_response('rain')


            elif text == 'deposit' and chat_type == 'private':
                message1 = 'Send RAMEN token deposits to this address:'
                message2 = '%s' % (user.bitcoincash_address)
                send_telegram_message.delay(message1, self.dest_id, self.update_id)
                send_telegram_message.delay(message2, self.dest_id, self.update_id)
            # Check balance using "/balance" or "/balance@..."    
            elif text == 'balance' or text.startswith('balance@', 0):
                if chat_type == 'private':
                    balance = compute_balance(user.id)
                    balance = '{:,}'.format(round(balance, 8))
                    
                    balance_str = str(balance)
                    if 'e' in balance_str:
                        balance_str = "{:,.8f}".format(float(balance_str))
                    if balance_str.endswith('.0'):
                        balance_str = balance_str[:-2]
                    user_name = self.get_name(t_message['from'])
                    self.message = f"<b>@{user_name}</b>, you have {balance_str} \U0001F35C RAMEN \U0001F35C!"
                    # Update last activity
                    user.last_activity = timezone.now()
                    user.save()          
                
            elif text.strip() == 'withdraw' and chat_type == 'private':
                self.message = get_response('withdraw')
                
            elif text.startswith('withdraw ') and chat_type == 'private':
                amount = None
                addr = None
                withdraw_error = ''
                invalid_message = "You have not entered a valid amount or BCH address!"
                try:
                    amount_temp = text.split()[1]
                    try:
                        amount = amount_temp.replace(',', '').strip()
                        amount = amount.replace("'", '').replace('"', '')
                        if 'e' in amount:
                            amount = None
                            self.message = invalid_message
                        else:
                            amount = float(amount)
                    except ValueError:
                        self.message = "You have entered an invalid amount!"
                    addr_temp = text.split()[2].strip()
                    if  addr_temp.startswith('bitcoincash') and len(addr_temp) == 54:
                        addr = addr_temp.strip()
                        self.message = "You have entered an invalid BCH address!"
                except IndexError:
                    self.message = invalid_message
                
                if addr and amount:
                    if isinstance(amount, str):
                        amount = amount.replace("'", '').replace('"', '')
                    balance = compute_balance(user.id)
                    try:
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
                                time_now = datetime.now(timezone.utc)
                                tdiff = time_now - last_withdraw_time
                                withdraw_time_limit = tdiff.total_seconds()
                                if withdraw_time_limit < 3600:
                                    withdraw_limit = True
                                    username = self.get_name(t_message['from'])
                                    self.message = f"<b>@{username}</b>, you have reached your hourly withdrawal limit!"

                            if not withdraw_limit:
                                if amount >= 1000:
                                    # TODO: Re-implement withdrawal for RAMEN
                                    # For now, withdrawals are disabled
                                    self.message = "Withdrawals are temporarily disabled."
                                else:
                                    self.message = f"We can't process your withdrawal request because it is below minimum. The minimum amount allowed is 1000 \U0001F35C RAMEN."
                        else:
                            username = self.get_name(t_message['from'])
                            self.message = f"<b>@{username}</b>, you don't have enough \U0001F35C RAMEN \U0001F35C to withdraw!"
                    except TypeError:
                        amount = None
                if not addr or not amount:
                    self.message = """Withdrawing converts your RAMEN Points to RAMEN Tokens (CashTokens).
                    \n\nWithdrawals are currently disabled. When enabled, you will be able to withdraw using:
                    \n/withdraw "amount" "cashtoken_address"
                    """

            elif text.startswith('tip '):
                self.tip = True

            elif ' ramen' in text or ' ramens' in text:
                pattern1 = re.compile(r'^\d+\s+ramen(\s+pof)?(\s+%)?\s*$')
                pattern2 = re.compile(r'^\d+\s+ramens\s*\w*\d*\D*$')
                if pattern1.match(text) or pattern2.match(text):
                    self.tip = True
                
            elif text == 'ramenfeedon':
                admins = get_chat_admins(t_message["chat"]["id"])
                if from_id in admins:
                    group = TelegramGroup.objects.get(chat_id=t_message["chat"]["id"])
                    group.post_to_spicefeed = True
                    user = User.objects.get(telegram_id=t_message['from']['id'])
                    group.privacy_set_by = user
                    group.last_privacy_setting = timezone.now()
                    group.save()
                    self.message = 'RamenFeed enabled'

            elif text == 'ramenfeedoff':
                admins = get_chat_admins(t_message["chat"]["id"])
                if from_id in admins:
                    group = TelegramGroup.objects.get(chat_id=t_message["chat"]["id"])
                    group.post_to_spicefeed = False
                    user = User.objects.get(telegram_id=t_message['from']['id'])
                    group.privacy_set_by = user
                    group.last_privacy_setting = timezone.now()
                    group.save()
                    self.message = 'RamenFeed disabled'

            elif text == 'ramenfeedstatus':
                group = TelegramGroup.objects.get(chat_id=t_message["chat"]["id"])
                if group.post_to_spicefeed:
                    self.message = 'RamenFeed is enabled'
                else:
                    self.message = 'RamenFeed is disabled'
            
            else:
                if chat_type == 'private':

                    if 'tip' != text:
                        self.message = """What can I help you with? Here are a list of my commands:
                            \nType:
                            \ndeposit - for information on depositing \ntip - for information on tipping RAMEN points \nwithdraw - for information on withdrawing RAMEN \nbalance - for information on your RAMEN points balance
                            \n\nTo learn more about RamenBot, please visit:
                            \nhttps://t.me/IAMBCH_BOT
                        """

                    if 'tip' in text:
                        self.message = """
                            To tip someone RAMEN Points, simply **reply** to any of their messages with:
                            \ntip [amount]
                            \n**Example:** tip 200
                            \nOR
                            \n[amount] ramen
                            \n**Example:** 100 ramen
                        """
                    else:
                        self.message = """What can I help you with? Here are a list of my commands:
                            \nType:
                            \ndeposit - for information on depositing \ntip - for information on tipping RAMEN points \nrain - for information on raining RAMEN on others \nwithdraw - for information on withdrawing RAMEN \nbalance - for information on your RAMEN points balance
                            \n\nTo learn more about RamenBot, please visit:
                            \nhttps://t.me/IAMBCH_BOT
                        """
                else:
                    # Added plus symbol, hot pepper, thumbs up & fire emoji for tipping
                    for i in settings.ALLOWED_SYMBOLS.keys():
                        if str(i) in text:
                            self.tip = True
                            self.tip_with_emoji = True
                            break

            if self.tip:
                if 'reply_to_message' in t_message.keys():
                    with_pof = text.strip().lower().endswith('pof')
                    self.handle_tipping(t_message, text, with_pof=with_pof)
                


        info = {
            'text': text,
            'entities': entities,
            'message': self.message,
            'data_keys': list(self.data.keys())
        }
        logger.info(str(info))
        return info
        
    def respond(self):
        if self.message and self.dest_id:

            if self.tip and self.recipient:

                group = TelegramGroup.objects.get(chat_id=self.dest_id)

                content = Content(
                    tip_amount=self.tip_amount,
                    sender=self.sender,
                    recipient=self.recipient,
                    details=self.data,
                    post_to_spicefeed=group.post_to_spicefeed,
                    parent=self.parent,
                    recipient_content_id=self.recipient_content_id
                )
                content.save()

                # Sender outgoing transaction
                transaction = Transaction(
                    user = self.sender,
                    amount = self.tip_amount,
                    transaction_type = 'Outgoing'
                )
                transaction.save()

                # Recipient incoming transaction
                transaction = Transaction(
                    user = self.recipient,
                    amount = self.tip_amount,
                    transaction_type = 'Incoming'
                )
                transaction.save()
            send_telegram_message.delay(
                self.message,
                self.dest_id,
                self.update_id,
                self.reply_to_message_id  # Reply to original message for reaction tips
            )
        else:
            logger.info(f"No response")
