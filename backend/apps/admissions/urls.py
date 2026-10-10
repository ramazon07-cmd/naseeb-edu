from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .telegram_feed import TelegramFeedView
from .assistant import AssistantChatView
from .views.admin_portal import AdminAiUsageView, AdminHealthView, AdminSummaryView
from .views import (
    AchievementViewSet,
    ActivityViewSet,
    ActivityLogViewSet,
    ApplicationViewSet,
    BookingViewSet,
    CatalogOpportunityProgramViewSet,
    CatalogProgramViewSet,
    CatalogScholarshipViewSet,
    CatalogUniversityViewSet,
    ChallengeAttemptViewSet,
    ChannelMessageViewSet,
    CollegeResearchView,
    CollegeSearchView,
    EducationMatchAIView,
    DashboardStatsView,
    DocumentViewSet,
    EssayViewSet,
    GlobalSearchView,
    HonorViewSet,
    InternshipViewSet,
    MeetingNoteViewSet,
    MessageChannelViewSet,
    MessageReportViewSet,
    NotificationViewSet,
    OpportunityProgramViewSet,
    ParentPortalView,
    ParentStudentLinkViewSet,
    PublicReachView,
    ProgramServiceViewSet,
    ProjectViewSet,
    RecommendationLetterViewSet,
    ResearchViewSet,
    RoadmapMissionViewSet,
    CounselorRoadmapTemplateViewSet,
    CounselorRoadmapViewSet,
    SchoolViewSet,
    ScreenTimeViewSet,
    ScholarshipViewSet,
    StudentProfileViewSet,
    StudentMessageViewSet,
    StudentParentAccessView,
    StudentTeamView,
    StoreItemViewSet,
    SupportTicketViewSet,
    TaskViewSet,
    UniversityViewSet,
)

router = DefaultRouter()
router.register('schools', SchoolViewSet, basename='schools')
router.register('students', StudentProfileViewSet, basename='students')
router.register('universities', UniversityViewSet, basename='universities')
router.register('scholarships', ScholarshipViewSet, basename='scholarships')
router.register('opportunity-programs', OpportunityProgramViewSet, basename='opportunity-programs')
router.register('catalog/universities', CatalogUniversityViewSet, basename='catalog-universities')
router.register('catalog/programs', CatalogProgramViewSet, basename='catalog-programs')
router.register('catalog/scholarships', CatalogScholarshipViewSet, basename='catalog-scholarships')
router.register('catalog/opportunity-programs', CatalogOpportunityProgramViewSet, basename='catalog-opportunity-programs')
router.register('applications', ApplicationViewSet, basename='applications')
router.register('tasks', TaskViewSet, basename='tasks')
router.register('documents', DocumentViewSet, basename='documents')
router.register('achievements', AchievementViewSet, basename='achievements')
router.register('researches', ResearchViewSet, basename='researches')
router.register('projects', ProjectViewSet, basename='projects')
router.register('internships', InternshipViewSet, basename='internships')
router.register('activities', ActivityViewSet, basename='activities')
router.register('honors', HonorViewSet, basename='honors')
router.register('recommendations', RecommendationLetterViewSet, basename='recommendations')
router.register('essays', EssayViewSet, basename='essays')
router.register('meetings', MeetingNoteViewSet, basename='meetings')
router.register('notifications', NotificationViewSet, basename='notifications')
router.register('activity', ActivityLogViewSet, basename='activity')
router.register('roadmap-missions', RoadmapMissionViewSet, basename='roadmap-missions')
router.register('counselor-roadmap-templates', CounselorRoadmapTemplateViewSet, basename='counselor-roadmap-templates')
router.register('counselor-roadmaps', CounselorRoadmapViewSet, basename='counselor-roadmaps')
router.register('bookings', BookingViewSet, basename='bookings')
router.register('student-messages', StudentMessageViewSet, basename='student-messages')
router.register('message-channels', MessageChannelViewSet, basename='message-channels')
router.register('channel-messages', ChannelMessageViewSet, basename='channel-messages')
router.register('message-reports', MessageReportViewSet, basename='message-reports')
router.register('program-services', ProgramServiceViewSet, basename='program-services')
router.register('store-items', StoreItemViewSet, basename='store-items')
router.register('support-tickets', SupportTicketViewSet, basename='support-tickets')
router.register('screen-time', ScreenTimeViewSet, basename='screen-time')
router.register('parent-links', ParentStudentLinkViewSet, basename='parent-links')
router.register('challenge-attempts', ChallengeAttemptViewSet, basename='challenge-attempts')

urlpatterns = [
    path('telegram-feed/', TelegramFeedView.as_view(), name='telegram-feed'),
    path('assistant/chat/', AssistantChatView.as_view(), name='assistant-chat'),
    path('public/reach/', PublicReachView.as_view(), name='public-reach'),
    path('dashboard/stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('admin/summary/', AdminSummaryView.as_view(), name='admin-summary'),
    path('admin/ai-usage/', AdminAiUsageView.as_view(), name='admin-ai-usage'),
    path('admin/health/', AdminHealthView.as_view(), name='admin-health'),
    path('search/', GlobalSearchView.as_view(), name='global-search'),
    path('college-research/', CollegeResearchView.as_view(), name='college-research'),
    path('college-search/', CollegeSearchView.as_view(), name='college-search'),
    path('education-matches/ai/', EducationMatchAIView.as_view(), name='education-match-ai'),
    path('student-team/', StudentTeamView.as_view(), name='student-team'),
    path('parent-portal/', ParentPortalView.as_view(), name='parent-portal'),
    path('my-parents/', StudentParentAccessView.as_view(), name='student-parent-access'),
    path('essay-lab/', include('apps.admissions.essay_lab.urls')),
    path('', include(router.urls)),
]
