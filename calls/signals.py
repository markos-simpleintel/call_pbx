from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User
from .utils import scan_user_folder

@receiver(post_save, sender=User)
def scan_user_recordings(sender, instance, created, **kwargs):
    if created:
        # Trigger scan for the new user's phone number
        scan_user_folder(instance.phone_number)
