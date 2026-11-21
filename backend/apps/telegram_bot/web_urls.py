from django.urls import path

from . import web_views

urlpatterns = [
    path('student/', web_views.StudentTelegramView.as_view()),
    path('student/link/', web_views.StudentTelegramLinkView.as_view()),
    path('staff-access/', web_views.StaffAccessListView.as_view()),
    path('staff-access/<int:user_id>/', web_views.StaffAccessDetailView.as_view()),
]
