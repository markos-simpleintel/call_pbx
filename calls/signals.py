from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User
from .utils import scan_user_folder

@receiver(post_save, sender=User)
def scan_user_recordings(sender, instance, created, **kwargs):
    if created:
        # 1. Update existing calls in DB that were previously unassociated
        Call.objects.filter(caller_id=instance.phone_number, user__isnull=True).update(user=instance)
        
        # 2. Trigger disk scan for any files not yet in DB
        scan_user_folder(instance.phone_number)
