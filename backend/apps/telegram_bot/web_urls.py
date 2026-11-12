from django.urls import path

from . import web_views

urlpatterns = [
    path('student/', web_views.StudentTelegramView.as_view()),
]
