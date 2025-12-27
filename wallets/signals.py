from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Wallet

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_wallet(sender, instance, created, **kwargs):
    """
    Signal to create a wallet when a new user is created.
    """
    if created:
        Wallet.objects.get_or_create(user=instance)

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_wallet(sender, instance, **kwargs):
    """
    Signal to save the wallet when the user is saved.
    """
    try:
        instance.wallet.save()
    except Wallet.DoesNotExist:
        Wallet.objects.create(user=instance)
