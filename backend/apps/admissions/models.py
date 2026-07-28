from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class School(TimeStampedModel):
    name = models.CharField(max_length=180, unique=True)
    code = models.SlugField(max_length=80, unique=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class StudentProfile(TimeStampedModel):
    MAX_LEVEL = 100
    class Grade(models.TextChoices):
        GRADE_8 = '8', '8-sinf'
        GRADE_9 = '9', '9-sinf'
        GRADE_10 = '10', '10-sinf'
        GRADE_11 = '11', '11-sinf'
        GAP_YEAR = 'gap', 'Gap year'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='student_profile')
    assigned_counselor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_students',
    )
    grade = models.CharField(max_length=10, choices=Grade.choices, default=Grade.GRADE_10)
    school_name = models.CharField(max_length=180, default='Naseeb Edu')
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='students',
    )
    gpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    ielts_score = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    sat_score = models.PositiveIntegerField(null=True, blank=True)
    target_major = models.CharField(max_length=160, blank=True)
    target_countries = models.CharField(max_length=255, blank=True, help_text='Comma-separated countries')
    budget_usd = models.PositiveIntegerField(null=True, blank=True)
    scholarship_needed = models.BooleanField(default=True)
    parent_contact = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    xp_total = models.PositiveIntegerField(default=0)
    level = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @staticmethod
    def xp_required_for_level(level):
        """Level 1 starts at 0 XP; each next level costs 100 XP more."""
        normalized_level = max(1, int(level))
        return 100 * normalized_level * (normalized_level - 1) // 2

    @property
    def eligible_level(self):
        eligible = 1
        while eligible < self.MAX_LEVEL and self.xp_total >= self.xp_required_for_level(eligible + 1):
            eligible += 1
        return eligible

    @property
    def next_level_xp(self):
        if self.level >= self.MAX_LEVEL:
            return self.xp_required_for_level(self.MAX_LEVEL)
        return self.xp_required_for_level(self.level + 1)

    @property
    def xp_progress_percent(self):
        if self.level >= self.MAX_LEVEL or self.eligible_level > self.level:
            return 100
        current_threshold = self.xp_required_for_level(self.level)
        next_threshold = self.next_level_xp
        span = max(1, next_threshold - current_threshold)
        return min(100, round(((self.xp_total - current_threshold) / span) * 100))

    @property
    def level_up_pending(self):
        return self.eligible_level > self.level

    @property
    def progress_percent(self):
        total = self.tasks.count() + self.applications.count() + self.documents.count()
        if total == 0:
            return 0
        done_tasks = self.tasks.filter(status=Task.Status.APPROVED).count()
        done_apps = self.applications.filter(status__in=[Application.Status.SUBMITTED, Application.Status.ACCEPTED]).count()
        done_docs = self.documents.filter(status=Document.Status.APPROVED).count()
        return round(((done_tasks + done_apps + done_docs) / total) * 100)

    @property
    def task_progress_percent(self):
        """Return a weighted task completion score instead of a binary done/not-done score."""
        weights = {
            Task.Status.TODO: 0,
            Task.Status.LATE: 0,
            Task.Status.IN_PROGRESS: 40,
            Task.Status.SUBMITTED: 80,
            Task.Status.APPROVED: 100,
        }
        statuses = list(self.tasks.values_list('status', flat=True))
        if not statuses:
            return 0
        return round(sum(weights.get(status, 0) for status in statuses) / len(statuses))

    @property
    def roadmap_progress_percent(self):
        total = self.roadmap_missions.count()
        if total == 0:
            return 0
        completed = self.roadmap_missions.filter(status=RoadmapMission.Status.COMPLETED).count()
        return round((completed / total) * 100)

    @property
    def journey_progress_percent(self):
        task_exists = self.tasks.exists()
        roadmap_exists = self.roadmap_missions.exists()
        if task_exists and roadmap_exists:
            return round((self.task_progress_percent + self.roadmap_progress_percent) / 2)
        if task_exists:
            return self.task_progress_percent
        if roadmap_exists:
            return self.roadmap_progress_percent
        return 0

    @property
    def is_at_risk(self):
        today = timezone.localdate()
        return self.tasks.filter(status=Task.Status.LATE).exists() or self.tasks.filter(
            due_date__lt=today,
        ).exclude(status=Task.Status.APPROVED).exists() or self.roadmap_missions.filter(
            due_date__lt=today,
        ).exclude(status=RoadmapMission.Status.COMPLETED).exists()


class University(TimeStampedModel):
    class Tier(models.TextChoices):
        DREAM = 'dream', 'Dream'
        TARGET = 'target', 'Target'
        SAFETY = 'safety', 'Safety'

    class InstitutionType(models.TextChoices):
        PUBLIC = 'public', 'Public'
        PRIVATE = 'private', 'Private'

    class CampusSetting(models.TextChoices):
        URBAN = 'urban', 'Urban'
        SUBURBAN = 'suburban', 'Suburban'
        RURAL = 'rural', 'Rural'

    class DegreeType(models.TextChoices):
        FOUR_YEAR = 'four_year', '4-year'
        TWO_YEAR = 'two_year', '2-year'

    name = models.CharField(max_length=220)
    country = models.CharField(max_length=120)
    city = models.CharField(max_length=120, blank=True)
    website = models.URLField(blank=True)
    ranking = models.PositiveIntegerField(null=True, blank=True)
    institution_type = models.CharField(max_length=20, choices=InstitutionType.choices, default=InstitutionType.PRIVATE)
    campus_setting = models.CharField(max_length=20, choices=CampusSetting.choices, blank=True)
    degree_type = models.CharField(max_length=20, choices=DegreeType.choices, default=DegreeType.FOUR_YEAR)
    acceptance_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    sat_min = models.PositiveSmallIntegerField(null=True, blank=True)
    sat_max = models.PositiveSmallIntegerField(null=True, blank=True)
    act_min = models.PositiveSmallIntegerField(null=True, blank=True)
    act_max = models.PositiveSmallIntegerField(null=True, blank=True)
    tuition_usd = models.PositiveIntegerField(null=True, blank=True)
    net_price_usd = models.PositiveIntegerField(null=True, blank=True)
    average_aid_usd = models.PositiveIntegerField(null=True, blank=True)
    students_receiving_aid_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    undergrad_enrollment = models.PositiveIntegerField(null=True, blank=True)
    student_faculty_ratio = models.CharField(max_length=20, blank=True)
    test_optional = models.BooleanField(default=False)
    offers_need_based_aid = models.BooleanField(default=False)
    offers_merit_aid = models.BooleanField(default=False)
    offers_athletic_aid = models.BooleanField(default=False)
    offers_international_aid = models.BooleanField(default=False)
    need_blind = models.BooleanField(default=False)
    meets_full_need = models.BooleanField(default=False)
    css_profile_required = models.BooleanField(default=False)
    fafsa_required = models.BooleanField(default=False)
    aid_application_notes = models.TextField(blank=True)
    financial_aid_url = models.URLField(blank=True)
    popular_majors = models.CharField(max_length=300, blank=True, help_text='Comma-separated majors')
    application_deadline = models.DateField(null=True, blank=True)
    scholarship_deadline = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['country', 'ranking', 'name']
        unique_together = ('name', 'country')

    def __str__(self):
        return f'{self.name}, {self.country}'


class Scholarship(TimeStampedModel):
    class Type(models.TextChoices):
        MERIT = 'merit', 'Merit'
        NEED_BASED = 'need_based', 'Need-based'
        ATHLETIC = 'athletic', 'Athletic'
        LEADERSHIP = 'leadership', 'Leadership'
        RESEARCH = 'research', 'Research'
        DIVERSITY = 'diversity', 'Diversity'
        FULL_RIDE = 'full_ride', 'Full ride'

    class FundingLevel(models.TextChoices):
        FULL = 'full', 'Full funding'
        PARTIAL = 'partial', 'Partial funding'
        FIXED = 'fixed', 'Fixed amount'

    class Scope(models.TextChoices):
        NATIONAL = 'national', 'National'
        INTERNATIONAL = 'international', 'International'

    university = models.ForeignKey(
        University,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scholarships',
    )
    title = models.CharField(max_length=220)
    provider = models.CharField(max_length=180)
    scholarship_type = models.CharField(max_length=30, choices=Type.choices)
    funding_level = models.CharField(max_length=20, choices=FundingLevel.choices, default=FundingLevel.PARTIAL)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.INTERNATIONAL)
    amount_usd = models.PositiveIntegerField(null=True, blank=True)
    coverage = models.CharField(max_length=300, blank=True)
    eligible_countries = models.CharField(max_length=300, blank=True)
    eligible_grades = models.CharField(max_length=120, blank=True)
    min_gpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    min_ielts = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    min_sat = models.PositiveSmallIntegerField(null=True, blank=True)
    requires_essay = models.BooleanField(default=False)
    requires_recommendation = models.BooleanField(default=False)
    requires_financial_documents = models.BooleanField(default=False)
    requires_transcript = models.BooleanField(default=True)
    requires_cv = models.BooleanField(default=False)
    requires_portfolio = models.BooleanField(default=False)
    deadline = models.DateField(null=True, blank=True)
    application_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['deadline', 'title']

    def __str__(self):
        return self.title


class OpportunityProgram(TimeStampedModel):
    class ProgramType(models.TextChoices):
        NATIONAL = 'national', 'National'
        INTERNATIONAL = 'international', 'International'

    class DeliveryMode(models.TextChoices):
        ONSITE = 'onsite', 'On-site'
        ONLINE = 'online', 'Online'
        HYBRID = 'hybrid', 'Hybrid'

    title = models.CharField(max_length=220)
    provider = models.CharField(max_length=180)
    program_type = models.CharField(max_length=20, choices=ProgramType.choices)
    category = models.CharField(max_length=100)
    country = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120, blank=True)
    delivery_mode = models.CharField(max_length=20, choices=DeliveryMode.choices, default=DeliveryMode.ONSITE)
    description = models.TextField(blank=True)
    eligible_grades = models.CharField(max_length=120, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    fee_usd = models.PositiveIntegerField(null=True, blank=True)
    scholarship_available = models.BooleanField(default=False)
    aid_details = models.CharField(max_length=300, blank=True)
    requirements = models.TextField(blank=True)
    application_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['program_type', 'deadline', 'title']

    def __str__(self):
        return self.title


class Application(TimeStampedModel):
    class Status(models.TextChoices):
        RESEARCHING = 'researching', 'Researching'
        SHORTLISTED = 'shortlisted', 'Shortlisted'
        APPLYING = 'applying', 'Applying'
        SUBMITTED = 'submitted', 'Submitted'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'
        WAITLISTED = 'waitlisted', 'Waitlisted'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='applications')
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name='applications')
    program = models.CharField(max_length=220)
    tier = models.CharField(max_length=20, choices=University.Tier.choices, default=University.Tier.TARGET)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.RESEARCHING)
    deadline = models.DateField(null=True, blank=True)
    scholarship_deadline = models.DateField(null=True, blank=True)
    application_portal_url = models.URLField(blank=True)
    portal_username = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['deadline', 'university__name']
        unique_together = ('student', 'university', 'program')

    def __str__(self):
        return f'{self.student} → {self.university.name}'


class ApplicationStatusHistory(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='status_history')
    status = models.CharField(max_length=30, choices=Application.Status.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.application} — {self.status}'


class Task(TimeStampedModel):
    class Status(models.TextChoices):
        TODO = 'todo', 'To Do'
        IN_PROGRESS = 'in_progress', 'In Progress'
        SUBMITTED = 'submitted', 'Submitted'
        APPROVED = 'approved', 'Approved'
        LATE = 'late', 'Late'

    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        URGENT = 'urgent', 'Urgent'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='tasks')
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_tasks')
    title = models.CharField(max_length=220)
    description = models.TextField(blank=True)
    due_date = models.DateField()
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.TODO)
    student_response = models.TextField(blank=True)
    submission_url = models.URLField(blank=True)
    submission_file = models.FileField(upload_to='task_submissions/', blank=True, null=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['due_date', '-priority']

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        return self.status not in {self.Status.APPROVED} and self.due_date < timezone.localdate()


class RoadmapMission(TimeStampedModel):
    class Status(models.TextChoices):
        PLANNED = 'planned', 'Planned'
        IN_PROGRESS = 'in_progress', 'In Progress'
        SUBMITTED = 'submitted', 'Submitted for approval'
        COMPLETED = 'completed', 'Completed'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='roadmap_missions')
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_roadmap_missions',
    )
    title = models.CharField(max_length=220)
    category = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    level = models.PositiveSmallIntegerField(default=1)
    sequence = models.PositiveSmallIntegerField(default=1)
    prerequisite = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unlocked_missions',
    )
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PLANNED)
    reflection = models.TextField(blank=True)

    class Meta:
        ordering = ['level', 'sequence', 'id']

    def __str__(self):
        return self.title


class XPTransaction(models.Model):
    class Source(models.TextChoices):
        TASK = 'task', 'Task approval'
        ROADMAP = 'roadmap', 'Roadmap approval'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='xp_transactions')
    source_type = models.CharField(max_length=20, choices=Source.choices)
    source_id = models.PositiveBigIntegerField()
    amount = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)
    awarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='awarded_xp_transactions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['source_type', 'source_id'], name='unique_xp_per_approved_work'),
        ]

    def __str__(self):
        return f'{self.student}: +{self.amount} XP ({self.source_type} #{self.source_id})'


class LevelApproval(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='level_approvals')
    from_level = models.PositiveSmallIntegerField()
    to_level = models.PositiveSmallIntegerField()
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='approved_student_levels',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.student}: Level {self.from_level} → {self.to_level}'


class CommunityPost(TimeStampedModel):
    class Type(models.TextChoices):
        DISCUSSION = 'discussion', 'Discussion'
        QUESTION = 'question', 'Q&A'
        UPDATE = 'update', 'Update'

    author = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='community_posts')
    post_type = models.CharField(max_length=20, choices=Type.choices, default=Type.DISCUSSION)
    title = models.CharField(max_length=220)
    body = models.TextField()
    liked_by = models.ManyToManyField(StudentProfile, blank=True, related_name='liked_community_posts')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Booking(TimeStampedModel):
    class Status(models.TextChoices):
        REQUESTED = 'requested', 'Requested'
        CONFIRMED = 'confirmed', 'Confirmed'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='bookings')
    counselor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_bookings',
    )
    topic = models.CharField(max_length=220)
    starts_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=45)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['starts_at']

    def __str__(self):
        return f'{self.student} — {self.topic}'


class StudentMessage(TimeStampedModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='portal_messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_student_messages')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_student_messages')
    body = models.TextField()
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender} → {self.recipient}'


class MessageChannel(TimeStampedModel):
    class Kind(models.TextChoices):
        DIRECT = 'direct', 'Direct'
        GROUP = 'group', 'Group'
        COMMUNITY = 'community', 'Community'
        DISCUSSION = 'discussion', 'Discussion'

    kind = models.CharField(max_length=20, choices=Kind.choices)
    name = models.CharField(max_length=180, blank=True)
    description = models.TextField(blank=True)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='message_channels',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_message_channels',
    )
    direct_key = models.CharField(max_length=80, unique=True, null=True, blank=True)
    is_public = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-last_message_at', '-updated_at']
        indexes = [
            models.Index(fields=['kind', 'school', 'is_public'], name='msg_channel_discovery_idx'),
            models.Index(fields=['last_message_at'], name='msg_channel_recent_idx'),
        ]

    def __str__(self):
        return self.name or f'{self.kind} #{self.pk}'


class ChannelMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        MODERATOR = 'moderator', 'Moderator'
        MEMBER = 'member', 'Member'

    channel = models.ForeignKey(MessageChannel, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='channel_memberships')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(null=True, blank=True)
    notifications_enabled = models.BooleanField(default=True)
    muted_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['joined_at', 'id']
        constraints = [
            models.UniqueConstraint(fields=['channel', 'user'], name='unique_channel_membership'),
        ]
        indexes = [models.Index(fields=['user', 'channel'], name='msg_member_lookup_idx')]

    def __str__(self):
        return f'{self.user} in {self.channel}'


class ChannelMessage(TimeStampedModel):
    channel = models.ForeignKey(MessageChannel, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='channel_messages',
    )
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    body = models.TextField()
    is_anonymous = models.BooleanField(default=False)
    is_edited = models.BooleanField(default=False)
    is_accepted_answer = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at', 'id']
        indexes = [
            models.Index(fields=['channel', '-created_at'], name='msg_channel_timeline_idx'),
            models.Index(fields=['parent', 'created_at'], name='msg_thread_reply_idx'),
        ]

    def __str__(self):
        return f'{self.channel} — message #{self.pk}'


class MessageReport(TimeStampedModel):
    class Reason(models.TextChoices):
        SPAM = 'spam', 'Spam'
        HARASSMENT = 'harassment', 'Harassment or bullying'
        UNSAFE = 'unsafe', 'Unsafe content'
        PRIVACY = 'privacy', 'Privacy concern'
        MISINFORMATION = 'misinformation', 'Misinformation'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        REVIEWING = 'reviewing', 'Reviewing'
        RESOLVED = 'resolved', 'Resolved'
        DISMISSED = 'dismissed', 'Dismissed'

    class Action(models.TextChoices):
        NONE = 'none', 'No action'
        CONTENT_REMOVED = 'content_removed', 'Content removed'
        MUTED_24H = 'muted_24h', 'Member muted for 24 hours'
        MUTED_7D = 'muted_7d', 'Member muted for 7 days'

    message = models.ForeignKey(ChannelMessage, on_delete=models.CASCADE, related_name='reports')
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='message_reports',
    )
    reason = models.CharField(max_length=30, choices=Reason.choices)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    action = models.CharField(max_length=30, choices=Action.choices, default=Action.NONE)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_message_reports',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    moderator_note = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['message', 'reporter'], name='unique_message_reporter'),
        ]
        indexes = [
            models.Index(fields=['status', '-created_at'], name='msg_report_status_idx'),
            models.Index(fields=['message', 'status'], name='msg_report_message_idx'),
        ]

    def __str__(self):
        return f'Report #{self.pk} for message #{self.message_id}'


class ProgramService(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PENDING = 'pending', 'Mentor pending'
        COMPLETED = 'completed', 'Completed'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='program_services')
    name = models.CharField(max_length=220)
    category = models.CharField(max_length=160, blank=True)
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mentored_program_services',
    )
    total_hours = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    used_hours = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    unlimited = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ['status', 'name']

    def __str__(self):
        return f'{self.student} — {self.name}'


class ResourceLibraryItem(TimeStampedModel):
    title = models.CharField(max_length=220)
    category = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    destination = models.CharField(max_length=80, blank=True, help_text='Student frontend page key')
    external_url = models.URLField(blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['category', 'sort_order', 'title']

    def __str__(self):
        return self.title


class StoreItem(TimeStampedModel):
    title = models.CharField(max_length=220)
    category = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    price_label = models.CharField(max_length=80, blank=True)
    destination_url = models.URLField(blank=True)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-is_featured', 'category', 'title']

    def __str__(self):
        return self.title


class Document(TimeStampedModel):
    class Type(models.TextChoices):
        PASSPORT = 'passport', 'Passport'
        TRANSCRIPT = 'transcript', 'Transcript'
        IELTS = 'ielts', 'IELTS'
        SAT = 'sat', 'SAT'
        CV = 'cv', 'CV / Resume'
        REC_LETTER = 'recommendation', 'Recommendation Letter'
        ESSAY = 'essay', 'Essay'
        CERTIFICATE = 'certificate', 'Certificate'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        REQUIRED = 'required', 'Required'
        UPLOADED = 'uploaded', 'Uploaded'
        REVIEWING = 'reviewing', 'Reviewing'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=220)
    document_type = models.CharField(max_length=40, choices=Type.choices, default=Type.OTHER)
    file = models.FileField(upload_to='student_documents/', blank=True, null=True)
    google_docs_url = models.URLField(blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.REQUIRED)
    counselor_comment = models.TextField(blank=True)

    class Meta:
        ordering = ['student__user__first_name', 'document_type']

    def __str__(self):
        return self.title


class Achievement(TimeStampedModel):
    class Category(models.TextChoices):
        OLYMPIAD = 'olympiad', 'Olympiad'
        STARTUP = 'startup', 'Startup'
        VOLUNTEERING = 'volunteering', 'Volunteering'
        LEADERSHIP = 'leadership', 'Leadership'
        RESEARCH = 'research', 'Research'
        PROJECT = 'project', 'Project'
        SPORT = 'sport', 'Sport'
        ART = 'art', 'Art'
        OTHER = 'other', 'Other'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='achievements')
    title = models.CharField(max_length=220)
    category = models.CharField(max_length=40, choices=Category.choices)
    description = models.TextField()
    impact = models.CharField(max_length=255, blank=True)
    date = models.DateField(null=True, blank=True)
    proof_file = models.FileField(upload_to='achievement_proofs/', blank=True, null=True)
    verified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date', 'title']

    def __str__(self):
        return self.title


class Research(TimeStampedModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='researches')
    title = models.CharField(max_length=220)
    field = models.CharField(max_length=160, blank=True)
    role = models.CharField(max_length=160, blank=True)
    summary = models.TextField()
    outcome = models.CharField(max_length=255, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    link = models.URLField(blank=True)
    google_docs_url = models.URLField(blank=True)
    verified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-start_date', 'title']

    def __str__(self):
        return self.title


class Project(TimeStampedModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='projects')
    title = models.CharField(max_length=220)
    role = models.CharField(max_length=160, blank=True)
    description = models.TextField()
    impact = models.CharField(max_length=255, blank=True)
    technologies = models.CharField(max_length=255, blank=True)
    link = models.URLField(blank=True)
    google_docs_url = models.URLField(blank=True)
    date = models.DateField(null=True, blank=True)
    verified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date', 'title']

    def __str__(self):
        return self.title


class Internship(TimeStampedModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='internships')
    organization = models.CharField(max_length=220)
    position = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    supervisor = models.CharField(max_length=180, blank=True)
    google_docs_url = models.URLField(blank=True)
    verified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-start_date', 'organization']

    def __str__(self):
        return f'{self.position} — {self.organization}'


class Activity(TimeStampedModel):
    class Type(models.TextChoices):
        EXTRACURRICULAR = 'extracurricular', 'Extracurricular'
        VOLUNTEERING = 'volunteering', 'Volunteering'
        LEADERSHIP = 'leadership', 'Leadership'
        CLUB = 'club', 'Club'
        COMPETITION = 'competition', 'Competition'
        COMMUNITY = 'community', 'Community Service'
        OTHER = 'other', 'Other'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='activities')
    name = models.CharField(max_length=220)
    activity_type = models.CharField(max_length=40, choices=Type.choices, default=Type.EXTRACURRICULAR)
    role = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    impact = models.CharField(max_length=255, blank=True)
    hours_per_week = models.PositiveSmallIntegerField(null=True, blank=True)
    weeks_per_year = models.PositiveSmallIntegerField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    google_docs_url = models.URLField(blank=True)
    verified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-start_date', 'name']

    def __str__(self):
        return self.name


class Honor(TimeStampedModel):
    class Level(models.TextChoices):
        SCHOOL = 'school', 'School'
        REGIONAL = 'regional', 'Regional'
        NATIONAL = 'national', 'National'
        INTERNATIONAL = 'international', 'International'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='honors')
    title = models.CharField(max_length=220)
    issuer = models.CharField(max_length=220, blank=True)
    level = models.CharField(max_length=30, choices=Level.choices, default=Level.SCHOOL)
    award_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    proof_file = models.FileField(upload_to='honor_proofs/', blank=True, null=True)
    google_docs_url = models.URLField(blank=True)
    verified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-award_date', 'title']

    def __str__(self):
        return self.title


class RecommendationLetter(TimeStampedModel):
    class Status(models.TextChoices):
        REQUESTED = 'requested', 'Requested'
        DRAFTING = 'drafting', 'Drafting'
        SUBMITTED = 'submitted', 'Submitted'
        APPROVED = 'approved', 'Approved'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='recommendations')
    recommender_name = models.CharField(max_length=180)
    recommender_title = models.CharField(max_length=180, blank=True)
    recommender_email = models.EmailField(blank=True)
    relationship = models.CharField(max_length=180, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.REQUESTED)
    deadline = models.DateField(null=True, blank=True)
    file = models.FileField(upload_to='recommendation_letters/', blank=True, null=True)
    google_docs_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['deadline', 'recommender_name']

    def __str__(self):
        return f'{self.student} — {self.recommender_name}'


class Essay(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        NEEDS_REVISION = 'needs_revision', 'Needs Revision'
        REVIEWING = 'reviewing', 'Reviewing'
        APPROVED = 'approved', 'Approved'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='essays')
    application = models.ForeignKey(Application, on_delete=models.SET_NULL, null=True, blank=True, related_name='essays')
    title = models.CharField(max_length=220)
    prompt = models.TextField()
    content = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.DRAFT)
    counselor_comment = models.TextField(blank=True)
    google_docs_url = models.URLField(blank=True)

    class Meta:
        ordering = ['student__user__first_name', 'status', '-updated_at']

    def __str__(self):
        return self.title


class EssayRevision(models.Model):
    essay = models.ForeignKey(Essay, on_delete=models.CASCADE, related_name='revisions')
    version = models.PositiveIntegerField()
    prompt = models.TextField()
    content = models.TextField(blank=True)
    status = models.CharField(max_length=40, choices=Essay.Status.choices)
    counselor_comment = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version', '-created_at']
        unique_together = ('essay', 'version')

    def __str__(self):
        return f'{self.essay.title} v{self.version}'


class MeetingNote(TimeStampedModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='meeting_notes')
    counselor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='meeting_notes')
    title = models.CharField(max_length=220)
    meeting_date = models.DateField(default=timezone.localdate)
    summary = models.TextField()
    next_steps = models.TextField(blank=True)

    class Meta:
        ordering = ['-meeting_date']

    def __str__(self):
        return self.title


class Notification(TimeStampedModel):
    class Channel(models.TextChoices):
        SYSTEM = 'system', 'System'
        EMAIL = 'email', 'Email'
        TELEGRAM = 'telegram', 'Telegram'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=220)
    message = models.TextField()
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.SYSTEM)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class ActivityLog(TimeStampedModel):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='activity_logs')
    student = models.ForeignKey(StudentProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    action = models.CharField(max_length=180)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.action
