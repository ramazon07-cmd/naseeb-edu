from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .collab_views import ReviewEssayViewSet
from .views import EssayFolderViewSet, EssayLabEssayViewSet

router = SimpleRouter()
router.register('essays', EssayLabEssayViewSet, basename='essay-lab-essays')
router.register('folders', EssayFolderViewSet, basename='essay-lab-folders')
# Staff side of shared essays (the assigned counselor; admins read).
router.register('review/essays', ReviewEssayViewSet, basename='essay-lab-review')

urlpatterns = [
    path('', include(router.urls)),
]
