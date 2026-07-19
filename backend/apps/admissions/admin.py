from django.contrib import admin
from .models import (
    Achievement,
    Activity,
    ActivityLog,
    Application,
    ApplicationStatusHistory,
    Booking,
    ChannelMembership,
    ChannelMessage,
    CommunityPost,
    Document,
    Essay,
    EssayRevision,
    Honor,
    Internship,
    LevelApproval,
    MeetingNote,
    MessageChannel,
    MessageReport,
    Notification,
    OpportunityProgram,
    ProgramService,
    Project,
    RecommendationLetter,
    Research,
    ResourceLibraryItem,
    RoadmapMission,
    School,
    Scholarship,
    StudentProfile,
    StudentMessage,
    StoreItem,
    Task,
    University,
    XPTransaction,
)


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'contact_email', 'contact_phone', 'is_active')
    search_fields = ('name', 'code', 'contact_email')
    list_filter = ('is_active',)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'school', 'level', 'xp_total', 'grade', 'gpa', 'ielts_score', 'sat_score', 'target_major', 'assigned_counselor')
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'target_major')
    list_filter = ('school', 'grade', 'scholarship_needed', 'assigned_counselor')


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ('name', 'country', 'institution_type', 'acceptance_rate', 'net_price_usd', 'ranking')
    search_fields = ('name', 'country', 'city')
    list_filter = ('country', 'institution_type', 'degree_type', 'test_optional', 'offers_international_aid')


@admin.register(Scholarship)
class ScholarshipAdmin(admin.ModelAdmin):
    list_display = ('title', 'provider', 'scholarship_type', 'funding_level', 'scope', 'deadline', 'is_active')
    search_fields = ('title', 'provider', 'university__name')
    list_filter = ('scholarship_type', 'funding_level', 'scope', 'is_active')


@admin.register(OpportunityProgram)
class OpportunityProgramAdmin(admin.ModelAdmin):
    list_display = ('title', 'provider', 'program_type', 'category', 'country', 'deadline', 'scholarship_available')
    search_fields = ('title', 'provider', 'country', 'city')
    list_filter = ('program_type', 'category', 'delivery_mode', 'scholarship_available', 'is_active')


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('student', 'university', 'program', 'tier', 'status', 'deadline')
    search_fields = ('student__user__first_name', 'student__user__last_name', 'university__name', 'program')
    list_filter = ('status', 'tier', 'university__country')


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'due_date', 'priority', 'status')
    search_fields = ('title', 'student__user__first_name', 'student__user__last_name')
    list_filter = ('status', 'priority', 'due_date')


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'document_type', 'status')
    list_filter = ('document_type', 'status')


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'category', 'date', 'verified')
    list_filter = ('category', 'verified')


@admin.register(Research)
class ResearchAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'field', 'role', 'start_date', 'verified')
    search_fields = ('title', 'student__user__first_name', 'field')
    list_filter = ('verified',)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'role', 'date', 'verified')
    search_fields = ('title', 'student__user__first_name', 'technologies')
    list_filter = ('verified',)


@admin.register(Internship)
class InternshipAdmin(admin.ModelAdmin):
    list_display = ('organization', 'position', 'student', 'start_date', 'is_current', 'verified')
    search_fields = ('organization', 'position', 'student__user__first_name')
    list_filter = ('is_current', 'verified')


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('name', 'student', 'activity_type', 'role', 'hours_per_week', 'verified')
    search_fields = ('name', 'student__user__first_name', 'role')
    list_filter = ('activity_type', 'verified')


@admin.register(Honor)
class HonorAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'issuer', 'level', 'award_date', 'verified')
    search_fields = ('title', 'issuer', 'student__user__first_name')
    list_filter = ('level', 'verified')


@admin.register(RecommendationLetter)
class RecommendationLetterAdmin(admin.ModelAdmin):
    list_display = ('student', 'recommender_name', 'recommender_title', 'status', 'deadline')
    search_fields = ('student__user__first_name', 'recommender_name', 'recommender_email')
    list_filter = ('status',)


@admin.register(Essay)
class EssayAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'application', 'version', 'status')
    list_filter = ('status',)


admin.site.register(MeetingNote)
admin.site.register(Notification)
admin.site.register(ActivityLog)
admin.site.register(ApplicationStatusHistory)
admin.site.register(EssayRevision)
admin.site.register(RoadmapMission)
admin.site.register(CommunityPost)
admin.site.register(Booking)
admin.site.register(StudentMessage)
admin.site.register(ProgramService)
admin.site.register(ResourceLibraryItem)
admin.site.register(StoreItem)
admin.site.register(XPTransaction)
admin.site.register(LevelApproval)
admin.site.register(MessageChannel)
admin.site.register(ChannelMembership)
admin.site.register(ChannelMessage)
admin.site.register(MessageReport)
