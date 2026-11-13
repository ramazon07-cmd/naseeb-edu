from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .google import GoogleConnectCallbackView, GoogleConnectStartView
from .views import PlanViewSet, ProductAuditEventViewSet, UserViewSet, WorkspaceSubscriptionViewSet

router = DefaultRouter()
router.register('accounts', UserViewSet, basename='accounts')
router.register('audit-events', ProductAuditEventViewSet, basename='audit-events')
router.register('plans', PlanViewSet, basename='plans')
router.register('workspace-subscriptions', WorkspaceSubscriptionViewSet, basename='workspace-subscriptions')

urlpatterns = [
    path('google/start/', GoogleConnectStartView.as_view(), name='google-start'),
    path('google/callback/', GoogleConnectCallbackView.as_view(), name='google-callback'),
    path('', include(router.urls)),
]
