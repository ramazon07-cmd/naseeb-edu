from django.urls import path

from . import views

urlpatterns = [
    path('login/', views.LoginView.as_view()),
    path('confirm/', views.ConfirmView.as_view()),
    path('students/', views.StudentsView.as_view()),
    path('digest/', views.DigestView.as_view()),
    path('settings/', views.SettingsView.as_view()),
    path('add-student/', views.AddStudentView.as_view()),
    path('find-students/', views.FindStudentsView.as_view()),
    path('reset-password/', views.ResetPasswordView.as_view()),
    path('student-link/', views.StudentLinkView.as_view()),
    path('whoami/', views.WhoAmIView.as_view()),
    path('student-outbox/', views.StudentOutboxView.as_view()),
    path('student-outbox/ack/', views.StudentOutboxAckView.as_view()),
    path('scheduled-jobs/', views.ScheduledJobsView.as_view()),
    # The name an older bot calls; same view.
    path('meeting-reminders/', views.ScheduledJobsView.as_view()),
    path('due/', views.DueView.as_view()),
    path('mark-sent/', views.MarkSentView.as_view()),
    path('logout/', views.LogoutView.as_view()),
    path('unlink/', views.LogoutView.as_view()),
]
