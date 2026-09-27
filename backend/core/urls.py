from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from apps.users.auth_views import DemoAwareTokenObtainPairView, SafeTokenRefreshView
from apps.users.security import guarded_admin_login
from core.health import health_check, readiness_check

urlpatterns = [
    path('admin/login/', guarded_admin_login(admin.site.login), name='admin-login-guarded'),
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health-check'),
    path('api/health/ready/', readiness_check, name='readiness-check'),
    path('api/auth/token/', DemoAwareTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', SafeTokenRefreshView.as_view(), name='token_refresh'),
    path('api/users/', include('apps.users.urls')),
    path('api/', include('apps.admissions.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
