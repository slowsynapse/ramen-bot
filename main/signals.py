from django.db.models.signals import post_save
from django.db.models import Sum
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone
import requests
from main.tasks import download_upload_file
from .models import User, Transaction, Deposit, Content, Media, User
from .utils.wallets import generate_cash_address
from subprocess import Popen, PIPE


def create_addresses(user):
    bitcoincash_address = generate_cash_address(user.id)
    cmd = 'node /code/spiceslp/address-conversion.js {0}'.format(bitcoincash_address)
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE) 
    stdout, _ = p.communicate()
    result = stdout.decode('utf8')
    simple_ledger_address = str(result).split('\n')[0]
    user.bitcoincash_address = bitcoincash_address
    user.simple_ledger_address = simple_ledger_address
    user.save()


@receiver(post_save, sender=User)
def user_post_save(sender, instance=None, created=False, **kwargs):
    if created and not instance.simple_ledger_address:
        create_addresses(instance)


@receiver(post_save, sender=Deposit)
def deposit_post_save(sender, instance=None, created=False, **kwargs):
    if created:
        transaction = Transaction(
            user=instance.user,
            amount=instance.amount, 
            transaction_type='Incoming'
        )
        transaction.save()


@receiver(post_save, sender=Content)
def content_post_save(sender, instance=None, created=False, **kwargs):
    if created:
        data = instance.details
        if instance.source == 'telegram':
            
            if 'photo' in data['message']['reply_to_message'].keys():
                file_type = 'photo'
                file_id = data['message']['reply_to_message']['photo'][-1]['file_id']
                download_upload_file.delay(file_id, file_type, instance.id)

            elif 'sticker' in data['message']['reply_to_message'].keys():
                file_type = 'sticker'
                file_id = data['message']['reply_to_message']['sticker']['file_id']
                download_upload_file.delay(file_id, file_type, instance.id)

            elif 'animation' in data['message']['reply_to_message'].keys():
                file_type = 'animation'
                file_id = data['message']['reply_to_message']['animation']['file_id']
                download_upload_file.delay(file_id, file_type, instance.id)

            elif 'video' in data['message']['reply_to_message'].keys():
                file_type = 'animation'
                file_id = data['message']['reply_to_message']['video']['file_id']
                download_upload_file.delay(file_id, file_type, instance.id)

            elif 'video_note' in data['message']['reply_to_message'].keys():
                file_type = 'animation'
                file_id = data['message']['reply_to_message']['video_note']['file_id']
                download_upload_file.delay(file_id, file_type, instance.id)
            
            elif 'voice' in data['message']['reply_to_message'].keys():
                file_type = 'audio'
                file_id = data['message']['reply_to_message']['voice']['file_id']
                download_upload_file.delay(file_id, file_type, instance.id)

            elif 'document' in data['message']['reply_to_message'].keys():
                file_type = data['message']['reply_to_message']['document']['mime_type']
                if 'image' in file_type:
                    file_type = 'photo'
                file_id = data['message']['reply_to_message']['document']['file_id']
                download_upload_file.delay(file_id, file_type, instance.id)

        # Initially equate tip amount and total_tips
        instance.total_tips = instance.tip_amount
        instance.save()

        if instance.parent:
            # Update parent's total_tips and last activity
            total_tips = instance.parent.tip_amount
            children_tips = instance.parent.children.all().aggregate(Sum('tip_amount'))['tip_amount__sum'] or 0
            total_tips += children_tips
            instance.parent.total_tips = total_tips
            instance.parent.last_activity = timezone.now()
            instance.parent.save()
