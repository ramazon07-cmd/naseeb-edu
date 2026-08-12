from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductAuditEventViewSet, RegisterView, UserViewSet

router = DefaultRouter()
router.register('accounts', UserViewSet, basename='accounts')
router.register('audit-events', ProductAuditEventViewSet, basename='audit-events')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('', include(router.urls)),
]
