from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .assistant import AssistantChatView
from .views import (
    AchievementViewSet,
    ActivityViewSet,
    ActivityLogViewSet,
    ApplicationViewSet,
    BookingViewSet,
    ChannelMessageViewSet,
    CommunityPostViewSet,
    CollegeResearchView,
    DashboardStatsView,
    DocumentViewSet,
    EssayViewSet,
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
    ResourceLibraryItemViewSet,
    RoadmapMissionViewSet,
    CounselorRoadmapTemplateViewSet,
    CounselorRoadmapViewSet,
    SchoolViewSet,
    ScreenTimeViewSet,
    ScholarshipViewSet,
    StudentProfileViewSet,
    StudentMessageViewSet,
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
router.register('community-posts', CommunityPostViewSet, basename='community-posts')
router.register('bookings', BookingViewSet, basename='bookings')
router.register('student-messages', StudentMessageViewSet, basename='student-messages')
router.register('message-channels', MessageChannelViewSet, basename='message-channels')
router.register('channel-messages', ChannelMessageViewSet, basename='channel-messages')
router.register('message-reports', MessageReportViewSet, basename='message-reports')
router.register('program-services', ProgramServiceViewSet, basename='program-services')
router.register('resource-library', ResourceLibraryItemViewSet, basename='resource-library')
router.register('store-items', StoreItemViewSet, basename='store-items')
router.register('support-tickets', SupportTicketViewSet, basename='support-tickets')
router.register('screen-time', ScreenTimeViewSet, basename='screen-time')
router.register('parent-links', ParentStudentLinkViewSet, basename='parent-links')

urlpatterns = [
    path('assistant/chat/', AssistantChatView.as_view(), name='assistant-chat'),
    path('public/reach/', PublicReachView.as_view(), name='public-reach'),
    path('dashboard/stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('college-research/', CollegeResearchView.as_view(), name='college-research'),
    path('student-team/', StudentTeamView.as_view(), name='student-team'),
    path('parent-portal/', ParentPortalView.as_view(), name='parent-portal'),
    path('', include(router.urls)),
]
