from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PlanViewSet, ProductAuditEventViewSet, UserViewSet, WorkspaceSubscriptionViewSet

router = DefaultRouter()
router.register('accounts', UserViewSet, basename='accounts')
router.register('audit-events', ProductAuditEventViewSet, basename='audit-events')
router.register('plans', PlanViewSet, basename='plans')
router.register('workspace-subscriptions', WorkspaceSubscriptionViewSet, basename='workspace-subscriptions')

urlpatterns = [
    path('', include(router.urls)),
]
