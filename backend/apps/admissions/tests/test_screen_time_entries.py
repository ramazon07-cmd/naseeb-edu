from datetime import timedelta

from django.utils import timezone

from ..models import ScreenTimeDaily
from .base import RoleIsolationBase


class ScreenTimeEntryTests(RoleIsolationBase):
    def track(self, entries):
        self.client.force_authenticate(self.student_a_user)
        return self.client.post('/api/screen-time/track/', {'entries': entries}, format='json')

    def test_tomorrow_is_accepted_for_clients_ahead_of_server_time(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        response = self.track([{'date': tomorrow.isoformat(), 'page': 'roadmap', 'seconds': 30}])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ScreenTimeDaily.objects.get(user=self.student_a_user).date, tomorrow)

    def test_one_bad_entry_is_skipped_not_the_batch(self):
        today = timezone.localdate()
        response = self.track([
            {'date': today.isoformat(), 'page': 'roadmap', 'seconds': 20},
            {'date': (today + timedelta(days=2)).isoformat(), 'page': 'roadmap', 'seconds': 20},
            {'date': (today - timedelta(days=8)).isoformat(), 'page': 'roadmap', 'seconds': 20},
            {'date': 'not-a-date', 'page': 'roadmap', 'seconds': 20},
            {'date': today.isoformat(), 'page': 'bad page!', 'seconds': 20},
            {'date': today.isoformat(), 'page': 'essays', 'seconds': 0},
            'not an object',
        ])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {'tracked_seconds': 20, 'entries': 1, 'skipped': 6})
        self.assertEqual(list(ScreenTimeDaily.objects.values_list('date', 'page', 'active_seconds')), [(today, 'roadmap', 20)])

    def test_only_bad_entries_store_nothing(self):
        response = self.track([{'date': 'nope', 'page': 'roadmap', 'seconds': 20}])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {'tracked_seconds': 0, 'entries': 0, 'skipped': 1})
        self.assertFalse(ScreenTimeDaily.objects.exists())

    def test_batch_shape_and_per_page_cap_still_reject(self):
        self.assertEqual(self.track([]).status_code, 400)
        today = timezone.localdate().isoformat()
        over = [{'date': today, 'page': 'roadmap', 'seconds': 300}] * 3
        self.assertEqual(self.track(over).status_code, 400)
