from django.db.models.signals import post_save
from django.db.models import Sum
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone

from .models import User, Transaction, Deposit, Content


@receiver(post_save, sender=User)
def user_post_save(sender, instance=None, created=False, **kwargs):
    """Generate BCH address for new users."""
    if created and not instance.bitcoincash_address:
        from main.utils.wallets import generate_bch_address
        instance.bitcoincash_address = generate_bch_address(instance.id)
        instance.save(update_fields=['bitcoincash_address'])


@receiver(post_save, sender=Deposit)
def deposit_post_save(sender, instance=None, created=False, **kwargs):
    """Create a transaction record when a deposit is made."""
    if created:
        transaction = Transaction(
            user=instance.user,
            amount=instance.amount,
            transaction_type='Incoming'
        )
        transaction.save()


@receiver(post_save, sender=Content)
def content_post_save(sender, instance=None, created=False, **kwargs):
    """Update tip totals when content is created."""
    if created:
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
