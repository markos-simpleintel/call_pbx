from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    phone_number = models.CharField(max_length=15, unique=True)
    is_verified = models.BooleanField(default=False)

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.phone_number

class Call(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='calls', null=True, blank=True)
    caller_id = models.CharField(max_length=20)
    session_id = models.CharField(max_length=100, unique=True)
    wav_filename = models.CharField(max_length=255)
    txt_filename = models.CharField(max_length=255, blank=True)
    wav_size = models.BigIntegerField(default=0)
    txt_size = models.BigIntegerField(default=0)
    created_at = models.DateTimeField()
    transfer_reasons = models.TextField(blank=True, null=True)
    transfer_reason_descriptions = models.TextField(blank=True, null=True)
    last_updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.caller_id} - {self.session_id}"
