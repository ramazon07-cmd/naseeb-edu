"""Answers the assistant can give from the database alone (no AI call, 0 tokens).

``answer_locally`` recognises a small set of plain questions in English,
Uzbek (Latin) and Russian and answers them from the caller's own data, with
the same scoping as ``build_role_context``: a student sees only their own
records, a counselor only aggregate counts (never a student's name or any
record text). It returns ``None`` whenever it is not sure, so the question
goes to the AI instead: a wrong canned answer is worse than a paid one.
"""
import re
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from apps.users.models import User
from .models import Application, RoadmapMission, StudentProfile, Task
from .progress import OPEN_TASK_STATUSES, late_tasks, summarize_progress
from .scoping import active_visible_students

LANGUAGES = ('uz', 'ru', 'en')
MAX_QUESTION_CHARS = 120

_APOSTROPHES = str.maketrans({c: "'" for c in '‘’ʻʼ`´′ʹ'})


def _normalize(text):
    return re.sub(r'\s+', ' ', str(text).translate(_APOSTROPHES).casefold().replace('ё', 'е')).strip()


def _has(pattern, text):
    return re.search(pattern, text) is not None


# Questions about writing, improving or planning go to the AI, never here.
_NOT_A_LOOKUP = (
    r'essay|insho|эссе|сочинен|\bwrite\b|\byoz(?:ib|ing|ish)|напиш|improve|\bplan\b|\breja|\bплан|advice|\btips?\b|'
    r'maslahat|yaxshila|улучш|\bsovet|совет|help me|yordam ber|помоги|\bhow to\b|\bhow can\b|how do i (?:improve|write|get)'
)
_NOT_A_LOOKUP_EXCEPT_ESSAY = _NOT_A_LOOKUP.replace('essay|insho|эссе|', '')

# A lookup of the user's OWN data needs a self marker (my / mening, -im endings / мой, у меня) or must be
# one of the exact suggestion questions below. "Deadline for MIT?" or "How are universities ranked?"
# are general questions and go to the AI.
_SELF = (
    r"\bmy\b|\bmine\b|\bmening\b|\bмо[йяеи]\w*|\bу меня\b|\bменя\b|\bмне\b|"
    r"\b[a-z']{3,}(?:im|larim|imiz|ingiz|imdagi|amdagi|imni|imga|imda)\b"
)
_CHIPS = frozenset((
    'which tasks are overdue', 'how many tasks are overdue', 'how many students are at risk',
    'qaysi vazifalarim kechikkan', 'nechta vazifa kechikkan', "nechta o'quvchi xavf ostida",
    'какие задания просрочены', 'сколько заданий просрочено', 'сколько учеников в зоне риска',
))
_SOON = r'\bnext\b|upcoming|nearest|soonest|yaqin|keyingi|navbatdagi|ближайш|следующ'
_MAX_WHERE_WORDS = 6
_WHERE_INFO = r"info|about|haqida|ma'lumot|информац"
_APP_WORDS = r'application|ariza|заявк|hujjat topshir|universit|университет'
_OVERDUE = r'overdue|past due|kechik|muddati o\'t|o\'tkazib yubor|просроч'
_DEADLINE = (
    r'deadline|\bdue\b|muddat|\bсрок|дедлайн|upcoming tasks?|keyingi (?:vazifa|topshiriq)|'
    r'ближайш\w* (?:задач|задани)'
)
_ROADMAP = r'roadmap|yo\'l ?xarita|yol ?xarita|дорожн\w* карт|\bmission|missiya|миссия'
_NEXT = r'\bnext\b|current|keyingi|navbatdagi|qadam|\bstep\b|следующ|текущ|шаг|which|qaysi'
_APP_STATUS = (
    r'status|how many|how are|going|ketyapti|holat|qancha|nechta|сколько|как идут|статус|как дела|идут'
)
_HOW_TO_APPLY = r'how to|how do|how can|qanday topshir|qanday qil|как подать|как оформ|как сдел'
_PROGRESS = (
    r'\bmy (?:overall |journey )?progress\b|progressim|taraqqiyotim|mening (?:progress|taraqqiyot)|'
    r'\bмой (?:общий )?прогресс'
)
_AT_RISK = r'at[- ]risk|xavf ostida|xavfli|в зоне риска|под угрозой'
_PEOPLE = r'student|o\'quvchi|talaba|ученик|студент|учащ'
_MEETING = r'meeting|uchrashuv|встреч|appointment'
_BOOK = r'\bbook|schedule|set up|arrange|band qil|bron|yozil|записа|назнач|заброни'
_ESSAY_LAB = r'essay[- ]?lab|insho laborator|эссе[- ]?лаб|лаборатори\w* эссе'
_HOW = r'\bwhere\b|\bhow\b|find|open|\buse\b|qayerda|qaerda|qanday|ochish|foydalan|где|как|открыть|использ'
_WHERE = r'\bwhere\b|qayerda|qaerda|где'
_PAGES = (
    ('tasks', r'\btasks?\b|vazifa|topshiriq|задач|задани'),
    ('roadmap', _ROADMAP),
    ('applications', r'application|ariza|заявк|hujjat topshir'),
    ('documents', r'document|hujjat|документ'),
    ('messages', r'message|xabar|сообщен'),
    ('meetings', _MEETING),
)


def _detect(text):
    """The one intent this question is about, or ``None`` when it is unclear or not a plain lookup."""
    if not text or len(text) > MAX_QUESTION_CHARS:
        return None
    lookup = not _has(_NOT_A_LOOKUP, text)
    found = set()
    app = _has(_APP_WORDS, text)
    own = _has(_SELF, text) or text.rstrip('?!. ') in _CHIPS

    if lookup and own:
        if _has(_OVERDUE, text) and not app:
            found.add('overdue')
        elif _has(_DEADLINE, text) and _has(_SOON, text):
            found.add('app_deadline' if app else 'deadline')
        if _has(_ROADMAP, text) and _has(_NEXT, text):
            found.add('roadmap')
        if app and _has(_APP_STATUS, text) and not _has(_HOW_TO_APPLY, text) and not _has(_DEADLINE, text):
            found.add('applications')
        if _has(_PROGRESS, text):
            found.add('progress')
        if _has(_AT_RISK, text) and _has(_PEOPLE + r'|how many|nechta|сколько', text):
            found.add('at_risk')
    if _has(_MEETING, text) and _has(_BOOK, text) and not _has(_NOT_A_LOOKUP_EXCEPT_ESSAY, text):
        found.add('help_meeting')
    if _has(_ESSAY_LAB, text) and _has(_HOW, text) and not _has(_NOT_A_LOOKUP_EXCEPT_ESSAY, text):
        found.add('help_essay_lab')
    if (_has(_WHERE, text) and len(text.split()) <= _MAX_WHERE_WORDS and not _has(_WHERE_INFO, text)
            and not _has(_ESSAY_LAB, text) and not _has(_NOT_A_LOOKUP_EXCEPT_ESSAY, text)):
        pages = {name for name, pattern in _PAGES if _has(pattern, text)}
        if 'documents' in pages and 'applications' in pages:
            pages.discard('documents')
        if len(pages) == 1:
            found.add('where_' + pages.pop())
    return found.pop() if len(found) == 1 else None


# -- wording ---------------------------------------------------------------

_T = {
    'none_tasks': {
        'en': 'You have no open tasks right now.',
        'uz': 'Hozir sizda ochiq vazifa yo\'q.',
        'ru': 'Сейчас у вас нет открытых заданий.',
    },
    'next_tasks': {
        'en': 'Your next tasks by deadline:',
        'uz': 'Muddati bo\'yicha eng yaqin vazifalaringiz:',
        'ru': 'Ближайшие задания по сроку:',
    },
    'no_overdue': {
        'en': 'You have no overdue tasks.',
        'uz': 'Kechikkan vazifalaringiz yo\'q.',
        'ru': 'Просроченных заданий нет.',
    },
    'overdue': {
        'en': 'You have {n} overdue task(s):',
        'uz': 'Sizda {n} ta kechikkan vazifa bor:',
        'ru': 'Просроченных заданий: {n}:',
    },
    'no_mission': {
        'en': 'You have no open roadmap missions.',
        'uz': 'Yo\'l xaritangizda ochiq missiya yo\'q.',
        'ru': 'Открытых миссий на дорожной карте нет.',
    },
    'mission': {
        'en': 'Your next roadmap mission:',
        'uz': 'Yo\'l xaritangizdagi keyingi missiya:',
        'ru': 'Следующая миссия на вашей дорожной карте:',
    },
    'no_apps': {
        'en': 'You have no applications yet.',
        'uz': 'Sizda hali arizalar yo\'q.',
        'ru': 'У вас пока нет заявок.',
    },
    'apps': {
        'en': 'Your applications ({n} in total):',
        'uz': 'Arizalaringiz (jami {n} ta):',
        'ru': 'Ваши заявки (всего {n}):',
    },
    'no_app_deadline': {
        'en': 'None of your applications has an upcoming deadline.',
        'uz': 'Arizalaringizning hech birida yaqin muddat yo\'q.',
        'ru': 'У ваших заявок нет ближайших сроков.',
    },
    'app_deadline': {
        'en': 'Your next application deadline:',
        'uz': 'Eng yaqin ariza muddati:',
        'ru': 'Ближайший срок по заявкам:',
    },
    'progress': {
        'en': 'Your journey progress is {n}%.',
        'uz': 'Sizning umumiy progressingiz {n}%.',
        'ru': 'Ваш общий прогресс: {n}%.',
    },
    'c_overdue': {
        'en': '{n} overdue task(s) across your students.',
        'uz': 'O\'quvchilaringizda jami {n} ta kechikkan vazifa bor.',
        'ru': 'Просроченных заданий у ваших учеников: {n}.',
    },
    'c_deadline': {
        'en': '{n} open task(s) are due within the next 7 days across your students.',
        'uz': 'O\'quvchilaringizda keyingi 7 kunda muddati tugaydigan {n} ta ochiq vazifa bor.',
        'ru': 'В ближайшие 7 дней срок по {n} открытым заданиям ваших учеников.',
    },
    'c_risk': {
        'en': '{n} of {total} students are at risk.',
        'uz': '{total} ta o\'quvchidan {n} tasi xavf ostida.',
        'ru': 'В зоне риска {n} из {total} учеников.',
    },
    'c_apps': {
        'en': 'Applications across your students ({n} in total):',
        'uz': 'O\'quvchilaringizning arizalari (jami {n} ta):',
        'ru': 'Заявки ваших учеников (всего {n}):',
    },
    'help_meeting_student': {
        'en': 'Open Meetings in the sidebar, choose a counselor, pick a free time slot and confirm. You will see the booking under Meetings.',
        'uz': 'Yon paneldagi "Uchrashuvlar" bo\'limini oching, maslahatchini tanlang, bo\'sh vaqtni belgilang va tasdiqlang. Bron "Uchrashuvlar"da ko\'rinadi.',
        'ru': 'Откройте «Встречи» в боковом меню, выберите консультанта, свободное время и подтвердите. Запись появится в разделе «Встречи».',
    },
    'help_meeting_counselor': {
        'en': 'Open Meetings in the sidebar to set your weekly hours and manage the bookings students make.',
        'uz': 'Yon paneldagi "Uchrashuvlar" bo\'limida haftalik vaqtingizni belgilang va o\'quvchilar bronlarini boshqaring.',
        'ru': 'В разделе «Встречи» бокового меню задайте свои часы приёма и управляйте записями учеников.',
    },
    'help_essay_lab': {
        'en': 'Essay Lab is in the sidebar. Start a new essay or open a draft, write in the editor and ask for feedback.',
        'uz': '"Insholar laboratoriyasi" yon panelda. Yangi insho boshlang yoki qoralamani oching, muharrirda yozing va fikr so\'rang.',
        'ru': '«Лаборатория эссе» находится в боковом меню. Создайте новое эссе или откройте черновик, пишите в редакторе и запросите отзыв.',
    },
    'where': {
        'en': 'You can find it under {page} in the sidebar.',
        'uz': 'Uni yon paneldagi "{page}" bo\'limidan topasiz.',
        'ru': 'Это раздел «{page}» в боковом меню.',
    },
}
_PAGE_NAMES = {
    'tasks': {'en': 'Tasks', 'uz': 'Vazifalar', 'ru': 'Задания'},
    'roadmap': {'en': 'Roadmap', 'uz': 'Yo‘l xaritasi', 'ru': 'План'},
    'applications': {'en': 'Applications', 'uz': 'Arizalar', 'ru': 'Заявки'},
    'documents': {'en': 'Documents', 'uz': 'Hujjatlar', 'ru': 'Документы'},
    'messages': {'en': 'Messages', 'uz': 'Xabarlar', 'ru': 'Сообщения'},
    'meetings': {'en': 'Meetings', 'uz': 'Uchrashuvlar', 'ru': 'Встречи'},
}
_STATUS_NAMES = {
    'researching': {'en': 'researching', 'uz': 'o\'rganilmoqda', 'ru': 'изучаются'},
    'shortlisted': {'en': 'shortlisted', 'uz': 'tanlab olingan', 'ru': 'в шорт-листе'},
    'applying': {'en': 'applying', 'uz': 'topshirilmoqda', 'ru': 'подаются'},
    'submitted': {'en': 'submitted', 'uz': 'topshirilgan', 'ru': 'поданы'},
    'accepted': {'en': 'accepted', 'uz': 'qabul qilingan', 'ru': 'приняты'},
    'rejected': {'en': 'rejected', 'uz': 'rad etilgan', 'ru': 'отклонены'},
    'waitlisted': {'en': 'waitlisted', 'uz': 'kutish ro\'yxatida', 'ru': 'в листе ожидания'},
}


_MONTHS = {
    'en': ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'),
    'uz': ('yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr'),
    'ru': ('янв.', 'февр.', 'марта', 'апр.', 'мая', 'июня', 'июля', 'авг.', 'сент.', 'окт.', 'нояб.', 'дек.'),
}


def _plural_en(text, n):
    # English templates write "task(s)" / "day(s)"; pick the right form for n.
    return text.replace('(s)', '' if n == 1 else 's')


def _t(key, lang, **values):
    text = _T[key][lang].format(**values)
    return _plural_en(text, values['n']) if lang == 'en' and isinstance(values.get('n'), int) else text


def _date(day, lang):
    month = _MONTHS[lang][day.month - 1]
    return f'{day.day}-{month}' if lang == 'uz' else f'{day.day} {month}'


def _when(due, today, lang):
    days = (due - today).days
    if days < 0:
        text = {'en': _plural_en(f'{-days} day(s) overdue', -days), 'uz': f'{-days} kun kechikkan', 'ru': f'просрочено на {-days} дн.'}
    elif days == 0:
        text = {'en': 'today', 'uz': 'bugun', 'ru': 'сегодня'}
    elif days == 1:
        text = {'en': 'tomorrow', 'uz': 'ertaga', 'ru': 'завтра'}
    else:
        text = {'en': f'in {days} days', 'uz': f'{days} kundan keyin', 'ru': f'через {days} дн.'}
    return f'{_date(due, lang)}, {text[lang]}'


def _status_lines(counts, lang):
    order = ('researching', 'shortlisted', 'applying', 'submitted', 'accepted', 'rejected', 'waitlisted')
    return '\n'.join(f'- {_STATUS_NAMES[s][lang]}: {counts[s]}' for s in order if counts.get(s))


def _counts(queryset, field='status'):
    return dict(queryset.order_by().values_list(field).annotate(total=Count('pk')))


# -- answers ---------------------------------------------------------------

def _student_answer(student, intent, lang):
    today = timezone.localdate()
    if intent in ('deadline', 'overdue'):
        tasks = Task.objects.filter(student=student)
        if intent == 'overdue':
            rows = tasks.filter(late_tasks(today))
            total = rows.count()
            if not total:
                return _t('no_overdue', lang)
            head = _t('overdue', lang, n=total)
        else:
            rows = tasks.filter(status__in=OPEN_TASK_STATUSES)
            if not rows.exists():
                return _t('none_tasks', lang)
            head = _t('next_tasks', lang)
        lines = [f'- {title} ({_when(due, today, lang)})' for title, due in rows.order_by('due_date').values_list('title', 'due_date')[:3]]
        return head + '\n' + '\n'.join(lines)
    if intent == 'roadmap':
        # Only missions the student can act on: submitted ones are waiting for approval.
        mission = (
            RoadmapMission.objects.filter(student=student)
            .exclude(status__in=(RoadmapMission.Status.COMPLETED, RoadmapMission.Status.SUBMITTED))
            .order_by('level', 'sequence', 'due_date').values('title', 'due_date').first()
        )
        if not mission:
            return _t('no_mission', lang)
        line = f'- {mission["title"]}'
        if mission['due_date']:
            line += f' ({_when(mission["due_date"], today, lang)})'
        return _t('mission', lang) + '\n' + line
    if intent == 'applications':
        counts = _counts(Application.objects.filter(student=student))
        if not sum(counts.values()):
            return _t('no_apps', lang)
        return _t('apps', lang, n=sum(counts.values())) + '\n' + _status_lines(counts, lang)
    if intent == 'app_deadline':
        row = (
            Application.objects.filter(student=student, deadline__gte=today)
            .exclude(status__in=('submitted', 'accepted', 'rejected', 'waitlisted'))
            .order_by('deadline').values('university__name', 'deadline').first()
        )
        if not row:
            return _t('no_app_deadline', lang)
        return _t('app_deadline', lang) + f'\n- {row["university__name"]} ({_when(row["deadline"], today, lang)})'
    if intent == 'progress':
        return _t('progress', lang, n=student.journey_progress_percent)
    return None


def _counselor_answer(user, intent, lang):
    students = active_visible_students(user)
    today = timezone.localdate()
    if intent == 'overdue':
        return _t('c_overdue', lang, n=Task.objects.filter(student__in=students).filter(late_tasks(today)).count())
    if intent == 'deadline':
        soon = Task.objects.filter(
            student__in=students, status__in=OPEN_TASK_STATUSES,
            due_date__gte=today, due_date__lte=today + timedelta(days=7),
        )
        return _t('c_deadline', lang, n=soon.count())
    if intent == 'at_risk':
        summary = summarize_progress(students)
        return _t('c_risk', lang, n=summary['students_at_risk'], total=summary['students_total'])
    if intent == 'applications':
        counts = _counts(Application.objects.filter(student__in=students))
        if not sum(counts.values()):
            return _t('no_apps', lang)
        return _t('c_apps', lang, n=sum(counts.values())) + '\n' + _status_lines(counts, lang)
    return None


def answer_locally(user, message, language=None):
    """A short templated answer from the database, or ``None`` to let the AI handle it."""
    lang = language
    if lang not in LANGUAGES:
        return None  # unknown language: let the AI answer in the user's own
    if user.role not in (User.Role.STUDENT, User.Role.COUNSELOR):
        return None
    intent = _detect(_normalize(message))
    if intent is None:
        return None
    is_student = user.role == User.Role.STUDENT
    if intent == 'help_meeting':
        return _t('help_meeting_student' if is_student else 'help_meeting_counselor', lang)
    if intent == 'help_essay_lab':
        return _t('help_essay_lab', lang) if is_student else None
    if intent.startswith('where_'):
        page = intent[6:]
        if not is_student and page not in ('messages', 'meetings'):
            return None
        return _t('where', lang, page=_PAGE_NAMES[page][lang])
    if not is_student:
        return _counselor_answer(user, intent, lang)
    if intent == 'at_risk':
        return None
    try:
        student = StudentProfile.objects.get(user=user)
    except StudentProfile.DoesNotExist:
        return None
    return _student_answer(student, intent, lang)
