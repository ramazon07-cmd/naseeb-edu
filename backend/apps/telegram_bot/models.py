from django.conf import settings
from django.db import models

DEFAULT_PREFS = {'essays': True, 'streak': True, 'application': True}


class TelegramLink(models.Model):
    class Language(models.TextChoices):
        UZ = 'uz', 'Uzbek'
        RU = 'ru', 'Russian'
        EN = 'en', 'English'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='telegram_link')
    chat_id = models.BigIntegerField(unique=True)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.UZ)
    # Wall-clock time in Asia/Tashkent; null until the counselor picks one (no daily update).
    notify_time = models.TimeField(null=True, blank=True)
    prefs = models.JSONField(default=dict)
    # Fingerprint of the user's password hash: a changed password kills the link.
    auth_fingerprint = models.CharField(max_length=64)
    last_sent_date = models.DateField(null=True, blank=True)
    # Lease taken by /due so two bot instances never send the same update.
    claimed_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['is_active', 'notify_time'], name='tgl_due_idx')]

    def __str__(self):
        return f'link user={self.user_id}'


class PendingLogin(models.Model):
    """Credentials were right; waits for the counselor to press Confirm in the chat."""

    chat_id = models.BigIntegerField(unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    token_hash = models.CharField(max_length=64, unique=True)
    auth_fingerprint = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
