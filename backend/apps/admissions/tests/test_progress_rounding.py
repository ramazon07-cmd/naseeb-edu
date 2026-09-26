"""Every percentage uses one rule: exact value, rounded half up."""
from django.test import SimpleTestCase

from apps.admissions.models import StudentProfile
from apps.admissions.progress import ProgressStats, half_up, percent


class HalfUpTests(SimpleTestCase):
    def test_ties_round_up_like_the_browser(self):
        self.assertEqual(percent(1, 8), 13)       # 12.5
        self.assertEqual(percent(23, 40), 58)     # 57.5; float math gives 57.4999…
        self.assertEqual(percent(1, 3), 33)
        self.assertEqual(percent(2, 3), 67)
        self.assertEqual(percent(0, 0), 0)
        self.assertEqual(half_up(5, 2), 3)

    def test_stats_use_the_same_rule(self):
        stats = ProgressStats(task_counts={'approved': 1, 'todo': 7}, mission_counts={'completed': 1, 'planned': 7})
        self.assertEqual(stats.progress_percent, 13)
        self.assertEqual(stats.roadmap_progress_percent, 13)
        self.assertEqual(stats.task_progress_percent, 13)
        # (13 + 13) / 2
        self.assertEqual(stats.journey_progress_percent, 13)
        stats = ProgressStats(task_counts={'in_progress': 1, 'todo': 7}, mission_counts={'completed': 1, 'planned': 1})
        self.assertEqual(stats.task_progress_percent, 5)
        self.assertEqual(stats.journey_progress_percent, 28)  # 27.5

    def test_xp_progress_rounds_half_up(self):
        profile = StudentProfile(level=2, xp_total=100 + 25)  # 25 of the 200 XP between Level 2 and 3
        self.assertEqual(profile.xp_progress_percent, 13)
