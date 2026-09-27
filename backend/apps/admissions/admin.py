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
    ParentStudentLink,
    ProgramService,
    Project,
    RecommendationLetter,
    Research,
    RoadmapMission,
    School,
    ScreenTimeDaily,
    Scholarship,
    StudentProfile,
    StudentMessage,
    StoreItem,
    SupportTicket,
    Task,
    University,
    UniversityProgram,
    XPTransaction,
)


class ScaledModelAdmin(admin.ModelAdmin):
    """Admin defaults that stay fast with tens of thousands of students.

    Foreign keys render as raw id inputs instead of <select> boxes listing
    every user/student, and change lists join their foreign keys instead of
    running one query per row.
    """

    list_select_related = True

    def __init__(self, model, admin_site):
        if not self.raw_id_fields:
            self.raw_id_fields = tuple(
                field.name for field in model._meta.fields
                if field.many_to_one and not field.auto_created
            )
        super().__init__(model, admin_site)


class StudentRecordAdmin(ScaledModelAdmin):
    list_select_related = ('student__user',)


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'region', 'workspace_type', 'owner_counselor', 'contact_email', 'is_active')
    search_fields = ('name', 'code', 'contact_email')
    list_filter = ('workspace_type', 'region', 'is_active')


@admin.register(StudentProfile)
class StudentProfileAdmin(ScaledModelAdmin):
    list_select_related = ('user', 'school', 'assigned_counselor')
    list_display = ('user', 'school', 'level', 'xp_total', 'grade', 'gpa', 'ielts_score', 'sat_score', 'target_major', 'assigned_counselor')
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'target_major')
    list_filter = ('school', 'grade', 'scholarship_needed', 'assigned_counselor')

    def save_model(self, request, obj, form, change):
        if not (change and 'school' in form.changed_data):
            return super().save_model(request, obj, form, change)
        from .tenancy import move_student

        new_school = obj.school
        obj.school_id = form.initial.get('school')
        super().save_model(request, obj, form, change)
        move_student(obj, new_school, request.user)


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ('name', 'market', 'country', 'institution_type', 'acceptance_rate', 'net_price_usd', 'ranking', 'catalog_verified_at')
    search_fields = ('name', 'country', 'city')
    list_filter = ('market', 'country', 'institution_type', 'degree_type', 'test_optional', 'offers_international_aid')


@admin.register(UniversityProgram)
class UniversityProgramAdmin(admin.ModelAdmin):
    list_display = ('name', 'university', 'canonical_major', 'degree_level', 'teaching_language', 'tuition_usd', 'verified_at', 'is_active')
    search_fields = ('name', 'canonical_major', 'university__name')
    list_filter = ('university__market', 'degree_level', 'teaching_language', 'international_students_eligible', 'is_active')


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
class ApplicationAdmin(StudentRecordAdmin):
    list_display = ('student', 'university', 'program', 'tier', 'status', 'deadline')
    search_fields = ('student__user__first_name', 'student__user__last_name', 'university__name', 'program')
    list_filter = ('status', 'tier', 'university__country')


@admin.register(Task)
class TaskAdmin(StudentRecordAdmin):
    list_display = ('title', 'student', 'due_date', 'priority', 'status')
    search_fields = ('title', 'student__user__first_name', 'student__user__last_name')
    list_filter = ('status', 'priority', 'due_date')


@admin.register(Document)
class DocumentAdmin(StudentRecordAdmin):
    list_display = ('title', 'student', 'document_type', 'status')
    list_filter = ('document_type', 'status')


@admin.register(Achievement)
class AchievementAdmin(StudentRecordAdmin):
    list_display = ('title', 'student', 'category', 'date', 'verified')
    list_filter = ('category', 'verified')


@admin.register(Research)
class ResearchAdmin(StudentRecordAdmin):
    list_display = ('title', 'student', 'field', 'role', 'start_date', 'verified')
    search_fields = ('title', 'student__user__first_name', 'field')
    list_filter = ('verified',)


@admin.register(Project)
class ProjectAdmin(StudentRecordAdmin):
    list_display = ('title', 'student', 'role', 'date', 'verified')
    search_fields = ('title', 'student__user__first_name', 'technologies')
    list_filter = ('verified',)


@admin.register(Internship)
class InternshipAdmin(StudentRecordAdmin):
    list_display = ('organization', 'position', 'student', 'start_date', 'is_current', 'verified')
    search_fields = ('organization', 'position', 'student__user__first_name')
    list_filter = ('is_current', 'verified')


@admin.register(Activity)
class ActivityAdmin(StudentRecordAdmin):
    list_display = ('name', 'student', 'activity_type', 'role', 'hours_per_week', 'verified')
    search_fields = ('name', 'student__user__first_name', 'role')
    list_filter = ('activity_type', 'verified')


@admin.register(Honor)
class HonorAdmin(StudentRecordAdmin):
    list_display = ('title', 'student', 'issuer', 'level', 'award_date', 'verified')
    search_fields = ('title', 'issuer', 'student__user__first_name')
    list_filter = ('level', 'verified')


@admin.register(RecommendationLetter)
class RecommendationLetterAdmin(StudentRecordAdmin):
    list_display = ('student', 'recommender_name', 'recommender_title', 'status', 'deadline')
    search_fields = ('student__user__first_name', 'recommender_name', 'recommender_email')
    list_filter = ('status',)


@admin.register(Essay)
class EssayAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'application', 'version', 'status', 'shared_with_counselor')
    list_filter = ('status', 'shared_with_counselor')

    def get_readonly_fields(self, request, obj=None):
        # The text lives in the document's tabs; `content` and its counts are
        # derived from them, so an edit here would be overwritten by the next
        # tab save. A new essay's text becomes its first tab when opened.
        derived = ('word_count', 'preview') if obj is None else ('content', 'word_count', 'preview')
        return (*super().get_readonly_fields(request, obj), *derived)


admin.site.register(MeetingNote, ScaledModelAdmin)
admin.site.register(Notification, ScaledModelAdmin)
admin.site.register(ActivityLog, ScaledModelAdmin)
admin.site.register(ApplicationStatusHistory, ScaledModelAdmin)
admin.site.register(EssayRevision)
admin.site.register(RoadmapMission, ScaledModelAdmin)
admin.site.register(Booking, ScaledModelAdmin)
admin.site.register(StudentMessage, ScaledModelAdmin)
admin.site.register(ProgramService, ScaledModelAdmin)
@admin.register(StoreItem)
class StoreItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'provider_name', 'price_amount', 'currency', 'is_sample', 'is_active')
    list_filter = ('is_sample', 'is_active', 'category', 'currency')
    search_fields = ('title', 'provider_name', 'provider_role')
    readonly_fields = ('catalog_key',)


admin.site.register(XPTransaction, ScaledModelAdmin)
admin.site.register(LevelApproval, ScaledModelAdmin)
admin.site.register(MessageChannel, ScaledModelAdmin)
admin.site.register(ChannelMembership, ScaledModelAdmin)
admin.site.register(ChannelMessage, ScaledModelAdmin)
admin.site.register(MessageReport, ScaledModelAdmin)


@admin.register(SupportTicket)
class SupportTicketAdmin(ScaledModelAdmin):
    list_display = ('id', 'subject', 'category', 'requester', 'status', 'responded_by', 'updated_at')
    search_fields = ('subject', 'message', 'requester__username', 'requester__email')
    list_filter = ('status', 'category', 'created_at')
    readonly_fields = ('requester', 'created_at', 'updated_at', 'responded_at', 'requester_viewed_at')


@admin.register(ScreenTimeDaily)
class ScreenTimeDailyAdmin(ScaledModelAdmin):
    list_display = ('user', 'date', 'page', 'active_seconds', 'sessions', 'last_seen_at')
    search_fields = ('user__username', 'user__email', 'page')
    list_filter = ('date', 'page')
    readonly_fields = ('user', 'date', 'page', 'active_seconds', 'sessions', 'last_seen_at')


@admin.register(ParentStudentLink)
class ParentStudentLinkAdmin(ScaledModelAdmin):
    list_display = ('parent', 'student', 'relationship', 'status', 'can_view_applications', 'can_view_documents', 'can_view_meetings')
    search_fields = ('parent__username', 'parent__email', 'student__user__username', 'student__user__email')
    list_filter = ('status', 'relationship', 'can_view_applications', 'can_view_documents', 'can_view_meetings')
