"""P0: internal counselor notes stay with staff; students and parents can neither read nor write them."""
from rest_framework import status
from apps.users.models import User
from ..models import MeetingNote, ParentStudentLink
from .base import RoleIsolationBase


class InternalCounselorNotesTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.student_a.notes = 'Internal: weak essays, push on deadlines'
        self.student_a.save(update_fields=['notes'])
        self.meeting_note = MeetingNote.objects.create(
            student=self.student_a, counselor=self.counselor,
            title='Private session', summary='Family pressure on major choice', next_steps='Call parents',
        )
        self.parent = User.objects.create_user(
            username='parent-notes', email='parent-notes@example.com', password='StrongPass123!',
            role=User.Role.PARENT,
        )
        ParentStudentLink.objects.create(
            parent=self.parent, student=self.student_a, status=ParentStudentLink.Status.ACTIVE,
            can_view_meetings=True,
        )

    def test_student_profile_hides_internal_notes_from_the_student(self):
        self.client.force_authenticate(self.student_a_user)
        detail = self.client.get(f'/api/students/{self.student_a.id}/')
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertNotIn('notes', detail.data)
        listing = self.client.get('/api/students/')
        self.assertNotIn('Internal: weak essays', str(listing.data))

    def test_student_cannot_edit_internal_notes(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.patch(f'/api/students/{self.student_a.id}/', {'notes': 'erased'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.notes, 'Internal: weak essays, push on deadlines')

    def test_student_cannot_read_or_change_meeting_notes(self):
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(self.client.get('/api/meetings/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.get(f'/api/meetings/{self.meeting_note.id}/').status_code, status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.patch(f'/api/meetings/{self.meeting_note.id}/', {'summary': 'x'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.delete(f'/api/meetings/{self.meeting_note.id}/').status_code, status.HTTP_403_FORBIDDEN,
        )
        created = self.client.post(
            '/api/meetings/', {'student': self.student_a.id, 'title': 'Mine', 'summary': 'x'}, format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(MeetingNote.objects.count(), 1)
        self.meeting_note.refresh_from_db()
        self.assertEqual(self.meeting_note.summary, 'Family pressure on major choice')

    def test_student_search_does_not_surface_meeting_notes(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.get('/api/search/', {'q': 'Private session'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('Family pressure', str(response.data))

    def test_parent_sees_no_internal_notes(self):
        self.client.force_authenticate(self.parent)
        portal = self.client.get('/api/parent-portal/')
        self.assertEqual(portal.status_code, status.HTTP_200_OK)
        for secret in ('Internal: weak essays', 'Family pressure', 'Call parents'):
            self.assertNotIn(secret, str(portal.data))
        self.assertEqual(self.results(self.client.get('/api/students/')), [])
        meetings = self.client.get('/api/meetings/')
        self.assertIn(meetings.status_code, {status.HTTP_200_OK, status.HTTP_403_FORBIDDEN})
        self.assertNotIn('Family pressure', str(meetings.data))
        self.assertIn(
            self.client.patch(f'/api/students/{self.student_a.id}/', {'notes': 'x'}, format='json').status_code,
            {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND},
        )

    def test_assigned_counselor_still_reads_and_writes_internal_notes(self):
        self.client.force_authenticate(self.counselor)
        detail = self.client.get(f'/api/students/{self.student_a.id}/')
        self.assertEqual(detail.data['notes'], 'Internal: weak essays, push on deadlines')
        updated = self.client.patch(f'/api/students/{self.student_a.id}/', {'notes': 'Better now'}, format='json')
        self.assertEqual(updated.status_code, status.HTTP_200_OK, updated.data)
        self.assertEqual(updated.data['notes'], 'Better now')
        meetings = self.client.get('/api/meetings/')
        self.assertEqual([row['id'] for row in self.results(meetings)], [self.meeting_note.id])
