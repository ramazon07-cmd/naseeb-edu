from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        COUNSELOR = 'counselor', 'Counselor'
        TEACHER = 'teacher', 'Teacher'
        ORGANIZATION = 'organization', 'Organization School'
        STUDENT = 'student', 'Student'
        PARENT = 'parent', 'Parent'

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    phone = models.CharField(max_length=32, blank=True)
    position = models.CharField(max_length=120, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    school = models.ForeignKey(
        'admissions.School',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='users',
    )
    must_change_password = models.BooleanField(default=False)
    password_version = models.PositiveIntegerField(default=1)
    password_changed_at = models.DateTimeField(null=True, blank=True)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(role='counselor') | models.Q(school__isnull=False),
                name='counselor_requires_school',
            ),
        ]

    def clean(self):
        super().clean()
        if self.role == self.Role.COUNSELOR and not self.school_id:
            raise ValidationError({'school': 'Counselors must be connected to a school.'})

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.role})'

    @property
    def is_counselor_like(self):
        return self.is_staff or self.role in {self.Role.ADMIN, self.Role.COUNSELOR}

    @property
    def is_task_manager(self):
        return self.is_counselor_like or self.role == self.Role.TEACHER

    @property
    def is_organization(self):
        return self.role == self.Role.ORGANIZATION


class TemporaryCredential(models.Model):
    class Status(models.TextChoices):
        ISSUED = 'issued', 'Issued'
        USED = 'used', 'Used'
        EXPIRED = 'expired', 'Expired'
        REVOKED = 'revoked', 'Revoked'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='temporary_credentials')
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='issued_temporary_credentials',
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ISSUED)
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-issued_at', '-id']
        indexes = [
            models.Index(fields=['user', 'status', '-issued_at'], name='temp_cred_user_status_idx'),
            models.Index(fields=['status', 'expires_at'], name='temp_cred_expiry_idx'),
        ]

    @property
    def is_expired(self):
        return self.status == self.Status.ISSUED and self.expires_at <= timezone.now()

    def __str__(self):
        return f'{self.user} · {self.status}'


class CredentialAuditEvent(models.Model):
    class Event(models.TextChoices):
        ISSUED = 'issued', 'Credential issued'
        REISSUED = 'reissued', 'Credential reissued'
        USED = 'used', 'Temporary credential used'
        EXPIRED = 'expired', 'Temporary credential expired'
        REVOKED = 'revoked', 'Credential revoked'
        PASSWORD_CHANGED = 'password_changed', 'Password changed'

    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='credential_audit_events')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='credential_actions',
    )
    event = models.CharField(max_length=32, choices=Event.choices)
    credential = models.ForeignKey(
        TemporaryCredential,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_events',
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['target_user', '-created_at'], name='cred_audit_user_created_idx')]
