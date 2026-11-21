"""One run of the Telegram program import: fetch, find the official page, format, check, add.

Per channel, posts after the stored cursor are handled oldest first. A post that
was added or rejected moves the cursor past it; a post that could not be sent
(AI off, budget used up, gateway down, out of time) leaves the cursor where it
was, so the next run tries it again. A post the gateway fails on twice is skipped.

Most posts link to the channel's own article, not the organiser. Such an article
is opened to find the official link in it; the official page is then read so the
AI can write a short explanation from it.

Logs carry counts and post ids only, never post or page text.
"""
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from urllib.error import URLError

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .. import ai_budget, ai_usage
from ..models import OpportunityProgram, TelegramImportChannel
from . import fetch as fetch_module
from . import formatter, official, rules

logger = logging.getLogger('naseeb.telegram_import')
FEATURE = 'telegram_import'
MAX_AI_ATTEMPTS = 2
MIN_TEXT_CHARS = 40
MAX_CANDIDATES = 8
MAX_PAGES_PER_RUN = 60
# New posts are started until TELEGRAM_IMPORT_TIME_BUDGET_SECONDS; a step that could
# then still be running HARD_EXTRA seconds later is not started (the bot's call must
# end well before gunicorn's 120 s timeout).
HARD_EXTRA = 40
FETCH_ERRORS = (URLError, OSError, ValueError, UnicodeError)


class StopRun(Exception):
    """Nothing more can be done in this run (budget used up, out of time)."""


@dataclass
class RunStats:
    fetched: int = 0
    added: int = 0
    ai_calls: int = 0
    pages_read: int = 0
    rejected: Counter = field(default_factory=Counter)
    stopped: str = ''
    failed_channels: list = field(default_factory=list)

    def summary(self):
        rejected = ' '.join(f'{reason}={count}' for reason, count in sorted(self.rejected.items())) or 'none'
        return (
            f'fetched={self.fetched} added={self.added} ai_calls={self.ai_calls} pages_read={self.pages_read} '
            f'rejected_total={sum(self.rejected.values())} rejected: {rejected}'
            + (f' stopped={self.stopped}' if self.stopped else '')
            + (f' fetch_failed={",".join(self.failed_channels)}' if self.failed_channels else '')
        )


@dataclass
class Run:
    today: object
    catalog: rules.Catalog
    deadline: float
    hard_deadline: float
    fetch: object = None  # (channel, before) -> preview html
    pages: object = None  # url -> (final url, html)
    stats: RunStats = field(default_factory=RunStats)

    def check_time(self):
        if time.monotonic() >= self.deadline:
            raise StopRun('time_budget')

    def need(self, seconds):
        """Stop the run when a step that may take ``seconds`` could end past the hard deadline."""
        if time.monotonic() + seconds > self.hard_deadline:
            raise StopRun('time_budget')

    def read(self, url):
        """The parsed page at ``url``, or None (unreadable). Stops the run at its page limit or time."""
        if self.stats.pages_read >= MAX_PAGES_PER_RUN:
            raise StopRun('page_limit')
        self.need(official.TOTAL_SECONDS)
        self.stats.pages_read += 1
        try:
            return official.load(url, fetch=self.pages)
        except official.PageUnavailable as exc:
            logger.info('telegram_import_page_unreadable host=%s reason=%s', rules.host_of(url), exc)
            return None


def channels():
    names = []
    for name in settings.TELEGRAM_IMPORT_CHANNELS:
        name = name.strip().lstrip('@')
        if fetch_module.valid_channel(name) and name.lower() not in {n.lower() for n in names}:
            names.append(name)
    return names


def _catalog():
    return rules.Catalog(OpportunityProgram.objects.values_list('title', 'provider', 'application_url'))


def _create(post, result, page, catalog):
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
                    'official_page_read': page['url'] if page else '',
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


def candidate_links(run, links):
    """Official links in the post, plus those found on the channel's own article when the post has none."""
    candidates = rules.official_links(links)
    if candidates:
        return candidates[:MAX_CANDIDATES]
    for article in rules.article_links(links)[:1]:
        page = run.read(article)
        if page:
            article_host = rules.host_of(page['url'])
            found = [url for url in rules.official_links(page['links']) if rules.host_of(url) != article_host]
            candidates += [url for url in found if url not in candidates]
    return candidates[:MAX_CANDIDATES]


def official_page(run, candidates):
    """The first candidate page that can be read (two tries at most)."""
    for url in candidates[:2]:
        page = run.read(url)
        if page and page['text']:
            text, _, dropped = rules.prepare_post_text(page['text'])
            if dropped:
                logger.warning('telegram_import_model_directed_lines host=%s lines=%s', rules.host_of(url), dropped)
            return {'url': page['url'], 'title': rules.clean_text(page['title']), 'text': text}
    return None


def _format(run, post, text, candidates, page):
    """Call the gateway once for ``post``; refunds the budget when the call fails."""
    if not ai_budget.consume_job(FEATURE):
        ai_usage.record(FEATURE, None, provider='gateway', status=ai_usage.BUDGET_REFUSED)
        raise StopRun('budget_exhausted')
    run.stats.ai_calls += 1
    ai_usage.begin()
    try:
        result = formatter.format_post(post, text, candidates, run.today, page=page)
    except formatter.FormatterUnavailable:
        ai_budget.refund_job(FEATURE)
        ai_usage.record(FEATURE, None, provider='gateway', status=ai_usage.FAILED)
        raise
    ai_usage.record(FEATURE, None, provider='gateway', status=ai_usage.OK)
    return result


def handle_post(run, post, state):
    """'' when the post was handled (cursor may move past it); 'retry' when it must wait for the next run."""
    stats = run.stats
    source_key = f'telegram:{post.channel.lower()}:{post.id}'
    if OpportunityProgram.objects.filter(source_key=source_key).exists():
        return ''
    text, links, dropped = rules.prepare_post_text(post.text)
    if dropped:
        logger.warning('telegram_import_model_directed_lines channel=%s post=%s lines=%s', post.channel, post.id, dropped)
    # Cheap checks first: no page read and no AI call for a post that could never pass.
    if len(text) < MIN_TEXT_CHARS:
        stats.rejected['not_program'] += 1
        return ''
    candidates = candidate_links(run, links)
    if not candidates:
        stats.rejected['no_official_link'] += 1
        return ''
    page = official_page(run, candidates)
    run.need(settings.TELEGRAM_IMPORT_TIMEOUT_SECONDS + 5)
    try:
        result = _format(run, post, text, candidates, page)
    except formatter.FormatterUnavailable as exc:
        attempts = state.failed_attempts + 1 if state.failed_message_id == post.id else 1
        logger.warning('telegram_import_ai_failed channel=%s post=%s attempt=%s error=%s', post.channel, post.id, attempts, exc)
        if attempts >= MAX_AI_ATTEMPTS:
            stats.rejected['ai_failed'] += 1
            state.failed_message_id, state.failed_attempts = None, 0
            return ''
        state.failed_message_id, state.failed_attempts = post.id, attempts
        return 'retry'
    reason = rules.reject_reason(result, candidates, run.catalog, run.today)
    if reason:
        stats.rejected[reason] += 1
        return ''
    if _create(post, result, page, run.catalog):
        stats.added += 1
    else:
        stats.rejected['duplicate'] += 1
    return ''


def run_channel(run, name):
    stats = run.stats
    state, _ = TelegramImportChannel.objects.get_or_create(channel=name.lower())
    try:
        posts = fetch_module.new_posts(name, state.last_message_id, fetch=run.fetch)
    except FETCH_ERRORS as exc:
        logger.warning('telegram_import_fetch_failed channel=%s error=%s', name, exc.__class__.__name__)
        stats.failed_channels.append(name)
        return
    posts = posts[:max(1, settings.TELEGRAM_IMPORT_MAX_POSTS_PER_CHANNEL)]
    stats.fetched += len(posts)
    added_before, rejected_before = stats.added, sum(stats.rejected.values())
    try:
        for post in posts:
            run.check_time()
            if handle_post(run, post, state) == 'retry':
                break
            state.last_message_id = max(state.last_message_id, post.id)
            if state.failed_message_id == post.id:
                state.failed_message_id, state.failed_attempts = None, 0
            # Saved after every post: a run cut short never redoes (and pays for) finished posts.
            state.save(update_fields=['last_message_id', 'failed_message_id', 'failed_attempts', 'updated_at'])
    finally:
        state.last_run_at = timezone.now()
        state.save(update_fields=['last_message_id', 'failed_message_id', 'failed_attempts', 'last_run_at', 'updated_at'])
        logger.info(
            'telegram_import_channel channel=%s fetched=%s added=%s rejected=%s last_message_id=%s',
            name, len(posts), stats.added - added_before, sum(stats.rejected.values()) - rejected_before,
            state.last_message_id,
        )


def run(fetch=None, pages=None):
    """One import run; returns RunStats.

    ``fetch(channel, before)`` and ``pages(url)`` replace the network in tests. A run
    stops after TELEGRAM_IMPORT_TIME_BUDGET_SECONDS; the rest waits for the next one.
    """
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
    started = time.monotonic()
    budget = max(1, settings.TELEGRAM_IMPORT_TIME_BUDGET_SECONDS)
    current = Run(
        today=timezone.localdate(), catalog=_catalog(), fetch=fetch, pages=pages, stats=stats,
        deadline=started + budget, hard_deadline=started + budget + HARD_EXTRA,
    )
    for name in channels():
        try:
            run_channel(current, name)
        except StopRun as exc:
            stats.stopped = str(exc)
            logger.warning('telegram_import_stopped reason=%s channel=%s', exc, name)
            break
    logger.info('telegram_import_run %s', stats.summary())
    return stats
