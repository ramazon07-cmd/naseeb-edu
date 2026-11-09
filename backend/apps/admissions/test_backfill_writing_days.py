from datetime import date, datetime, timezone as dt_timezone
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .essay_lab.streak import MAX_SAVE_CREDIT as MAX_WORDS_PER_SAVE
from .management.commands.backfill_essay_writing_days import reconstruct_days
from .models import Essay, EssayCheckpoint, EssayTab, EssayWritingDay
from .test_essay_lab import EssayLabFixtureMixin


def at(day, hour=6, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=dt_timezone.utc)


class BackfillTests(EssayLabFixtureMixin, TestCase):
    def setUp(self):
        self.create_people()
        self.essay = Essay.objects.create(student=self.student, title='Old', prompt='', content='')
        self.tab = EssayTab.objects.create(essay=self.essay, title='Main', position=0)

    def sample(self, when, count, tab=None, reason='auto', kind='edit', author=None):
        checkpoint = EssayCheckpoint.objects.create(
            essay=self.essay, tab=tab or self.tab, doc={}, word_count=count, reason=reason, kind=kind, author=author,
        )
        EssayCheckpoint.objects.filter(pk=checkpoint.pk).update(created_at=when)

    def run_command(self, *args):
        out = StringIO()
        call_command('backfill_essay_writing_days', *args, stdout=out)
        return out.getvalue()

    def days(self):
        return {row.date: (row.words_net, row.words_peak) for row in EssayWritingDay.objects.filter(user=self.student_user)}

    def test_reconstructs_the_peak_of_new_text_from_samples(self):
        self.sample(at(5, 6), 50)
        self.sample(at(5, 7), 120)
        self.sample(at(5, 8), 80)
        self.sample(at(5, 9), 200)
        self.sample(at(6, 6), 210)
        self.run_command('--apply')
        self.assertEqual(self.days(), {date(2026, 10, 5): (150, 150), date(2026, 10, 6): (10, 10)})

    def test_dry_run_is_the_default_and_writes_nothing(self):
        self.sample(at(5), 10)
        self.sample(at(5, 9), 140)
        output = self.run_command()
        self.assertIn('Would create 1', output)
        self.assertFalse(EssayWritingDay.objects.exists())

    def test_is_idempotent_and_never_touches_a_day_with_live_data(self):
        self.sample(at(5), 10)
        self.sample(at(5, 9), 140)
        self.sample(at(6), 10)
        self.sample(at(6, 9), 90)
        EssayWritingDay.objects.create(user=self.student_user, date=date(2026, 10, 5), words_net=3, words_peak=7)
        self.run_command('--apply')
        self.assertEqual(self.days(), {date(2026, 10, 5): (3, 7), date(2026, 10, 6): (80, 80)})
        self.assertIn('Created 0', self.run_command('--apply'))
        self.assertEqual(EssayWritingDay.objects.count(), 2)

    def test_days_are_tashkent_days(self):
        self.sample(at(5, 6), 10)
        self.sample(at(5, 19, 30), 60)
        self.run_command('--apply')
        self.assertEqual(self.days(), {date(2026, 10, 6): (50, 50)})

    def test_since_and_today_are_respected(self):
        self.sample(at(5), 10)
        self.sample(at(5, 9), 60)
        self.sample(at(7), 60)
        self.sample(at(7, 9), 160)
        now = timezone.localtime()
        self.sample(now, 160)
        self.sample(now, 300)
        self.run_command('--apply', '--since', '2026-10-06')
        self.assertEqual(set(self.days()), {date(2026, 10, 7)})

    def test_restores_and_feedback_do_not_count_as_writing(self):
        self.sample(at(5, 6), 100)
        self.sample(at(5, 7), 100, reason='restore')
        self.sample(at(5, 8), 400)
        self.sample(at(5, 9), 450, kind='suggest', author=self.counselor)
        self.sample(at(5, 10), 460)
        self.assertEqual(reconstruct_days(self.student_user.pk, [
            (self.tab.pk, at(5, 6), 100, 'auto', 'edit', None),
            (self.tab.pk, at(5, 7), 100, 'restore', 'edit', None),
            (self.tab.pk, at(5, 8), 400, 'auto', 'edit', None),
            (self.tab.pk, at(5, 9), 450, 'auto', 'suggest', self.counselor.pk),
            (self.tab.pk, at(5, 10), 460, 'auto', 'edit', None),
        ]), {date(2026, 10, 5): (10, 10)})

    def test_one_sample_jump_is_capped(self):
        self.sample(at(5), 0)
        self.sample(at(5, 9), 2000)
        self.run_command('--apply')
        self.assertEqual(self.days(), {date(2026, 10, 5): (MAX_WORDS_PER_SAVE, MAX_WORDS_PER_SAVE)})

    def test_a_bad_since_is_an_error(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            self.run_command('--since', 'soon')
