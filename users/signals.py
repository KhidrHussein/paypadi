from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.conf import settings

from .models import User, UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Signal to create a user profile when a new user is created.
    """
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    """
    Signal to save the user profile when the user is saved.
    """
    try:
        instance.profile.save()
    except UserProfile.DoesNotExist:
        # In case the profile was not created by the create_user_profile signal
        UserProfile.objects.create(user=instance)


@receiver(pre_save, sender=settings.AUTH_USER_MODEL)
def update_user_referral(sender, instance, **kwargs):
    """
    Signal to handle user referral logic before saving the user.
    """
    if not instance.pk:  # Only for new users
        if instance.referred_by:
            # Add any referral logic here, e.g., bonus points
            pass
