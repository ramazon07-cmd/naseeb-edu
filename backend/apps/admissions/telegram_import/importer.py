"""One run of the Telegram program import: fetch, format, check, add.

Per channel, posts after the stored cursor are handled oldest first. A post that
was added or rejected moves the cursor past it; a post that could not be sent
(AI off, budget used up, gateway down) leaves the cursor where it was, so the
next run tries it again. A post the gateway fails on twice is skipped.

Logs carry counts and post ids only, never post text.
"""
import logging
from collections import Counter
from dataclasses import dataclass, field
from urllib.error import URLError

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .. import ai_budget, ai_usage
from ..models import OpportunityProgram, TelegramImportChannel
from . import fetch as fetch_module
from . import formatter, rules

logger = logging.getLogger('naseeb.telegram_import')
FEATURE = 'telegram_import'
MAX_AI_ATTEMPTS = 2
MIN_TEXT_CHARS = 40
FETCH_ERRORS = (URLError, OSError, ValueError, UnicodeError)


class StopRun(Exception):
    """Nothing more can be sent today (budget used up)."""


@dataclass
class RunStats:
    fetched: int = 0
    added: int = 0
    ai_calls: int = 0
    rejected: Counter = field(default_factory=Counter)
    stopped: str = ''
    failed_channels: list = field(default_factory=list)

    def summary(self):
        rejected = ' '.join(f'{reason}={count}' for reason, count in sorted(self.rejected.items())) or 'none'
        return (
            f'fetched={self.fetched} added={self.added} ai_calls={self.ai_calls} '
            f'rejected_total={sum(self.rejected.values())} rejected: {rejected}'
            + (f' stopped={self.stopped}' if self.stopped else '')
            + (f' fetch_failed={",".join(self.failed_channels)}' if self.failed_channels else '')
        )


def channels():
    names = []
    for name in settings.TELEGRAM_IMPORT_CHANNELS:
        name = name.strip().lstrip('@')
        if fetch_module.valid_channel(name) and name.lower() not in {n.lower() for n in names}:
            names.append(name)
    return names


def _catalog():
    return rules.Catalog(OpportunityProgram.objects.values_list('title', 'provider', 'application_url'))


def _create(post, result, catalog):
    fields = {key: result[key] for key in (
        'title', 'provider', 'program_type', 'category', 'country', 'city', 'delivery_mode', 'description',
        'eligible_grades', 'eligible_ages', 'deadline', 'deadline_text', 'start_date', 'end_date', 'fee_usd',
        'scholarship_available', 'aid_details', 'requirements', 'application_url',
    )}
    if fields['start_date'] and fields['end_date'] and fields['start_date'] > fields['end_date']:
        fields['end_date'] = None
    try:
        with transaction.atomic():
            OpportunityProgram.objects.create(
                source_key=f'telegram:{post.channel.lower()}:{post.id}',
                source_url=post.url,
                source_metadata={
                    'origin': 'telegram',
                    'channel': post.channel,
                    'message_id': post.id,
                    'posted_at': post.posted_at,
                    'imported_at': timezone.now().isoformat(timespec='seconds'),
                    'model': settings.TELEGRAM_IMPORT_MODEL,
                    'problems': result['problems'],
                },
                needs_verification=True,
                is_active=settings.TELEGRAM_IMPORT_PUBLISH_IMMEDIATELY,
                **fields,
            )
    except IntegrityError:
        return False
    catalog.add(result['title'], result['provider'], result['application_url'])
    return True


def _format(post, text, links, today, stats):
    """Call the gateway once for ``post``; refunds the budget when the call fails."""
    if not ai_budget.consume_job(FEATURE):
        ai_usage.record(FEATURE, None, provider='gateway', status=ai_usage.BUDGET_REFUSED)
        raise StopRun('budget_exhausted')
    stats.ai_calls += 1
    ai_usage.begin()
    try:
        result = formatter.format_post(post, text, links, today)
    except formatter.FormatterUnavailable:
        ai_budget.refund_job(FEATURE)
        ai_usage.record(FEATURE, None, provider='gateway', status=ai_usage.FAILED)
        raise
    ai_usage.record(FEATURE, None, provider='gateway', status=ai_usage.OK)
    return result


def handle_post(post, state, catalog, today, stats):
    """'' when the post was handled (cursor may move past it); 'retry' when it must wait for the next run."""
    source_key = f'telegram:{post.channel.lower()}:{post.id}'
    if OpportunityProgram.objects.filter(source_key=source_key).exists():
        return ''
    text, links, dropped = rules.prepare_post_text(post.text)
    if dropped:
        logger.warning('telegram_import_model_directed_lines channel=%s post=%s lines=%s', post.channel, post.id, dropped)
    official = rules.official_links(links)
    # Cheap checks first: no AI call for a post that could never pass.
    if len(text) < MIN_TEXT_CHARS:
        stats.rejected['not_program'] += 1
        return ''
    if not official:
        stats.rejected['no_official_link'] += 1
        return ''
    try:
        result = _format(post, text, links, today, stats)
    except formatter.FormatterUnavailable as exc:
        attempts = state.failed_attempts + 1 if state.failed_message_id == post.id else 1
        logger.warning('telegram_import_ai_failed channel=%s post=%s attempt=%s error=%s', post.channel, post.id, attempts, exc)
        if attempts >= MAX_AI_ATTEMPTS:
            stats.rejected['ai_failed'] += 1
            state.failed_message_id, state.failed_attempts = None, 0
            return ''
        state.failed_message_id, state.failed_attempts = post.id, attempts
        return 'retry'
    reason = rules.reject_reason(result, links, catalog, today)
    if reason:
        stats.rejected[reason] += 1
        return ''
    if _create(post, result, catalog):
        stats.added += 1
    else:
        stats.rejected['duplicate'] += 1
    return ''


def run_channel(name, catalog, today, stats, fetch=None):
    state, _ = TelegramImportChannel.objects.get_or_create(channel=name.lower())
    try:
        posts = fetch_module.new_posts(name, state.last_message_id, fetch=fetch)
    except FETCH_ERRORS as exc:
        logger.warning('telegram_import_fetch_failed channel=%s error=%s', name, exc.__class__.__name__)
        stats.failed_channels.append(name)
        return
    posts = posts[:max(1, settings.TELEGRAM_IMPORT_MAX_POSTS_PER_CHANNEL)]
    stats.fetched += len(posts)
    added_before, rejected_before = stats.added, sum(stats.rejected.values())
    try:
        for post in posts:
            if handle_post(post, state, catalog, today, stats) == 'retry':
                break
            state.last_message_id = max(state.last_message_id, post.id)
            if state.failed_message_id == post.id:
                state.failed_message_id, state.failed_attempts = None, 0
    finally:
        state.last_run_at = timezone.now()
        state.save(update_fields=['last_message_id', 'failed_message_id', 'failed_attempts', 'last_run_at', 'updated_at'])
        logger.info(
            'telegram_import_channel channel=%s fetched=%s added=%s rejected=%s last_message_id=%s',
            name, len(posts), stats.added - added_before, sum(stats.rejected.values()) - rejected_before,
            state.last_message_id,
        )


def run(fetch=None):
    """One import run; returns RunStats. ``fetch(channel, before)`` replaces the network in tests."""
    stats = RunStats()
    if not formatter.gateway_configured():
        stats.stopped = 'outbound_ai_off' if not settings.OUTBOUND_AI_ENABLED else 'gateway_not_configured'
        logger.warning(
            'telegram_import_skipped reason=%s: nothing was fetched or sent and no program was added '
            '(set OUTBOUND_AI_ENABLED and AI_GATEWAY_API_KEY to import)', stats.stopped,
        )
        return stats
    if settings.TELEGRAM_IMPORT_DAILY_BUDGET <= 0:
        stats.stopped = 'budget_off'
        logger.warning('telegram_import_skipped reason=budget_off: TELEGRAM_IMPORT_DAILY_BUDGET is 0')
        return stats
    today = timezone.localdate()
    catalog = _catalog()
    for name in channels():
        try:
            run_channel(name, catalog, today, stats, fetch=fetch)
        except StopRun as exc:
            stats.stopped = str(exc)
            logger.warning('telegram_import_stopped reason=%s channel=%s', exc, name)
            break
    logger.info('telegram_import_run %s', stats.summary())
    return stats
