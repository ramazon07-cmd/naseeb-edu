"""A staff member's "preview as student": their own calendar through the student filters, and nobody else's."""
from datetime import timedelta

from django.utils import timezone

from apps.users.models import User

from ..models import Booking, MeetingAvailability, MeetingSchedule
from .base import RoleIsolationBase

URL = '/api/bookings/availability/'


class PreviewAsStudentTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.assistant = User.objects.create_user(
            username='assistant-a', email='assistant-a@example.com', password='StrongPass123!',
            role=User.Role.ASSISTANT, school=self.school_a,
        )
        self.base = (timezone.now() + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
        # Window of 5 days and 24 h notice: slots at +1 h (too soon), +3 d (ok), +3 d 1 h (booked), +20 d (outside).
        MeetingSchedule.objects.create(
            participant=self.counselor, duration_minutes=45, min_notice_hours=24, window_days=5, hours={'0': [['09:00', '10:00']]},
        )
        self.soon = self.slot(timezone.now() + timedelta(hours=1))
        self.open = self.slot(self.base)
        self.taken = self.slot(self.base + timedelta(hours=1))
        self.far = self.slot(self.base + timedelta(days=17))
        Booking.objects.create(
            student=self.student_a, participant=self.counselor, availability_slot=self.taken, topic='Essay',
            starts_at=self.taken.starts_at, duration_minutes=45, status='pending',
        )

    def slot(self, start):
        return MeetingAvailability.objects.create(participant=self.counselor, starts_at=start, duration_minutes=45)

    def preview(self, user, participant):
        self.client.force_authenticate(user)
        return self.client.get(f'{URL}?as_student=1&participant={participant.id}')

    def test_staff_preview_matches_what_a_student_gets(self):
        preview = self.preview(self.counselor, self.counselor)
        self.assertEqual(preview.status_code, 200, preview.data)
        self.client.force_authenticate(self.student_a_user)
        student = self.client.get(f'{URL}?participant={self.counselor.id}').data
        self.assertEqual([slot['id'] for slot in preview.data], [slot['id'] for slot in student])
        self.assertEqual([slot['id'] for slot in preview.data], [self.open.id])
        self.assertTrue(all(slot['available'] for slot in preview.data))

    def test_the_plain_staff_listing_is_unchanged_and_shows_everything(self):
        self.client.force_authenticate(self.counselor)
        ids = {slot['id'] for slot in self.client.get(URL).data}
        self.assertEqual(ids, {self.soon.id, self.open.id, self.taken.id, self.far.id})

    def test_staff_can_only_preview_their_own_calendar(self):
        for user, other in ((self.counselor, self.teacher), (self.counselor, self.counselor_b), (self.teacher, self.counselor)):
            response = self.preview(user, other)
            self.assertEqual(response.status_code, 403, (user, other))
            self.assertNotIn('starts_at', str(response.data))
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get(f'{URL}?as_student=1').status_code, 403)
        self.assertEqual(self.client.get(f'{URL}?as_student=1&participant=abc').status_code, 400)

    def test_every_staff_role_with_hours_can_preview_itself(self):
        for user in (self.assistant, self.teacher, self.organization):
            MeetingAvailability.objects.create(participant=user, starts_at=self.base, duration_minutes=30)
            response = self.preview(user, user)
            self.assertEqual(response.status_code, 200, user.role)
            self.assertEqual([slot['participant'] for slot in response.data], [user.id])

    def test_students_cannot_use_it_to_bypass_the_filters_or_reach_other_schools(self):
        self.client.force_authenticate(self.student_a_user)
        shown = self.client.get(f'{URL}?as_student=1&participant={self.counselor.id}')
        self.assertEqual([slot['id'] for slot in shown.data], [self.open.id])
        # Still limited to the student's own school.
        self.assertEqual(self.client.get(f'{URL}?as_student=1&participant={self.counselor_b.id}').status_code, 400)

    def test_other_roles_still_cannot_list_availability(self):
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get(URL, {'as_student': '1', 'participant': self.counselor.id}).status_code, 200)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'{URL}?as_student=1&participant={self.counselor.id}').status_code, 401)
