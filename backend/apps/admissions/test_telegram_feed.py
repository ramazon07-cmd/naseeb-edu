import os
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.users.cache_safety import count_hit

from .telegram_feed import PublicPostParser, TelegramFeedView, fetch_posts, page_key, telegram_ssl_context


class TelegramTLSContextTests(SimpleTestCase):
    @patch.dict(os.environ, {}, clear=True)
    @patch('apps.admissions.telegram_feed.sys.platform', 'darwin')
    @patch('apps.admissions.telegram_feed.Path.is_file', return_value=True)
    @patch('apps.admissions.telegram_feed.ssl.create_default_context')
    def test_macos_adds_system_trust(self, create, exists):
        self.assertIs(telegram_ssl_context(), create.return_value)
        create.assert_called_once_with()
        create.return_value.load_verify_locations.assert_called_once_with(cafile='/etc/ssl/cert.pem')

    @patch('apps.admissions.telegram_feed.sys.platform', 'darwin')
    @patch('apps.admissions.telegram_feed.ssl.create_default_context')
    def test_explicit_trust_configuration_is_preserved(self, create):
        for name in ('SSL_CERT_FILE', 'SSL_CERT_DIR'):
            with self.subTest(name=name), patch.dict(os.environ, {name: '/configured/trust'}, clear=True):
                telegram_ssl_context()
                create.return_value.load_verify_locations.assert_not_called()

    @patch('apps.admissions.telegram_feed.sys.platform', 'linux')
    def test_certificate_and_hostname_verification_remain_required(self):
        context = telegram_ssl_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    @patch.dict(os.environ, {}, clear=True)
    @patch('apps.admissions.telegram_feed.sys.platform', 'darwin')
    @patch('apps.admissions.telegram_feed.Path.is_file', return_value=False)
    @patch('apps.admissions.telegram_feed.ssl.create_default_context')
    def test_absent_system_bundle_keeps_default_trust(self, create, exists):
        telegram_ssl_context()
        create.return_value.load_verify_locations.assert_not_called()


class TelegramFeedTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()

    def get(self, query='', authenticated=True):
        request = self.factory.get('/api/telegram-feed/' + query)
        if authenticated:
            force_authenticate(request, user=SimpleNamespace(is_authenticated=True, pk=1))
        return TelegramFeedView.as_view()(request)

    def keep(self, before, posts, cursor, age=0):
        """Cache a page as if it had been fetched ``age`` seconds ago."""
        page = {'channel': 'naseeb_edu', 'posts': posts, 'before': cursor}
        cache.set(page_key(before), {'page': page, 'at': time.time() - age}, 3600)
        return page

    def test_parser_deduplicates_and_ignores_other_channels(self):
        parser = PublicPostParser()
        parser.feed('<a data-before="132"></a><div data-post="naseeb_edu/133"></div>'
                    '<div data-post="naseeb_edu/132"></div><div data-post="naseeb_edu/133"></div>'
                    '<div data-post="other/140"></div><div data-post="naseeb_edu/1?bad"></div>')
        self.assertEqual(parser.ids, {132, 133})
        self.assertEqual(parser.before, 132)

    @patch('apps.admissions.telegram_feed.fetch_posts')
    def test_cached_latest_and_history_are_separate(self, fetch):
        fetch.return_value = {'channel': 'naseeb_edu', 'posts': ['naseeb_edu/132'], 'before': 132}
        self.assertEqual(self.get().status_code, 200)
        self.get()
        fetch.assert_called_once_with(None)
        self.get('?before=132')
        self.assertEqual(fetch.call_count, 2)
        fetch.assert_called_with(132)

    @patch('apps.admissions.telegram_feed.fetch_posts')
    def test_invalid_cursor_never_fetches(self, fetch):
        for cursor in ('-1', '0', '1.5', 'https://localhost', '9' * 13):
            self.assertEqual(self.get('?before=' + cursor).status_code, 400)
        fetch.assert_not_called()

    @patch('apps.admissions.telegram_feed.WAIT_FOR_OTHER', 0)
    @patch('apps.admissions.telegram_feed.fetch_posts', side_effect=URLError('offline'))
    def test_failure_is_not_cached_and_retried_after_a_short_backoff(self, fetch):
        self.assertEqual(self.get().status_code, 503)
        response = self.get()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response['Retry-After'], '3')
        self.assertEqual(fetch.call_count, 1)  # the second request did not ask Telegram again
        cache.delete(page_key(None) + ':lock')  # the backoff has passed
        self.assertEqual(self.get().status_code, 503)
        self.assertEqual(fetch.call_count, 2)

    @patch('apps.admissions.telegram_feed.fetch_posts', side_effect=URLError('offline'))
    def test_an_old_copy_is_served_while_telegram_is_down(self, fetch):
        old = self.keep(None, ['naseeb_edu/151'], 151, age=3600)
        response = self.get()
        self.assertEqual((response.status_code, response.data), (200, old))
        fetch.assert_called_once_with(None)

    @patch('apps.admissions.telegram_feed.fetch_posts')
    def test_one_request_asks_telegram_and_the_others_get_the_old_copy(self, fetch):
        old = self.keep(None, ['naseeb_edu/151'], 151, age=3600)
        count_hit(page_key(None) + ':lock', 10)  # another request is already asking
        self.assertEqual(self.get().data, old)
        fetch.assert_not_called()

    def test_many_cold_requests_at_once_ask_telegram_only_once(self):
        asked = []
        page = {'channel': 'naseeb_edu', 'posts': ['naseeb_edu/151'], 'before': None}

        def slow_fetch(before):
            asked.append(before)
            time.sleep(0.3)
            return page

        with patch('apps.admissions.telegram_feed.fetch_posts', slow_fetch), ThreadPoolExecutor(20) as pool:
            results = list(pool.map(lambda _: self.get().data, range(20)))
        self.assertEqual(asked, [None])
        self.assertEqual(results, [page] * 20)

    @patch('apps.admissions.telegram_feed.time.sleep')
    @patch('apps.admissions.telegram_feed.fetch_posts')
    def test_a_cold_cache_waits_for_the_request_that_is_asking(self, fetch, sleep):
        page = {'channel': 'naseeb_edu', 'posts': ['naseeb_edu/151'], 'before': None}
        count_hit(page_key(None) + ':lock', 10)
        sleep.side_effect = lambda _: cache.set(page_key(None), {'page': page, 'at': time.time()}, 60)
        self.assertEqual(self.get().data, page)
        fetch.assert_not_called()

    @patch('apps.admissions.telegram_feed.fetch_posts')
    def test_the_newest_page_goes_stale_after_a_minute_but_history_does_not(self, fetch):
        fetch.return_value = {'channel': 'naseeb_edu', 'posts': ['naseeb_edu/140'], 'before': None}
        self.keep(None, ['naseeb_edu/151'], 140, age=61)
        self.keep(140, ['naseeb_edu/131'], None, age=61)
        self.get('?before=140')
        fetch.assert_not_called()
        self.get()
        fetch.assert_called_once_with(None)

    @patch('apps.admissions.telegram_feed.HISTORY_PAGES_PER_MINUTE', 2)
    @patch('apps.admissions.telegram_feed.WAIT_FOR_OTHER', 0)
    @patch('apps.admissions.telegram_feed.fetch_posts')
    def test_pages_asked_from_telegram_are_capped_per_minute(self, fetch):
        fetch.return_value = {'channel': 'naseeb_edu', 'posts': ['naseeb_edu/100'], 'before': None}
        self.keep(None, ['naseeb_edu/151'], 140)
        self.assertEqual([self.get(f'?before={cursor}').status_code for cursor in (140, 130, 120)], [200, 200, 503])
        self.assertEqual(fetch.call_count, 2)

    @patch('apps.admissions.telegram_feed.HISTORY_PAGES_PER_MINUTE', 2)
    @patch('apps.admissions.telegram_feed.WAIT_FOR_OTHER', 0)
    @patch('apps.admissions.telegram_feed.fetch_posts')
    def test_older_pages_cannot_use_up_the_newest_pages_budget(self, fetch):
        fetch.return_value = {'channel': 'naseeb_edu', 'posts': ['naseeb_edu/100'], 'before': None}
        self.keep(None, ['naseeb_edu/151'], 140, age=61)
        statuses = [self.get(f'?before={cursor}').status_code for cursor in range(150, 100, -1)]
        self.assertEqual(statuses.count(503), 48)
        self.assertEqual(fetch.call_count, 2)
        fetch.return_value = {'channel': 'naseeb_edu', 'posts': ['naseeb_edu/160'], 'before': 151}
        self.assertEqual(self.get().data['posts'], ['naseeb_edu/160'])
        fetch.assert_called_with(None)

    @patch('apps.admissions.telegram_feed.LATEST_PAGES_PER_MINUTE', 1)
    @patch('apps.admissions.telegram_feed.fetch_posts', side_effect=URLError('offline'))
    def test_the_newest_page_is_capped_too(self, fetch):
        for _ in range(3):
            cache.delete(page_key(None) + ':lock')
            self.get()
        self.assertEqual(fetch.call_count, 1)

    @patch('apps.admissions.telegram_feed.fetch_posts')
    def test_a_made_up_cursor_gets_the_newest_page_and_no_cache_entry(self, fetch):
        latest = self.keep(None, ['naseeb_edu/151'], 140)
        response = self.get('?before=999999999999')
        self.assertEqual((response.status_code, response.data), (200, latest))
        fetch.assert_not_called()
        self.assertIsNone(cache.get(page_key(999999999999)))

    @override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': {
        **settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'], 'telegram_feed': '2/minute'}})
    @patch('apps.admissions.telegram_feed.fetch_posts')
    def test_a_user_is_rate_limited(self, fetch):
        self.keep(None, ['naseeb_edu/151'], None)
        self.assertEqual([self.get().status_code for _ in range(3)], [200, 200, 429])

    def test_authentication_required(self):
        self.assertIn(self.get(authenticated=False).status_code, (401, 403))

    @patch('apps.admissions.telegram_feed.build_opener')
    def test_history_uses_fixed_host_and_monotonic_cursor(self, opener):
        opener.return_value.open.return_value.__enter__.return_value.read.return_value = (
            b'<a data-before="150"></a><div data-post="naseeb_edu/132"></div>'
            b'<div data-post="naseeb_edu/140"></div>')
        result = fetch_posts(140)
        self.assertEqual(result['posts'], ['naseeb_edu/132'])
        self.assertIsNone(result['before'])
        self.assertEqual(opener.return_value.open.call_args.args[0].full_url,
                         'https://t.me/s/naseeb_edu?before=140')
