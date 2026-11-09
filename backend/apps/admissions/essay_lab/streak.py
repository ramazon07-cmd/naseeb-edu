"""Writing streak: what a save adds to the student's day, and the streak read from those days.

A day is a Tashkent calendar day (`timezone.localdate`). Words are tracked as a
per-day running net of the text the student has on the page (deleting takes it
back, never below 0) and its peak; "words today" is the peak, so typing and
deleting in a loop cannot add up. What one save may add is capped by how long
the tab has been idle since its previous save, so a pasted block earns about
what typing could have produced. Writing time is the screen-time tracker's
`essay_lab` seconds, added to the day by the track endpoint on the server's
calendar. `goal_met` is kept by the two writes (words and seconds); reading the
streak never writes and never recomputes it.

Raw SQL here: the words upsert (`record_words`) and the seconds upsert
(`record_essay_seconds`), both `INSERT ... ON CONFLICT (user_id, date) DO UPDATE`
with CASE expressions, valid on PostgreSQL and SQLite.
"""

import logging
import math
import re
import time
from datetime import date, datetime, timedelta

from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from ..models import EssayWritingDay
from .doc import block_id, doc_stats

logger = logging.getLogger(__name__)

GOAL_WORDS = 100
GOAL_MINUTES = 10
GOAL_SECONDS = GOAL_MINUTES * 60
MIN_WORDS_WITH_MINUTES = 25
# What a save may add: seconds since the student's previous credited save (any tab or essay)
# times TYPING_WORDS_PER_SECOND (90 words a minute), at most MAX_SAVE_CREDIT, with no minimum,
# so back-to-back saves earn nothing extra. This is a rate limit, not a paste detector: the
# daily 100 words need at least ~67 s of wall-clock time however they arrive. The default
# applies when there is no earlier save to measure from, or the cache is unreachable and the
# tab has none.
TYPING_WORDS_PER_SECOND = 1.5
MAX_SAVE_CREDIT = 60
DEFAULT_SAVE_CREDIT = 30
SECONDS_REPORT_FACTOR = 1.1
# A report dated yesterday keeps that date when it arrives within this many minutes after midnight.
SECONDS_MIDNIGHT_MINUTES = 30
SECONDS_BUCKET_START = 40
SECONDS_BUCKET_MAX = 120
SECONDS_LOCK_TTL = 5
SECONDS_LOCK_TRIES = 3
SECONDS_LOCK_WAIT = 0.005
SECONDS_LAST_REPORT_TTL = 3600
# record_essay_seconds credits a batch dated up to this many days back to its own date.
SECONDS_BACKDATE_DAYS = 7
SCREEN_TIME_PAGE = 'essay_lab'
# The card counts the current and best streak over this much history, so a read stays small.
STREAK_HISTORY_DAYS = 800

FIRE = 'fire'
EMBER = 'ember'
MONTH_RE = re.compile(r'^(\d{4})-(\d{2})$')


def save_credit_cap(previous_save_at, now):
    if previous_save_at is None:
        return DEFAULT_SAVE_CREDIT
    idle = (now - previous_save_at).total_seconds()
    if idle < 0:
        return DEFAULT_SAVE_CREDIT
    return min(MAX_SAVE_CREDIT, math.ceil(idle * TYPING_WORDS_PER_SECOND))


def goal_met(words, seconds):
    return words >= GOAL_WORDS or (seconds >= GOAL_SECONDS and words >= MIN_WORDS_WITH_MINUTES)


def record_words(user, words_before, words_after, now, previous_save_at=None):
    """Fold one save's change in the tab's word count into the student's day.

    One upsert, race-safe: net = max(0, net + delta), peak = max(peak, net) and goal_met,
    all computed by the database. Never raises: a failure here must not fail the save.
    """
    delta = words_after - words_before
    if not delta:
        return
    if delta > 0:
        reachable, last = _swap_last_report(user, 'words', now)
        if reachable and last is not None:
            last = datetime.fromtimestamp(last, now.tzinfo)
            previous_save_at = last if previous_save_at is None else max(previous_save_at, last)
        elif not reachable and previous_save_at is None:
            return
        delta = min(delta, save_credit_cap(previous_save_at, now))
    try:
        table = connection.ops.quote_name(EssayWritingDay._meta.db_table)
        net = f'(CASE WHEN {table}.words_net + %s < 0 THEN 0 ELSE {table}.words_net + %s END)'
        peak = f'(CASE WHEN {net} > {table}.words_peak THEN {net} ELSE {table}.words_peak END)'
        met = (
            f'CASE WHEN {table}.goal_met OR {peak} >= %s'
            f' OR ({table}.active_seconds >= %s AND {peak} >= %s) THEN %s ELSE %s END'
        )
        net_params = [delta, delta]
        peak_params = net_params * 2
        first = max(delta, 0)
        params = [
            user.pk, timezone.localdate(now), first, first, 0, goal_met(first, 0),
            *net_params,
            *peak_params,
            *peak_params, GOAL_WORDS, GOAL_SECONDS, *peak_params, MIN_WORDS_WITH_MINUTES, True, False,
        ]
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO {table} (user_id, date, words_net, words_peak, active_seconds, goal_met)'
                ' VALUES (%s, %s, %s, %s, %s, %s)'
                ' ON CONFLICT (user_id, date) DO UPDATE SET'
                f' words_net = {net}, words_peak = {peak}, goal_met = {met}',
                params,
            )
    except Exception:
        logger.exception('Could not record the writing day for user %s', user.pk)


def _block_words(block):
    return doc_stats({'type': 'doc', 'content': [block]}).word_count


def own_words_delta(stored_doc, ops):
    """Net words the student's own ops v2 add, measured against the blocks they touch.

    Used when the save was merged into a newer version: the document-wide count then also
    holds words other people added since, which are not the student's writing.
    """
    try:
        words = {block_id(block): _block_words(block) for block in stored_doc.get('content') or []}
        delta = 0
        for op in ops:
            if 'ins' in op:
                bid, count = block_id(op['ins']), _block_words(op['ins'])
                delta += count
                words[bid] = count
            elif 'del' in op:
                delta -= words.pop(op['del'], 0)
            elif op['set'] in words:
                count = _block_words(op['block'])
                delta += count - words[op['set']]
                words[op['set']] = count
        return delta
    except Exception:
        logger.exception('Could not measure the words a merged save added')
        return 0


def _take_lock(lock_key):
    # The lock is held for two cache calls, so a short wait makes a lost race (second tab) rare.
    for attempt in range(SECONDS_LOCK_TRIES):
        if cache.add(lock_key, 1, SECONDS_LOCK_TTL):
            return True
        time.sleep(SECONDS_LOCK_WAIT * (attempt + 1))
    return False


def _swap_last_report(user, kind, now):
    """(reachable, previous timestamp or None): reads this user's last `kind` report time and replaces it with now.

    Serialized by a short cache lock. Not reachable means the lock was never obtained or the
    cache failed; callers then credit as little as they safely can.
    """
    cache_key = f'essay-{kind}-last:{user.pk}'
    lock_key = f'essay-{kind}-lock:{user.pk}'
    try:
        if not _take_lock(lock_key):
            return False, None
        try:
            last = cache.get(cache_key)
            cache.set(cache_key, now.timestamp(), SECONDS_LAST_REPORT_TTL)
        finally:
            cache.delete(lock_key)
        return True, last
    except Exception:
        logger.warning('Essay Lab %s credit cannot reach the cache', kind)
        return False, None


def _spend_seconds(user, claimed, now):
    """Take up to `claimed` seconds from this user's Essay Lab time bucket; returns what was granted.

    The bucket refills at 1.1 s per second up to SECONDS_BUCKET_MAX and starts with
    SECONDS_BUCKET_START. Serialized by a short cache lock; a lost race or an unreachable
    cache grants nothing.
    """
    cache_key = f'essay-seconds-bucket:{user.pk}'
    lock_key = f'essay-seconds-lock:{user.pk}'
    try:
        if not _take_lock(lock_key):
            return 0
        try:
            state = cache.get(cache_key)
            if state is None:
                balance = SECONDS_BUCKET_START
            else:
                balance = min(SECONDS_BUCKET_MAX, state[0] + max(0, now.timestamp() - state[1]) * SECONDS_REPORT_FACTOR)
            credit = min(claimed, int(balance))
            cache.set(cache_key, (balance - credit, now.timestamp()), SECONDS_LAST_REPORT_TTL)
        finally:
            cache.delete(lock_key)
        return credit
    except Exception:
        logger.warning('Essay Lab seconds are not credited: the cache is unavailable')
        return 0


def clamp_essay_seconds(user, entries, now):
    """Limit a screen-time batch's Essay Lab seconds to what the wall clock allows.

    A token bucket per student: it refills at 1.1 s per second, holds at most two minutes and
    starts with 40 s (a first report plus some slack for timer jitter), so one inflated batch
    or a burst of requests cannot add more than the time that really passed. A request that
    loses the cache lock race is credited nothing, and so is one that cannot reach the cache.
    The seconds belong to the server's today; only a batch dated yesterday that arrives in the
    first minutes after midnight keeps yesterday (time spent before the day changed). Other
    pages pass through untouched.
    """
    essay = {key: seconds for key, seconds in entries.items() if key[1] == SCREEN_TIME_PAGE}
    if not essay:
        return entries
    local = timezone.localtime(now)
    today = local.date()
    yesterday = today - timedelta(days=1)
    claimed = sum(essay.values())
    allowed = _spend_seconds(user, claimed, now)
    just_after_midnight = local.hour == 0 and local.minute < SECONDS_MIDNIGHT_MINUTES
    early = sum(seconds for (day, _), seconds in essay.items() if day == yesterday) if just_after_midnight else 0
    clamped = {key: seconds for key, seconds in entries.items() if key[1] != SCREEN_TIME_PAGE}
    credit_early = min(early, allowed)
    credit_today = allowed - credit_early
    if credit_early:
        clamped[(yesterday, SCREEN_TIME_PAGE)] = credit_early
    if credit_today:
        clamped[(today, SCREEN_TIME_PAGE)] = credit_today
    return clamped


def record_essay_seconds(user, entries, today):
    """Add a screen-time batch's `essay_lab` seconds to the student's days, in one upsert.

    `entries` is {(date, page): seconds}, credited to that date (a future date counts as
    today; dates older than SECONDS_BACKDATE_DAYS are dropped). The screen-time request
    passes it clamp_essay_seconds' output, which already dates everything to the server's today.
    Does nothing when the batch has no Essay Lab entry. Never raises: the request must not fail because of it.
    """
    by_day = {}
    for (client_date, page), seconds in entries.items():
        if page != SCREEN_TIME_PAGE:
            continue
        day = min(client_date, today)
        if day < today - timedelta(days=SECONDS_BACKDATE_DAYS):
            continue
        by_day[day] = by_day.get(day, 0) + seconds
    if not by_day:
        return
    try:
        table = connection.ops.quote_name(EssayWritingDay._meta.db_table)
        total = f'{table}.active_seconds + EXCLUDED.active_seconds'
        rows = [(user.pk, day, seconds) for day, seconds in by_day.items()]
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO {table} (user_id, date, words_net, words_peak, active_seconds, goal_met) VALUES '
                + ', '.join(['(%s, %s, 0, 0, %s, %s)'] * len(rows))
                + ' ON CONFLICT (user_id, date) DO UPDATE SET'
                f' active_seconds = {total},'
                f' goal_met = CASE WHEN {table}.goal_met OR ({total} >= %s AND {table}.words_peak >= %s)'
                ' THEN %s ELSE %s END',
                [value for row in rows for value in (*row, False)] + [GOAL_SECONDS, MIN_WORDS_WITH_MINUTES, True, False],
            )
    except Exception:
        logger.exception('Could not record Essay Lab time for user %s', user.pk)


def parse_month(value, today):
    """First day of the requested month, or None when it is malformed or after the current month."""
    match = MONTH_RE.match(value or '')
    if not match:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12 or year < 1:
        return None
    first = date(year, month, 1)
    return first if first <= today.replace(day=1) else None


def current_streak(fire_days, today):
    """Length of the run of fire dates ending today (or yesterday while today has none yet)."""
    cursor = today if today in fire_days else today - timedelta(days=1)
    current = 0
    while cursor in fire_days:
        current += 1
        cursor -= timedelta(days=1)
    return current


def streak_numbers(fire_days, today):
    """(current, best) from the set of fire dates.

    Today without a fire day yet does not break the streak: counting starts at yesterday.
    """
    current = current_streak(fire_days, today)
    best = run = 0
    previous = None
    for day in sorted(fire_days):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    return current, best


def build_streak(user, first_of_month):
    """The /streak/ payload from two read-only queries.

    One for the requested month's days plus today's (the progress line), one for the
    dates that met the goal, from which the current and best streaks are counted.
    """
    today = timezone.localdate()
    next_month = (first_of_month + timedelta(days=32)).replace(day=1)
    rows = EssayWritingDay.objects.filter(user=user).filter(
        Q(date__gte=first_of_month, date__lt=next_month) | Q(date=today)
    ).values_list('date', 'words_peak', 'active_seconds', 'goal_met')
    fire_days = set(
        EssayWritingDay.objects.filter(
            user=user, goal_met=True, date__gte=today - timedelta(days=STREAK_HISTORY_DAYS),
        ).order_by('date').values_list('date', flat=True)
    )
    month_days = {}
    words_today = seconds_today = 0
    for day, words, seconds, met in rows:
        if day == today:
            words_today, seconds_today = words, seconds
        if first_of_month <= day < next_month:
            if met:
                month_days[day.isoformat()] = FIRE
            elif words or seconds:
                month_days[day.isoformat()] = EMBER
    current, best = streak_numbers(fire_days, today)
    return {
        'today': today.isoformat(),
        'current': current,
        'best': best,
        'progress': {
            'words': words_today,
            'minutes': seconds_today // 60,
            'goal_met': today in fire_days,
        },
        'goal': {'words': GOAL_WORDS, 'minutes': GOAL_MINUTES, 'min_words': MIN_WORDS_WITH_MINUTES},
        'month': first_of_month.strftime('%Y-%m'),
        'days': month_days,
    }
