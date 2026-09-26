"""Admissions API views.

Split by domain; every name is re-exported so existing
imports such as ``from apps.admissions.views import X`` keep working.
"""
from .common import (  # noqa: F401
    INLINE_FILE_EXTENSIONS,
    serve_private_file,
    CounselorOrOwnerPermission,
    ScopedQuerysetMixin,
    CONTACT_LIST_LIMIT,
    COLLEGE_RESEARCH_LIMIT,
    SCREEN_TIME_TEAM_LIMIT,
    StaffControlledWorkPermission,
    StaffControlledWorkMixin,
    ProductAdminPermission,
)
from .students import (  # noqa: F401
    StudentProfileViewSet,
)
from .catalog import (  # noqa: F401
    SchoolViewSet,
    UniversityViewSet,
    ScholarshipViewSet,
    OpportunityProgramViewSet,
    StoreItemViewSet,
)
from .research import (  # noqa: F401
    COLLEGE_RESEARCH_QUESTIONS,
    build_college_research,
    CollegeResearchView,
    EducationMatchAIView,
)
from .records import (  # noqa: F401
    ApplicationViewSet,
    TaskViewSet,
    DocumentViewSet,
    PrivateEvidenceViewSetMixin,
    AchievementViewSet,
    ResearchViewSet,
    ProjectViewSet,
    InternshipViewSet,
    ActivityViewSet,
    HonorViewSet,
    RecommendationLetterViewSet,
    MeetingNoteViewSet,
    NotificationViewSet,
    ActivityLogViewSet,
)
from .essays import (  # noqa: F401
    EssayViewSet,
)
from .support import (  # noqa: F401
    SupportTicketPermission,
    SupportTicketViewSet,
)
from .portal import (  # noqa: F401
    StudentPortalPermission,
    StudentCollaborationPermission,
    BookingPermission,
    StudentPortalOwnedViewSet,
    booking_participants_for,
    BookingViewSet,
    StudentMessageViewSet,
    ProgramServicePermission,
    ProgramServiceViewSet,
    ScreenTimeViewSet,
    StudentTeamView,
)
from .roadmaps import (  # noqa: F401
    RoadmapMissionViewSet,
    CounselorRoadmapTemplateViewSet,
    CounselorRoadmapViewSet,
)
from .messaging import (  # noqa: F401
    messaging_contacts_for,
    discoverable_channels_for,
    attach_channel_summaries,
    moderatable_channels_for,
    channel_membership_role,
    MessageChannelPermission,
    MessageChannelViewSet,
    ChannelMessagePagination,
    ChannelMessagePermission,
    ChannelMessageViewSet,
    MessageReportPermission,
    MessageReportViewSet,
)
from .parents import (  # noqa: F401
    ParentLinkPermission,
    ParentStudentLinkViewSet,
    ParentPortalView,
)
from .dashboard import (  # noqa: F401
    PUBLIC_REACH_CACHE_KEY,
    PUBLIC_REACH_CACHE_SECONDS,
    _public_reach_counts,
    _public_reach_payload,
    PublicReachView,
    DashboardStatsView,
)
from .search import (  # noqa: F401
    GlobalSearchView,
    SEARCH_LIMIT_PER_TYPE,
)
from .challenges import (  # noqa: F401
    ChallengeAttemptPermission,
    ChallengeAttemptViewSet,
)
