from datetime import timedelta

from django.utils import timezone

from ..meetings import SCHEDULE_DAYS
from ..models import Booking, MeetingAvailability, MeetingSchedule
from .base import RoleIsolationBase

URL = '/api/bookings/availability/weekly/'
EVERY_DAY = {str(day): [['09:00', '10:30']] for day in range(7)}


class MeetingScheduleTests(RoleIsolationBase):
    def save(self, hours=EVERY_DAY, duration=45):
        return self.client.put(URL, {'duration_minutes': duration, 'hours': hours}, format='json')

    def slots(self):
        return MeetingAvailability.objects.filter(participant=self.counselor)

    def test_weekly_hours_become_bookable_slots(self):
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get(URL).data, {'duration_minutes': 45, 'hours': {}})
        response = self.save()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.get(URL).data['hours'], EVERY_DAY)
        # 09:00 and 09:45 each day; today's may already be past.
        self.assertIn(self.slots().count(), range(SCHEDULE_DAYS * 2, (SCHEDULE_DAYS + 1) * 2 + 1))
        local = {timezone.localtime(slot.starts_at).strftime('%H:%M') for slot in self.slots()}
        self.assertEqual(local, {'09:00', '09:45'})
        self.client.force_authenticate(self.student_a_user)
        offered = self.client.get(f'/api/bookings/availability/?participant={self.counselor.id}')
        self.assertTrue(offered.data)

    def test_new_hours_replace_unbooked_slots_and_keep_booked_and_manual_ones(self):
        self.client.force_authenticate(self.counselor)
        self.save()
        booked = self.slots().order_by('starts_at')[5]
        Booking.objects.create(student=self.student_a, participant=self.counselor, availability_slot=booked,
                               topic='Essay', starts_at=booked.starts_at, duration_minutes=45)
        manual_start = (timezone.now() + timedelta(days=3)).replace(hour=15, minute=0, second=0, microsecond=0)
        manual = MeetingAvailability.objects.create(participant=self.counselor, starts_at=manual_start, duration_minutes=30)
        self.assertEqual(self.save(hours={}).status_code, 200)
        self.assertEqual(set(self.slots().values_list('id', flat=True)), {booked.id, manual.id})

    def test_slots_are_topped_up_as_time_passes(self):
        self.client.force_authenticate(self.counselor)
        self.save()
        before = self.slots().count()
        MeetingSchedule.objects.update(generated_until=timezone.localdate() + timedelta(days=SCHEDULE_DAYS - 10))
        self.client.force_authenticate(self.student_a_user)
        self.client.get(f'/api/bookings/availability/?participant={self.counselor.id}')
        # The ten missing days overlap what exists, so nothing is duplicated and the horizon moves.
        self.assertEqual(self.slots().count(), before)
        self.assertEqual(MeetingSchedule.objects.get().generated_until, timezone.localdate() + timedelta(days=SCHEDULE_DAYS))

    def test_bad_hours_are_rejected(self):
        self.client.force_authenticate(self.counselor)
        for hours in ({'7': [['09:00', '10:00']]}, {'0': [['10:00', '09:00']]}, {'0': [['09:00', '11:00'], ['10:00', '12:00']]},
                      {'0': [['9am', '10:00']]}, {'0': 'all day'}, []):
            self.assertEqual(self.save(hours=hours).status_code, 400, hours)
        self.assertEqual(self.save(duration=20).status_code, 400)
        self.assertFalse(self.slots().exists())

    def test_students_cannot_read_or_set_weekly_hours(self):
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self.save().status_code, 403)
        self.assertFalse(MeetingSchedule.objects.exists())
