"""Role isolation: parent invites and the parent portal."""
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from apps.users.models import User
from ..models import (
    Application,
    Booking,
    Document,
    Essay,
    ParentStudentLink,
    StudentMessage,
    StudentProfile,
    Task,
    University,
)
from .base import RoleIsolationBase


class ParentRoleIsolationTests(RoleIsolationBase):
    def test_parent_invite_requires_consent_and_counselor_scope(self):
        self.client.force_authenticate(self.counselor)
        invited = self.client.post(
            '/api/parent-links/invite/',
            {
                'student': self.student_a.id,
                'email': 'parent-a@example.com',
                'first_name': 'Dilnoza',
                'last_name': 'Parent',
                'password': 'StrongParent123!',
                'relationship': ParentStudentLink.Relationship.MOTHER,
                'can_view_applications': True,
                'can_view_documents': True,
                'can_view_meetings': True,
            },
            format='json',
        )
        self.assertEqual(invited.status_code, status.HTTP_201_CREATED, invited.data)
        parent = User.objects.get(email='parent-a@example.com')
        self.assertEqual(parent.role, User.Role.PARENT)
        link = ParentStudentLink.objects.get(parent=parent, student=self.student_a)
        self.assertEqual(link.status, ParentStudentLink.Status.PENDING)

        denied = self.client.post(
            '/api/parent-links/invite/',
            {
                'student': self.student_b.id,
                'email': 'other-parent@example.com',
                'password': 'StrongParent123!',
                'relationship': ParentStudentLink.Relationship.GUARDIAN,
            },
            format='json',
        )
        # Same 400 as a non-existent id (no student-id enumeration).
        self.assertEqual(denied.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='other-parent@example.com').exists())

        self.client.force_authenticate(parent)
        before_consent = self.client.get('/api/parent-portal/')
        self.assertEqual(before_consent.status_code, status.HTTP_200_OK)
        self.assertEqual(before_consent.data['children'], [])
        self.assertEqual([item['id'] for item in before_consent.data['pending_invitations']], [link.id])
        accepted = self.client.post(f'/api/parent-links/{link.id}/accept/', {}, format='json')
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        link.refresh_from_db()
        self.assertEqual(link.status, ParentStudentLink.Status.ACTIVE)
        self.assertIsNotNone(link.consented_at)

    def test_parent_portal_is_read_only_and_never_exposes_private_student_data(self):
        parent = User.objects.create_user(
            username='privacy-parent', email='privacy-parent@example.com',
            password='StrongParent123!', role=User.Role.PARENT,
        )
        ParentStudentLink.objects.create(
            parent=parent, student=self.student_a, status=ParentStudentLink.Status.ACTIVE,
            relationship=ParentStudentLink.Relationship.FATHER,
            consented_at=timezone.now(),
        )
        Task.objects.create(
            student=self.student_a, assigned_by=self.counselor, title='Visible task title',
            description='Counselor-only detail', student_response='Private student response',
            due_date=timezone.localdate() + timedelta(days=4),
        )
        university = University.objects.create(name='Parent Test University', country='Singapore')
        Application.objects.create(
            student=self.student_a, university=university, program='Computer Science',
            application_portal_url='https://private.example.com', portal_username='private-login',
            notes='Private application note',
        )
        Document.objects.create(
            student=self.student_a, title='Transcript', document_type=Document.Type.TRANSCRIPT,
            counselor_comment='Private counselor note', google_docs_url='https://docs.google.com/document/d/private/edit',
        )
        Essay.objects.create(
            student=self.student_a, title='Private essay', prompt='Prompt', content='Private essay body',
            counselor_comment='Private essay feedback',
        )
        StudentMessage.objects.create(
            student=self.student_a, sender=self.student_a_user, recipient=self.counselor,
            body='Private student message',
        )
        Booking.objects.create(
            student=self.student_a, participant=self.counselor, topic='Application check-in',
            starts_at=timezone.now() + timedelta(days=2), notes='Private meeting note',
        )
        self.student_a.notes = 'Private counselor profile note'
        self.student_a.save(update_fields=['notes'])

        self.client.force_authenticate(parent)
        response = self.client.get('/api/parent-portal/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['children']), 1)
        child = response.data['children'][0]
        self.assertEqual(child['profile']['id'], self.student_a.id)
        serialized = str(response.data)
        for secret in (
            'Private student response', 'Counselor-only detail', 'private-login',
            'Private application note', 'Private counselor note', 'private.example.com',
            'Private essay', 'Private essay body', 'Private essay feedback',
            'Private student message', 'Private meeting note', 'Private counselor profile note',
            'docs.google.com',
        ):
            self.assertNotIn(secret, serialized)
        self.assertEqual(child['tasks'][0]['title'], 'Visible task title')
        self.assertEqual(child['documents'][0]['title'], 'Transcript')
        self.assertEqual(child['meetings'][0]['topic'], 'Application check-in')

        self.assertEqual(self.results(self.client.get('/api/students/')), [])
        self.assertEqual(self.client.get('/api/tasks/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.results(self.client.get('/api/applications/')), [])
        self.assertEqual(self.results(self.client.get('/api/documents/')), [])
        self.assertEqual(self.client.get('/api/student-messages/').status_code, status.HTTP_403_FORBIDDEN)

    def test_parent_only_sees_active_linked_children_and_permissioned_sections(self):
        parent = User.objects.create_user(
            username='multi-parent', email='multi-parent@example.com',
            password='StrongParent123!', role=User.Role.PARENT,
        )
        ParentStudentLink.objects.create(
            parent=parent, student=self.student_a, status=ParentStudentLink.Status.ACTIVE,
            can_view_applications=False, can_view_documents=False, can_view_meetings=False,
            consented_at=timezone.now(),
        )
        ParentStudentLink.objects.create(
            parent=parent, student=self.student_b, status=ParentStudentLink.Status.REVOKED,
            revoked_at=timezone.now(),
        )
        sibling_user = User.objects.create_user(
            username='linked-sibling', email='linked-sibling@example.com',
            password='StrongPass123!', role=User.Role.STUDENT, school=self.school_a,
        )
        sibling = StudentProfile.objects.create(
            user=sibling_user, school=self.school_a, school_name=self.school_a.name,
            assigned_counselor=self.counselor,
        )
        ParentStudentLink.objects.create(
            parent=parent, student=sibling, status=ParentStudentLink.Status.ACTIVE,
            consented_at=timezone.now(),
        )
        other_parent = User.objects.create_user(
            username='other-family', email='other-family@example.com',
            password='StrongParent123!', role=User.Role.PARENT,
        )
        ParentStudentLink.objects.create(
            parent=other_parent, student=self.student_b, status=ParentStudentLink.Status.ACTIVE,
            consented_at=timezone.now(),
        )
        self.client.force_authenticate(parent)
        portal = self.client.get('/api/parent-portal/')
        self.assertEqual(
            {child['profile']['id'] for child in portal.data['children']},
            {self.student_a.id, sibling.id},
        )
        self.assertNotIn(self.student_b.id, {child['profile']['id'] for child in portal.data['children']})
        child = next(item for item in portal.data['children'] if item['profile']['id'] == self.student_a.id)
        self.assertEqual(child['applications'], [])
        self.assertEqual(child['documents'], [])
        self.assertEqual(child['meetings'], [])
        links = self.results(self.client.get('/api/parent-links/'))
        self.assertEqual({item['parent'] for item in links}, {parent.id})
