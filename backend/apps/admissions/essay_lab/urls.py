from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import EssayFolderViewSet, EssayLabEssayViewSet

router = SimpleRouter()
router.register('essays', EssayLabEssayViewSet, basename='essay-lab-essays')
router.register('folders', EssayFolderViewSet, basename='essay-lab-folders')

urlpatterns = [
    path('', include(router.urls)),
]
