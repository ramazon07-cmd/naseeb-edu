from datetime import date

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import ProductAuditEvent
from .models import (
    Application,
    ApplicationStatusHistory,
    Booking,
    ChannelMembership,
    ChannelMessage,
    Document,
    Essay,
    MeetingNote,
    MessageChannel,
    MessageReport,
    RecommendationLetter,
    RoadmapMission,
    School,
    StudentProfile,
    Task,
    University,
)


User = get_user_model()


class SchoolStudentVisibilityTests(APITestCase):
    def setUp(self):
        self.school_a = School.objects.create(name='Visibility School A', code='visibility-a')
        self.school_b = School.objects.create(name='Visibility School B', code='visibility-b')
        self.organization = User.objects.create_user(
            username='visibility-school', email='visibility-school@example.com', password='StrongPass123!',
            role=User.Role.ORGANIZATION, school=self.school_a,
        )
        self.admin = User.objects.create_user(
            username='visibility-admin', email='visibility-admin@example.com', password='StrongPass123!',
            role=User.Role.ADMIN,
        )
        self.counselor = User.objects.create_user(
            username='visibility-counselor', email='visibility-counselor@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school_a,
        )
        self.student_user = User.objects.create_user(
            username='visibility-student', email='visibility-student@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school_a, must_change_password=True,
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user,
            school=self.school_a,
            school_name=self.school_a.name,
            assigned_counselor=self.counselor,
            notes='PRIVATE COUNSELOR PROFILE NOTE',
        )
        other_user = User.objects.create_user(
            username='other-visibility-student', email='other-visibility@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school_b,
        )
        self.other_student = StudentProfile.objects.create(
            user=other_user, school=self.school_b, school_name=self.school_b.name,
        )
        university = University.objects.create(name='Visibility University', country='Testland')
        application = Application.objects.create(
            student=self.student,
            university=university,
            program='Computer Science',
            application_portal_url='https://portal.example/private',
            portal_username='PRIVATE-PORTAL-USERNAME',
            notes='PRIVATE APPLICATION NOTE',
        )
        ApplicationStatusHistory.objects.create(
            application=application, status=application.status, changed_by=self.counselor,
            note='PRIVATE STATUS NOTE',
        )
        Task.objects.create(
            student=self.student, assigned_by=self.counselor, title='Visible task',
            due_date=date(2027, 12, 1), student_response='PRIVATE TASK RESPONSE',
            submission_url='https://docs.google.com/document/d/private-task/edit',
        )
        RoadmapMission.objects.create(
            student=self.student, assigned_by=self.counselor, title='Visible roadmap mission',
            reflection='PRIVATE ROADMAP REFLECTION',
        )
        Document.objects.create(
            student=self.student, title='Visible document', document_type=Document.Type.TRANSCRIPT,
            status=Document.Status.UPLOADED, counselor_comment='PRIVATE DOCUMENT COMMENT',
        )
        Essay.objects.create(
            student=self.student, application=application, title='Essay metadata', prompt='PRIVATE ESSAY PROMPT',
            content='PRIVATE ESSAY CONTENT', counselor_comment='PRIVATE ESSAY FEEDBACK',
        )
        RecommendationLetter.objects.create(
            student=self.student, recommender_name='Teacher One', recommender_email='private-recommender@example.com',
            notes='PRIVATE RECOMMENDATION NOTE',
        )
        MeetingNote.objects.create(
            student=self.student, counselor=self.counselor, title='Private meeting',
            summary='PRIVATE MEETING SUMMARY', next_steps='PRIVATE MEETING NEXT STEPS',
        )
        Booking.objects.create(
            student=self.student, participant=self.organization, topic='Visible meeting schedule',
            starts_at='2027-12-01T09:00:00Z', notes='PRIVATE BOOKING NOTE',
        )

    @staticmethod
    def serialized(payload):
        return str(payload)

    def assert_sensitive_values_absent(self, payload):
        serialized = self.serialized(payload)
        for secret in (
            'PRIVATE COUNSELOR PROFILE NOTE', 'PRIVATE-PORTAL-USERNAME', 'PRIVATE APPLICATION NOTE',
            'PRIVATE STATUS NOTE', 'PRIVATE TASK RESPONSE', 'private-task', 'PRIVATE ROADMAP REFLECTION',
            'PRIVATE DOCUMENT COMMENT', 'PRIVATE ESSAY PROMPT', 'PRIVATE ESSAY CONTENT',
            'PRIVATE ESSAY FEEDBACK', 'private-recommender@example.com', 'PRIVATE RECOMMENDATION NOTE',
            'PRIVATE MEETING SUMMARY', 'PRIVATE MEETING NEXT STEPS', 'PRIVATE BOOKING NOTE',
        ):
            self.assertNotIn(secret, serialized)

    def test_organization_safe_360_is_own_school_and_excludes_sensitive_data(self):
        self.client.force_authenticate(self.organization)
        own = self.client.get(f'/api/students/{self.student.id}/data-visibility/')
        other = self.client.get(f'/api/students/{self.other_student.id}/data-visibility/')
        self.assertEqual(own.status_code, status.HTTP_200_OK)
        self.assertEqual(other.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(own.data['policy']['access_scope'], 'own_school')
        self.assertEqual(own.data['policy']['access_mode'], 'read_only')
        self.assertIn('private_messages', own.data['policy']['excluded'])
        self.assertIn('document_metadata_and_secure_file', own.data['policy']['included'])
        self.assert_sensitive_values_absent(own.data)
        self.assertTrue(ProductAuditEvent.objects.filter(
            actor=self.organization, action='student_visibility.viewed', target_id=str(self.student.id)
        ).exists())

    def test_admin_safe_360_is_global_but_still_not_a_sensitive_data_dump(self):
        self.client.force_authenticate(self.admin)
        own = self.client.get(f'/api/students/{self.student.id}/data-visibility/')
        other = self.client.get(f'/api/students/{self.other_student.id}/data-visibility/')
        self.assertEqual(own.status_code, status.HTTP_200_OK)
        self.assertEqual(other.status_code, status.HTTP_200_OK)
        self.assertEqual(own.data['policy']['access_scope'], 'global')
        self.assert_sensitive_values_absent(own.data)

    def test_organization_direct_admissions_serializers_redact_sensitive_fields(self):
        self.client.force_authenticate(self.organization)
        paths = ('students', 'applications', 'tasks', 'roadmap-missions', 'documents', 'essays', 'recommendations', 'bookings')
        combined = {}
        for path in paths:
            response = self.client.get(f'/api/{path}/')
            self.assertEqual(response.status_code, status.HTTP_200_OK, path)
            combined[path] = response.data
        self.assert_sensitive_values_absent(combined)
        self.assertNotIn('notes', combined['students']['results'][0])
        self.assertNotIn('portal_username', combined['applications']['results'][0])
        self.assertNotIn('notes', combined['applications']['results'][0]['status_history'][0])
        self.assertNotIn('student_response', combined['tasks']['results'][0])
        self.assertNotIn('reflection', combined['roadmap-missions']['results'][0])
        self.assertNotIn('counselor_comment', combined['documents']['results'][0])
        self.assertNotIn('content', combined['essays']['results'][0])
        self.assertNotIn('recommender_email', combined['recommendations']['results'][0])
        self.assertNotIn('notes', combined['bookings']['results'][0])
        account = self.client.get('/api/users/accounts/').data['results'][0]
        for field in ('must_change_password', 'password_changed_at', 'credential_status', 'credential_expires_at'):
            self.assertNotIn(field, account)
        self.assertEqual(self.client.get('/api/meetings/').status_code, status.HTTP_403_FORBIDDEN)

    def test_organization_cannot_write_internal_profile_notes(self):
        self.client.force_authenticate(self.organization)
        response = self.client.patch(
            f'/api/students/{self.student.id}/', {'notes': 'School should not write this'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.student.refresh_from_db()
        self.assertEqual(self.student.notes, 'PRIVATE COUNSELOR PROFILE NOTE')

    def test_school_role_does_not_automatically_grant_moderation_report_access(self):
        channel = MessageChannel.objects.create(
            kind=MessageChannel.Kind.COMMUNITY, name='Explicit moderation', school=self.school_a,
            created_by=self.counselor,
        )
        message = ChannelMessage.objects.create(channel=channel, sender=self.student_user, body='Reported')
        MessageReport.objects.create(message=message, reporter=self.counselor, reason=MessageReport.Reason.PRIVACY)
        self.client.force_authenticate(self.organization)
        denied = self.client.get('/api/message-reports/')
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        ChannelMembership.objects.create(
            channel=channel, user=self.organization, role=ChannelMembership.Role.MODERATOR,
        )
        allowed = self.client.get('/api/message-reports/')
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(allowed.data['results']), 1)
