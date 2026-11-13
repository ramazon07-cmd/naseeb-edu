import datetime as dt

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.admissions.meeting_mail import deliver_queued_emails

from . import services
from .digest import build_digest, grouped_students
from .jobs import run_due_jobs
from .permissions import HasServiceKey
from . import student_link
from .students import add_student, find_students, reset_password


def _bad_request():
    return Response({'detail': 'invalid_request'}, status=400)


BIGINT = 2 ** 63


def _chat_id(data):
    value = data.get('chat_id')
    if isinstance(value, bool) or not isinstance(value, int) or not -BIGINT <= value < BIGINT:
        raise services.Refused('invalid_request', 400)
    return value


def _text(data, name, limit):
    value = data.get(name)
    if not isinstance(value, str) or not value or len(value) > limit:
        raise services.Refused('invalid_request', 400)
    return value


class BotView(APIView):
    authentication_classes = []
    permission_classes = [HasServiceKey]
    throttle_classes = []

    def get_authenticate_header(self, request):
        return 'ServiceKey'

    def get_data(self, request):
        data = request.query_params if request.method == 'GET' else request.data
        if not hasattr(data, 'get'):
            raise services.Refused('invalid_request', 400)
        return data

    def get_chat_id(self, request):
        data = self.get_data(request)
        if request.method == 'GET':
            try:
                value = int(data.get('chat_id', ''))
            except (TypeError, ValueError):
                raise services.Refused('invalid_request', 400)
            if not -BIGINT <= value < BIGINT:
                raise services.Refused('invalid_request', 400)
            return value
        return _chat_id(data)

    def handle_exception(self, exc):
        if isinstance(exc, services.Refused):
            return Response({'code': exc.code, **exc.extra}, status=exc.status)
        return super().handle_exception(exc)


class LoginView(BotView):
    def post(self, request):
        data = self.get_data(request)
        telegram_username = data.get('telegram_username')
        if telegram_username is not None and (not isinstance(telegram_username, str) or len(telegram_username) > 100):
            raise services.Refused('invalid_request', 400)
        payload = services.login(
            _chat_id(data), _text(data, 'username', 254), _text(data, 'password', 256), telegram_username,
        )
        return Response(payload)


class ConfirmView(BotView):
    def post(self, request):
        data = self.get_data(request)
        language = data.get('language')
        if language is not None and not isinstance(language, str):
            raise services.Refused('invalid_request', 400)
        link = services.confirm(_chat_id(data), _text(data, 'pending_token', 100), language)
        return Response(services.settings_payload(link))


class StudentsView(BotView):
    def post(self, request):
        link = services.resolve_link(self.get_chat_id(request))
        return Response(grouped_students(link.user))


class DigestView(BotView):
    def post(self, request):
        link = services.resolve_link(self.get_chat_id(request))
        return Response(build_digest(link.user, {**link.prefs}))


class SettingsView(BotView):
    def get(self, request):
        return Response(services.settings_payload(services.resolve_link(self.get_chat_id(request))))

    def put(self, request):
        data = self.get_data(request)
        link = services.resolve_link(_chat_id(data))
        language = data.get('language')
        if language is not None and not (isinstance(language, str) and language in services.LANGUAGES):
            raise services.Refused('invalid_request', 400)
        notify_time = None
        clear_notify_time = 'notify_time' in data and data['notify_time'] is None
        if data.get('notify_time') is not None:
            try:
                notify_time = dt.datetime.strptime(str(data['notify_time']), '%H:%M').time()
            except ValueError:
                raise services.Refused('invalid_request', 400)
        prefs = data.get('prefs')
        if prefs is not None and (
            not isinstance(prefs, dict) or set(prefs) - services.PREF_KEYS
            or not all(isinstance(v, bool) for v in prefs.values())
        ):
            raise services.Refused('invalid_request', 400)
        enabled = data.get('enabled')
        if enabled is not None and not isinstance(enabled, bool):
            raise services.Refused('invalid_request', 400)
        services.update_settings(
            link, language=language, notify_time=notify_time, clear_notify_time=clear_notify_time, prefs=prefs,
            enabled=enabled,
        )
        return Response(services.settings_payload(link))


class AddStudentView(BotView):
    def post(self, request):
        data = self.get_data(request)
        link = services.resolve_link(_chat_id(data))
        return Response(add_student(
            link,
            full_name=_text(data, 'full_name', 300),
            email=_text(data, 'email', 254),
            phone=_text(data, 'phone', 40),
        ), status=201)


class FindStudentsView(BotView):
    def post(self, request):
        data = self.get_data(request)
        link = services.resolve_link(_chat_id(data))
        return Response(find_students(link, _text(data, 'query', 200)))


class ResetPasswordView(BotView):
    def post(self, request):
        data = self.get_data(request)
        link = services.resolve_link(_chat_id(data))
        return Response(reset_password(link, data.get('student_id')))


class ScheduledJobsView(BotView):
    """The bot calls this once an hour instead of separate (paid) cron services.

    It runs the jobs that are due (see jobs.py) the way a cron would: each under its
    advisory lock (two bot instances during a deploy cannot run one twice), recorded
    for the health page.
    """

    def post(self, request):
        return Response({'ok': True, 'ran': run_due_jobs()})


class MeetingEmailsView(BotView):
    """The bot calls this every minute: send queued meeting emails for up to MEETING_EMAIL_SEND_SECONDS.

    Web requests and the reminder job only queue emails (meeting_mail.py); this is the one place
    they are handed to the mail server, outside every user's request. Each row is claimed and
    committed before it is sent, so this must not run inside a transaction.
    """

    def post(self, request):
        return Response(deliver_queued_emails())


class DueView(BotView):
    def post(self, request):
        return Response({'chats': services.due()})


class MarkSentView(BotView):
    def post(self, request):
        data = self.get_data(request)
        try:
            slot_date = dt.date.fromisoformat(str(data.get('slot_date')))
        except ValueError:
            raise services.Refused('invalid_request', 400)
        return Response({'marked': bool(services.mark_sent(_chat_id(data), slot_date))})


class LogoutView(BotView):
    def post(self, request):
        services.unlink(self.get_chat_id(request))
        return Response({'ok': True})


class StudentLinkView(BotView):
    """The student pressed Start on the link from the website: tie this chat to them."""

    def post(self, request):
        data = self.get_data(request)
        language = data.get('language')
        if language is not None and not isinstance(language, str):
            raise services.Refused('invalid_request', 400)
        return Response(student_link.consume_token(_chat_id(data), _text(data, 'token', 100), language))


class WhoAmIView(BotView):
    def post(self, request):
        data = self.get_data(request)
        username = data.get('telegram_username')
        if username is not None and (not isinstance(username, str) or len(username) > 100):
            raise services.Refused('invalid_request', 400)
        return Response({**services.whoami(_chat_id(data), username), 'site_url': student_link.meetings_url()})


class StudentOutboxView(BotView):
    def post(self, request):
        return Response(student_link.pending_messages())


def _int_list(value, limit=500):
    if not isinstance(value, list) or len(value) > limit or not all(
        isinstance(item, int) and not isinstance(item, bool) and -BIGINT <= item < BIGINT for item in value
    ):
        raise services.Refused('invalid_request', 400)
    return value


class StudentOutboxAckView(BotView):
    def post(self, request):
        data = self.get_data(request)
        return Response(student_link.acknowledge(_int_list(data.get('sent', [])), _int_list(data.get('blocked', []))))
