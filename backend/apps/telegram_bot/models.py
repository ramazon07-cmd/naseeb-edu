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


class StudentTelegram(models.Model):
    """A student's Telegram chat, linked through a one-time bot link; meeting messages go here."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='student_telegram')
    chat_id = models.BigIntegerField(unique=True)
    language = models.CharField(max_length=2, choices=TelegramLink.Language.choices, default=TelegramLink.Language.UZ)
    # Off when the student blocked the bot; the next link works again.
    is_active = models.BooleanField(default=True)
    linked_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'student telegram user={self.user_id}'


class StudentLinkToken(models.Model):
    """A one-time token inside the bot link the website gives a signed-in student.

    Only an HMAC of the token is stored. A student has at most one: the newest replaces the older one.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class StaffTelegramAccess(models.Model):
    """The Telegram @username a superadmin allowed for a counselor or assistant.

    Only that Telegram user gets the counselor login in the bot, and only for this account.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='telegram_access')
    # Lowercase, no '@'.
    telegram_username = models.CharField(max_length=32, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'@{self.telegram_username} -> user={self.user_id}'


class TelegramOutbox(models.Model):
    """A message for a student's chat; the bot fetches and sends these every minute."""

    chat_id = models.BigIntegerField()
    text = models.TextField()
    # Set for meeting reminders: one row per meeting, start time and step, so nothing is sent twice.
    key = models.CharField(max_length=120, unique=True, null=True, blank=True)
    booking = models.ForeignKey('admissions.Booking', on_delete=models.CASCADE, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    # Lease taken when handed to the bot, so two bot instances never send the same message.
    claimed_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['sent_at', 'created_at'], name='tg_outbox_pending_idx')]
