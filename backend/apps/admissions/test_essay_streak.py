import os
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status

from .essay_lab.streak import DEFAULT_SAVE_CREDIT, MAX_SAVE_CREDIT as MAX_WORDS_PER_SAVE, clamp_essay_seconds, goal_met, record_essay_seconds, record_words, streak_numbers
from .models import EssayCheckpoint, EssayTab, EssayWritingDay, ScreenTimeDaily
from .test_essay_lab import BASE, EssayLabTestCase, StatementCountMixin, make_doc


User = get_user_model()
URL = f'{BASE}/streak/'
# 2026-11-08 09:00 in Tashkent (UTC+5).
NOON = datetime(2026, 11, 8, 4, 0, tzinfo=dt_timezone.utc)


def words(count, prefix='w'):
    return make_doc(' '.join(f'{prefix}{i}' for i in range(count)))


@contextmanager
def clock(moment):
    with mock.patch('django.utils.timezone.now', return_value=moment):
        yield


class StreakTestCase(EssayLabTestCase):
    def setUp(self):
        super().setUp()
        self.essay = self.make_essay(content='')
        self.counter = 0

    def write(self, count, moment=None, essay=None, prefix='w'):
        self.counter += 1
        essay = essay or self.essay
        with clock(moment or NOON + timedelta(minutes=10 * self.counter)):
            response = self.autosave(essay, words(count, prefix), save_id=f'streak-{self.counter}')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response

    def day(self, moment=NOON):
        return EssayWritingDay.objects.get(user=self.student_user, date=(moment + timedelta(hours=5)).date())

    def make_days(self, **by_offset):
        for offset, (word_count, seconds) in by_offset.items():
            when = date(2026, 11, 8) - timedelta(days=int(offset[1:]))
            if word_count:
                EssayWritingDay.objects.create(user=self.student_user, date=when, words_net=word_count,
                                               words_peak=word_count, goal_met=goal_met(word_count, 0))
            if seconds:
                self.add_time(when, seconds)

    def add_time(self, when, seconds, page='essay_lab', user=None):
        record_essay_seconds(user or self.student_user, {(when, page): seconds}, date(2026, 11, 8))

    def get(self, query='', moment=NOON):
        with clock(moment):
            return self.client.get(URL + query)


class RecordingTests(StatementCountMixin, StreakTestCase):
    def test_growth_is_recorded(self):
        self.write(20)
        self.write(35)
        row = self.day()
        self.assertEqual((row.words_net, row.words_peak), (35, 35))

    def test_deleting_lowers_the_net_but_not_the_peak(self):
        self.write(25)
        self.write(15)
        row = self.day()
        self.assertEqual((row.words_net, row.words_peak), (15, 25))
        self.write(5)
        row = self.day()
        self.assertEqual((row.words_net, row.words_peak), (5, 25))

    def test_type_and_delete_cycles_do_not_accumulate(self):
        for _ in range(6):
            self.write(60)
            self.write(0)
        self.write(60)
        row = self.day()
        self.assertEqual((row.words_net, row.words_peak), (60, 60))

    def test_delete_only_save_leaves_no_writing(self):
        essay = self.make_essay(content=' '.join(f'x{i}' for i in range(50)))
        with clock(NOON):
            response = self.autosave(essay, words(10), save_id='delete-only')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.get().data['days'], {})
        self.assertEqual(self.get().data['progress']['words'], 0)

    def test_trimming_old_text_then_writing_counts_the_fresh_writing(self):
        essay = self.make_essay(content=' '.join(f'old{i}' for i in range(400)))
        self.write(100, essay=essay, prefix='cut')
        self.assertEqual(self.get().data['progress']['words'], 0)
        self.write(250, essay=essay, prefix='cut')
        row = self.day()
        self.assertEqual((row.words_net, row.words_peak), (MAX_WORDS_PER_SAVE, MAX_WORDS_PER_SAVE))

    def test_one_save_is_capped(self):
        self.write(2000)
        self.assertEqual(self.day().words_peak, DEFAULT_SAVE_CREDIT)

    def test_a_pasted_block_after_a_short_pause_does_not_meet_the_goal(self):
        self.write(5, moment=NOON)
        self.write(155, moment=NOON + timedelta(seconds=30))
        row = self.day()
        self.assertLess(row.words_peak, 100)
        self.assertFalse(row.goal_met)

    def test_back_to_back_saves_do_not_add_up_to_the_goal(self):
        for count in (20, 40, 60, 80, 100):
            self.write(count, moment=NOON)
        self.assertLess(self.day().words_peak, 100)
        self.assertFalse(self.day().goal_met)

    def test_a_huge_delete_is_not_capped(self):
        self.write(250)
        self.write(1000)
        self.write(0)
        self.assertEqual(self.day().words_net, 0)
        self.write(40)
        self.assertEqual(self.day().words_net, 40)

    def test_small_saves_add_up_beyond_the_cap(self):
        for total in (200, 400, 600):
            self.write(total)
        self.assertEqual(self.day().words_peak, DEFAULT_SAVE_CREDIT + 2 * MAX_WORDS_PER_SAVE)

    def test_duplicate_adds_nothing(self):
        self.write(150)
        before = self.day().words_peak
        response = self.client.post(f'{BASE}/essays/{self.essay.pk}/duplicate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        tab_id = self.tab_of(self.essay).pk
        response = self.client.post(f'{BASE}/essays/{self.essay.pk}/tabs/{tab_id}/duplicate/', {}, format='json')
        self.assertIn(response.status_code, (200, 201))
        row = self.day()
        self.assertEqual((row.words_net, row.words_peak), (before, before))

    def test_creating_an_essay_adds_nothing(self):
        response = self.client.post(f'{BASE}/essays/', {'title': 'New', 'content': ' '.join(['w'] * 200)}, format='json')
        self.assertIn(response.status_code, (200, 201), response.data)
        self.assertFalse(EssayWritingDay.objects.exists())

    def test_restoring_a_version_adds_nothing(self):
        self.write(5)
        checkpoint = EssayCheckpoint.objects.get(essay=self.essay)
        self.write(0)
        self.write(0)
        EssayCheckpoint.objects.filter(pk=checkpoint.pk).update(doc=words(250), content=' '.join(['w'] * 250))
        before = EssayWritingDay.objects.values_list('words_net', 'words_peak').get()
        tab = self.tab_of(self.essay)
        tab.refresh_from_db()
        response = self.client.post(f'{BASE}/essays/{self.essay.pk}/checkpoints/{checkpoint.pk}/restore/',
                                    {'base_seq': tab.save_seq}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(EssayWritingDay.objects.values_list('words_net', 'words_peak').get(), before)

    def test_a_failure_while_recording_never_fails_the_save(self):
        with mock.patch('apps.admissions.essay_lab.streak.connection') as broken:
            broken.cursor.side_effect = RuntimeError('boom')
            self.write(30)
        self.assertFalse(EssayWritingDay.objects.exists())
        self.assertEqual(self.tab_of(self.essay).word_count, 30)

    def test_interleaved_saves_from_two_essays_lose_nothing(self):
        other = self.make_essay(content='')
        user = self.student_user
        record_words(user, 0, 20, NOON)
        record_words(user, 0, 25, NOON)
        record_words(user, 20, 10, NOON)
        record_words(user, 25, 50, NOON)
        row = self.day()
        self.assertEqual((row.words_net, row.words_peak), (60, 60))
        self.assertEqual(other.pk != self.essay.pk, True)

    def test_a_word_change_is_exactly_one_query_and_no_change_is_none(self):
        record_words(self.student_user, 0, 10, NOON)
        with self.assertNumQueries(1):
            record_words(self.student_user, 10, 25, NOON)
        with self.assertNumQueries(1):
            record_words(self.student_user, 25, 5, NOON)
        with self.assertNumQueries(0):
            record_words(self.student_user, 5, 5, NOON)

    def test_each_user_has_their_own_day(self):
        record_words(self.student_user, 0, 10, NOON)
        record_words(self.other_user, 0, 25, NOON)
        self.assertEqual(self.day().words_peak, 10)
        self.assertEqual(EssayWritingDay.objects.get(user=self.other_user).words_peak, 25)


class TashkentDayTests(StreakTestCase):
    def test_midnight_in_tashkent_splits_days(self):
        late = datetime(2026, 11, 8, 18, 59, 30, tzinfo=dt_timezone.utc)
        early = datetime(2026, 11, 8, 19, 0, 30, tzinfo=dt_timezone.utc)
        self.write(10, late)
        self.write(30, early)
        self.assertEqual(
            list(EssayWritingDay.objects.order_by('date').values_list('date', 'words_peak')),
            [(date(2026, 11, 8), 10), (date(2026, 11, 9), 20)],
        )

    def test_boundaries_do_not_depend_on_the_process_timezone(self):
        original = os.environ.get('TZ')
        try:
            os.environ['TZ'] = 'America/Los_Angeles'
            time.tzset()
            late = datetime(2026, 11, 8, 18, 59, 30, tzinfo=dt_timezone.utc)
            early = datetime(2026, 11, 8, 19, 0, 30, tzinfo=dt_timezone.utc)
            self.write(10, late)
            self.write(30, early)
            self.assertEqual(
                list(EssayWritingDay.objects.order_by('date').values_list('date', flat=True)),
                [date(2026, 11, 8), date(2026, 11, 9)],
            )
            self.assertEqual(self.get(moment=early).data['today'], '2026-11-09')
        finally:
            if original is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = original
            time.tzset()

    def test_today_comes_from_the_server_clock(self):
        self.assertEqual(self.get(moment=datetime(2026, 11, 8, 19, 30, tzinfo=dt_timezone.utc)).data['today'],
                         '2026-11-09')
        self.assertEqual(self.get(moment=datetime(2026, 11, 8, 18, 30, tzinfo=dt_timezone.utc)).data['today'],
                         '2026-11-08')


class StreakRuleTests(StreakTestCase):
    def test_streak_numbers(self):
        today = date(2026, 11, 8)
        fire = {today - timedelta(days=n) for n in (0, 1, 2, 5, 6, 7, 8, 9)}
        self.assertEqual(streak_numbers(fire, today), (3, 5))
        self.assertEqual(streak_numbers(set(), today), (0, 0))

    def test_today_in_progress_does_not_break_the_streak(self):
        self.make_days(d1=(150, 0), d2=(100, 0), d3=(150, 0))
        data = self.get().data
        self.assertEqual((data['current'], data['best']), (3, 3))
        self.assertFalse(data['progress']['goal_met'])

    def test_finishing_today_extends_the_streak(self):
        self.make_days(d0=(120, 0), d1=(150, 0))
        self.assertEqual(self.get().data['current'], 2)
        self.assertTrue(self.get().data['progress']['goal_met'])

    def test_a_missed_day_breaks_the_streak(self):
        self.make_days(d2=(150, 0), d3=(150, 0))
        data = self.get().data
        self.assertEqual((data['current'], data['best']), (0, 2))

    def test_an_ember_day_breaks_the_streak(self):
        self.make_days(d1=(150, 0), d2=(40, 0), d3=(150, 0), d4=(150, 0))
        data = self.get().data
        self.assertEqual((data['current'], data['best']), (1, 2))

    def test_an_ember_today_does_not_count_and_does_not_yet_break(self):
        self.make_days(d0=(30, 0), d1=(150, 0))
        self.assertEqual(self.get().data['current'], 1)

    def test_best_streak_can_be_in_the_past(self):
        self.make_days(d1=(150, 0), d10=(150, 0), d11=(150, 0), d12=(150, 0), d13=(150, 0))
        data = self.get().data
        self.assertEqual((data['current'], data['best']), (1, 4))

    def test_fire_by_words_and_by_time_with_some_writing(self):
        self.make_days(d0=(25, 600), d1=(100, 0), d2=(24, 900), d3=(99, 0))
        days = self.get().data['days']
        self.assertEqual(days, {'2026-11-08': 'fire', '2026-11-07': 'fire', '2026-11-06': 'ember',
                                '2026-11-05': 'ember'})

    def test_time_alone_never_makes_a_fire_day(self):
        self.add_time(date(2026, 11, 8), 3600)
        data = self.get().data
        self.assertEqual(data['days'], {'2026-11-08': 'ember'})
        self.assertEqual((data['current'], data['progress']), (0, {'words': 0, 'minutes': 60, 'goal_met': False}))

    def test_time_from_other_pages_and_other_students_does_not_count(self):
        self.make_days(d0=(30, 0))
        self.add_time(date(2026, 11, 8), 900, page='dashboard')
        self.add_time(date(2026, 11, 8), 900, user=self.other_user)
        data = self.get().data
        self.assertEqual((data['progress']['minutes'], data['progress']['goal_met']), (0, False))

    def test_time_counts_on_its_own_day_and_a_future_date_counts_as_today(self):
        self.make_days(d2=(30, 0), d3=(30, 0))
        self.add_time(date(2026, 11, 6), 900)
        self.add_time(date(2026, 11, 5), 900)
        self.add_time(date(2026, 11, 9), 900)
        data = self.get().data
        self.assertEqual(data['current'], 0)
        self.assertEqual(data['days'], {'2026-11-08': 'ember', '2026-11-06': 'fire', '2026-11-05': 'fire'})

    def test_a_day_met_by_time_stays_fire_after_its_time_is_no_longer_read(self):
        self.make_days(d1=(30, 700), d2=(150, 0))
        self.assertEqual(self.get().data['current'], 2)
        self.assertTrue(EssayWritingDay.objects.get(date=date(2026, 11, 7)).goal_met)
        later = self.get(moment=NOON + timedelta(days=3)).data
        self.assertEqual(later['days']['2026-11-07'], 'fire')
        self.assertEqual(later['best'], 2)

    def test_progress_for_today(self):
        self.make_days(d0=(142, 725))
        data = self.get().data
        self.assertEqual(data['progress'], {'words': 142, 'minutes': 12, 'goal_met': True})
        self.assertEqual(data['goal'], {'words': 100, 'minutes': 10})


class StreakEndpointTests(StreakTestCase):
    def test_default_payload_shape(self):
        data = self.get().data
        self.assertEqual(set(data), {'today', 'current', 'best', 'progress', 'goal', 'month', 'days'})
        self.assertEqual(data['today'], '2026-11-08')
        self.assertEqual(data['month'], '2026-11')
        self.assertEqual((data['current'], data['best'], data['days']), (0, 0, {}))

    def test_month_selects_days_and_omits_empty_ones(self):
        EssayWritingDay.objects.create(user=self.student_user, date=date(2026, 10, 31), words_peak=120, goal_met=True)
        EssayWritingDay.objects.create(user=self.student_user, date=date(2026, 11, 1), words_peak=5)
        self.assertEqual(self.get('?month=2026-10').data['days'], {'2026-10-31': 'fire'})
        self.assertEqual(self.get('?month=2026-11').data['days'], {'2026-11-01': 'ember'})
        self.assertEqual(self.get('?month=2025-01').data['days'], {})

    def test_month_validation(self):
        for value in ('', 'nope', '2026-13', '2026-00', '2026-1', '2026-11-01', '2026-12', '2027-01', '9999-12',
                      '0000-01', '2026-11 ', '-2026-11'):
            with self.subTest(month=value):
                response = self.get(f'?month={value}')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                self.assertEqual(response.data['code'], 'invalid_month')

    def test_past_months_are_fine(self):
        self.assertEqual(self.get('?month=2020-02').status_code, status.HTTP_200_OK)

    def test_next_month_opens_in_tashkent_time(self):
        moment = datetime(2026, 11, 30, 19, 30, tzinfo=dt_timezone.utc)
        self.assertEqual(self.get('?month=2026-12', moment).status_code, status.HTTP_200_OK)

    def test_a_student_only_sees_their_own_days(self):
        EssayWritingDay.objects.create(user=self.other_user, date=date(2026, 11, 7), words_peak=500, goal_met=True)
        EssayWritingDay.objects.create(user=self.other_user, date=date(2026, 11, 8), words_peak=500, goal_met=True)
        data = self.get().data
        self.assertEqual((data['current'], data['best'], data['days']), (0, 0, {}))
        self.assertEqual(data['progress']['words'], 0)
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.get().data['current'], 2)

    def test_other_users_cannot_be_requested(self):
        EssayWritingDay.objects.create(user=self.other_user, date=date(2026, 11, 8), words_peak=500, goal_met=True)
        response = self.get(f'?user={self.other_user.pk}&student={self.other_student.pk}')
        self.assertEqual(response.data['progress']['words'], 0)

    def test_every_other_role_gets_403(self):
        parent = User.objects.create_user(
            username='lab-parent', email='lab-parent@example.com', password='StrongPass123!',
            role=User.Role.PARENT,
        )
        assistant = User.objects.create_user(
            username='lab-assistant', email='lab-assistant@example.com', password='StrongPass123!',
            role=User.Role.ASSISTANT, school=self.school,
        )
        admin = User.objects.create_user(
            username='lab-admin', email='lab-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        for user in (self.counselor, assistant, self.teacher, parent, self.organization, admin):
            with self.subTest(role=user.role):
                self.client.force_authenticate(user)
                self.assertEqual(self.get().status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(None)
        self.assertIn(self.get().status_code, (401, 403))

    def test_only_get_is_allowed(self):
        self.assertEqual(self.client.post(URL, {}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_query_count_is_bounded(self):
        for offset in range(1, 200):
            EssayWritingDay.objects.create(user=self.student_user, date=date(2026, 11, 8) - timedelta(days=offset),
                                           words_peak=150, goal_met=True)
        self.add_time(date(2026, 11, 8), 100)
        with clock(NOON), CaptureQueriesContext(connection) as queries:
            response = self.client.get(URL)
        self.assertEqual(response.data['current'], 199)
        self.assertEqual(len(queries), 2, [q['sql'] for q in queries])

    def test_the_endpoint_is_in_the_openapi_schema(self):
        response = self.client.get('/api/schema/')
        if response.status_code == status.HTTP_200_OK:
            self.assertIn('/api/essay-lab/streak/', response.content.decode())


class OwnWordsDeltaTests(StreakTestCase):
    def test_a_stored_block_that_cannot_be_measured_credits_nothing_and_does_not_raise(self):
        from .essay_lab.streak import own_words_delta
        self.assertEqual(own_words_delta({'content': [{'attrs': {'bid': 'a'}, 'type': 'paragraph', 'content': 5}]},
                                         [{'del': 'a', 'base': 'x'}]), 0)


class ClampEssaySecondsTests(StreakTestCase):
    """A report may credit at most the wall-clock time since the previous one (plus slack)."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()

    def clamp(self, seconds, moment, page='essay_lab'):
        return clamp_essay_seconds(self.student_user, {(date(2026, 11, 8), page): seconds}, moment)

    def test_one_inflated_batch_cannot_meet_the_time_goal(self):
        self.write(30)
        clamped = self.clamp(600, NOON)
        record_essay_seconds(self.student_user, clamped, date(2026, 11, 8))
        row = self.day()
        self.assertEqual(row.active_seconds, 30)
        self.assertFalse(row.goal_met)

    def test_honest_thirty_second_reports_are_credited_in_full(self):
        self.clamp(30, NOON)
        later = NOON + timedelta(seconds=30)
        self.assertEqual(self.clamp(30, later), {(date(2026, 11, 8), 'essay_lab'): 30})

    def test_a_burst_right_after_a_report_is_trimmed(self):
        self.clamp(30, NOON)
        burst = self.clamp(600, NOON + timedelta(seconds=30))
        self.assertEqual(burst, {(date(2026, 11, 8), 'essay_lab'): 40})

    def test_seconds_dated_in_the_past_are_credited_to_today(self):
        past = date(2026, 11, 5)
        clamped = clamp_essay_seconds(self.student_user, {(past, 'essay_lab'): 30}, NOON)
        self.assertEqual(clamped, {(date(2026, 11, 8), 'essay_lab'): 30})
        record_essay_seconds(self.student_user, clamped, date(2026, 11, 8))
        self.assertFalse(EssayWritingDay.objects.filter(user=self.student_user, date=past).exists())

    def test_a_request_that_loses_the_lock_race_is_credited_nothing(self):
        from django.core.cache import cache
        cache.add(f'essay-seconds-lock:{self.student_user.pk}', 1, 5)
        self.assertEqual(self.clamp(30, NOON), {})

    def test_an_unreachable_cache_credits_nothing(self):
        from unittest import mock
        with mock.patch('apps.admissions.essay_lab.streak.cache.add', side_effect=RuntimeError('down')):
            self.assertEqual(self.clamp(600, NOON), {})

    def test_the_lock_is_released_after_each_report(self):
        self.clamp(30, NOON)
        self.assertEqual(self.clamp(30, NOON + timedelta(seconds=30)), {(date(2026, 11, 8), 'essay_lab'): 30})

    def test_other_pages_are_untouched(self):
        self.assertEqual(self.clamp(600, NOON, page='dashboard'), {(date(2026, 11, 8), 'dashboard'): 600})
