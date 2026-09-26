from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
from django.utils import timezone


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # A superuser is a product admin in the app, not a student with a
        # Django-admin login.
        extra_fields.setdefault('role', User.Role.ADMIN)
        extra_fields.setdefault('admin_tier', User.AdminTier.SUPERADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class AdminTier(models.TextChoices):
        SUPPORT = 'support', 'Support'
        OPS = 'ops', 'Operations'
        SUPERADMIN = 'superadmin', 'Super admin'

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
    admin_tier = models.CharField(
        max_length=16,
        choices=AdminTier.choices,
        blank=True,
        help_text='Product staff permission level. Only meaningful for admin accounts.',
    )

    objects = UserManager()

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(role='counselor') | models.Q(school__isnull=False),
                name='counselor_requires_school',
            ),
            # A parent's reach comes only from accepted links to children.
            models.CheckConstraint(
                condition=~models.Q(role='parent') | models.Q(school__isnull=True),
                name='parent_has_no_school',
            ),
        ]
        indexes = [models.Index(fields=['first_name', 'last_name', 'id'], name='user_name_order_idx')]

    def clean(self):
        super().clean()
        if self.role == self.Role.COUNSELOR and not self.school_id:
            raise ValidationError({'school': 'Counselors must be connected to a school.'})
        if self.role == self.Role.PARENT and self.school_id:
            raise ValidationError({'school': 'Parent accounts are not connected to a school.'})
        if self.role == self.Role.STUDENT and not self.is_superuser and not self.school_id:
            raise ValidationError({'school': 'Students must belong to a school.'})

    def save(self, *args, **kwargs):
        # Admins created without an explicit tier keep the historical full
        # access; non-admin accounts never carry a staff tier.
        if self.role == self.Role.ADMIN:
            self.admin_tier = self.admin_tier or self.AdminTier.SUPERADMIN
        elif not self.is_superuser:
            self.admin_tier = ''
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and 'role' in update_fields:
            kwargs['update_fields'] = {*update_fields, 'admin_tier'}
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.role})'

    @property
    def staff_tier(self):
        """Effective product-staff tier, or '' for non-staff accounts."""
        if self.is_superuser:
            return self.AdminTier.SUPERADMIN
        if self.role == self.Role.ADMIN:
            return self.admin_tier or self.AdminTier.SUPERADMIN
        return ''

    @property
    def is_product_admin(self):
        """Product authorization is independent from Django admin-site access."""
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def is_counselor_like(self):
        return self.is_product_admin or self.role == self.Role.COUNSELOR

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


class ProductAuditEvent(models.Model):
    """Immutable product-level audit trail; Django's admin log is intentionally separate."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='product_audit_events',
    )
    action = models.CharField(max_length=80, db_index=True)
    target_type = models.CharField(max_length=80, db_index=True)
    target_id = models.CharField(max_length=80, blank=True)
    target_label = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    # Workspace the event belongs to, so the audit log filters by school
    # without parsing metadata.
    school = models.ForeignKey(
        'admissions.School',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['-created_at', '-id'], name='audit_created_id_idx'),
            models.Index(fields=['school', '-created_at'], name='product_audit_school_idx'),
            models.Index(fields=['actor', '-created_at'], name='product_audit_actor_idx'),
        ]

    def __str__(self):
        return f'{self.action}: {self.target_type} {self.target_id}'


# Fixed schema for Plan.features: every plan stores exactly these boolean keys.
PLAN_FEATURES = ('ai_assistant', 'essay_coach', 'parent_portal', 'reports', 'organization_accounts')
# Seat limits a plan can set; NULL means unlimited.
PLAN_LIMITS = ('max_counselors', 'max_students', 'max_teachers')


def normalize_plan_features(value):
    if not isinstance(value, dict):
        raise ValidationError({'features': 'Features must be an object.'})
    unknown = sorted(set(value) - set(PLAN_FEATURES))
    if unknown:
        raise ValidationError({'features': f'Unknown feature flags: {", ".join(unknown)}.'})
    if any(not isinstance(flag, bool) for flag in value.values()):
        raise ValidationError({'features': 'Feature flags must be true or false.'})
    return {key: value.get(key, False) for key in PLAN_FEATURES}


class Plan(models.Model):
    """A named set of entitlements. Prices and billing live elsewhere."""

    code = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    max_counselors = models.PositiveIntegerField(null=True, blank=True)
    max_students = models.PositiveIntegerField(null=True, blank=True)
    max_teachers = models.PositiveIntegerField(null=True, blank=True)
    features = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'id']

    def clean(self):
        super().clean()
        self.features = normalize_plan_features(self.features)

    def save(self, *args, **kwargs):
        self.features = normalize_plan_features(self.features)
        super().save(*args, **kwargs)

    def limit(self, key):
        if key not in PLAN_LIMITS:
            raise KeyError(key)
        return getattr(self, key)

    def has_feature(self, key):
        if key not in PLAN_FEATURES:
            raise KeyError(key)
        return bool(self.features.get(key))

    def __str__(self):
        return self.name


class WorkspaceSubscription(models.Model):
    """Links one workspace (School) to its plan and access state."""

    class Status(models.TextChoices):
        TRIAL = 'trial', 'Trial'
        ACTIVE = 'active', 'Active'
        SUSPENDED = 'suspended', 'Suspended'
        EXPIRED = 'expired', 'Expired'

    READ_ONLY_STATUSES = frozenset({Status.SUSPENDED, Status.EXPIRED})

    school = models.OneToOneField('admissions.School', on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='subscriptions')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    period_start = models.DateField(null=True, blank=True)
    # An open-ended subscription has no end date; a past end date makes the
    # workspace read-only even before anyone flips the status.
    period_end = models.DateField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(period_start__isnull=True)
                | models.Q(period_end__isnull=True)
                | models.Q(period_end__gte=models.F('period_start')),
                name='subscription_period_order',
            ),
        ]

    def clean(self):
        super().clean()
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValidationError({'period_end': 'The period cannot end before it starts.'})

    @staticmethod
    def read_only_for(status, period_end, today=None):
        if status in WorkspaceSubscription.READ_ONLY_STATUSES:
            return True
        return bool(period_end and period_end < (today or timezone.localdate()))

    @property
    def is_read_only(self):
        return self.read_only_for(self.status, self.period_end)

    def __str__(self):
        return f'{self.school} · {self.plan} ({self.status})'
