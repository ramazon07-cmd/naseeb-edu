"""Seed a throwaway PostgreSQL database with a realistic load-test dataset.

DEV ONLY. It bulk-inserts thousands of accounts that share one known password,
so it refuses to run unless every guard below passes:

* not on a hosted runtime (``RENDER`` unset),
* ``DATABASE_URL`` points at localhost and the database name starts with
  ``loadtest``,
* the database has no users yet (a fresh ``migrate``).

Usage, from the repository root::

    createdb -h 127.0.0.1 -p 55432 -U postgres loadtest
    export DATABASE_URL=postgres://postgres@127.0.0.1:55432/loadtest  # plus the usual env
    (cd backend && python manage.py migrate --noinput)
    python scripts/loadtest/seed.py --students 5000 --schools 20 --out scripts/loadtest/.accounts

It writes one ``<role>.csv`` (``username,password``) per role into ``--out``
for the Locust file to log in with.

Rows are bulk-inserted for speed, but every value that has a production code
path comes from it: schools are created through the ORM (so each gets its
plan), profiles take ``student_profile_defaults``, the Level 1 roadmap comes
from ``extend_level_one_roadmap``, XP uses the approval amounts, and essay
documents pass ``validate_doc`` before ``derive``. ``seed()`` is exercised at a
tiny size by the backend test suite so the dataset cannot drift from the real
data format.
"""
import argparse
import csv
import os
import random
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}
PASSWORD = 'Loadtest-Pass-2026!'
BATCH = 2000


def guard():
    if os.environ.get('RENDER'):
        sys.exit('Refusing to seed on a hosted runtime.')
    url = urlparse(os.environ.get('DATABASE_URL', ''))
    name = url.path.lstrip('/')
    if url.scheme not in {'postgres', 'postgresql'} or url.hostname not in LOCAL_HOSTS or not name.startswith('loadtest'):
        sys.exit('DATABASE_URL must be a local PostgreSQL database whose name starts with "loadtest".')


def setup_django():
    sys.path.insert(0, str(BACKEND))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    import django

    django.setup()


FIRST = ['Aziz', 'Madina', 'Jasur', 'Dilnoza', 'Timur', 'Nodira', 'Bekzod', 'Malika', 'Sardor', 'Shahzoda',
         'Otabek', 'Kamola', 'Rustam', 'Zarina', 'Farrux', 'Laylo', 'Javohir', 'Sevara', 'Ulugbek', 'Gulnora']
LAST = ['Karimov', 'Rashidova', 'Tursunov', 'Yusupova', 'Aliev', 'Nazarova', 'Saidov', 'Qodirova', 'Ergashev',
        'Mirzaeva', 'Xolmatov', 'Abdullaeva', 'Rahimov', 'Usmonova', 'Sharipov']
WORDS = ('grandmother kitchen market chemistry robot notebook village river winter football library laptop '
         'mathematics olympiad volunteer tutoring brother responsibility curiosity failure patience bridge '
         'language Samarkand garden physics experiment question community project mentor scholarship dream '
         'engineering medicine discipline morning bus journey window teacher lesson music violin courage').split()
TASK_TITLES = ['Draft personal statement', 'Book IELTS test', 'Request transcript', 'Shortlist universities',
               'Finish SAT practice test', 'Update activities list', 'Ask for recommendation', 'Scholarship research',
               'Prepare interview answers', 'Translate documents', 'Write supplement essay', 'Review CV']
MAJORS = ['Computer Science', 'Economics', 'Medicine', 'Mechanical Engineering', 'Data Science', 'Business',
          'International Relations', 'Architecture', 'Biology', 'Mathematics']
COUNTRIES = ['United States', 'United Kingdom', 'Canada', 'Germany', 'South Korea', 'Japan', 'Turkey', 'Italy',
             'Singapore', 'Hong Kong', 'Netherlands', 'Australia']
PAGES = ['dashboard', 'essay_lab', 'roadmap', 'applications', 'messages', 'student_center', 'college_search']


def sentence(rng, words=14):
    body = ' '.join(rng.choice(WORDS) for _ in range(words))
    return body[0].upper() + body[1:] + '.'


def paragraph(rng, sentences=5):
    return ' '.join(sentence(rng, rng.randint(9, 18)) for _ in range(sentences))


def rich_doc(rng, target_words=600):
    """A ProseMirror doc like one the Essay Lab editor saves: headings, marks, lists."""
    content = [{'type': 'heading', 'attrs': {'level': 1}, 'content': [{'type': 'text', 'text': 'My story'}]}]
    words = 0
    while words < target_words:
        text = paragraph(rng, rng.randint(3, 6))
        words += len(text.split())
        split = text.find(' ', len(text) // 3)
        inline = [
            {'type': 'text', 'text': text[:split + 1]},
            {'type': 'text', 'text': text[split + 1:split + 40], 'marks': [{'type': rng.choice(['bold', 'italic'])}]},
            {'type': 'text', 'text': text[split + 40:]},
        ]
        content.append({'type': 'paragraph', 'content': [node for node in inline if node['text']]})
        if rng.random() < 0.15:
            content.append({'type': 'bulletList', 'content': [
                {'type': 'listItem', 'content': [{'type': 'paragraph', 'content': [
                    {'type': 'text', 'text': sentence(rng, 8)}]}]}
                for _ in range(3)
            ]})
    return {'type': 'doc', 'content': content}


def bulk(model, rows):
    created = []
    for start in range(0, len(rows), BATCH):
        created.extend(model.objects.bulk_create(rows[start:start + BATCH]))
    return created


def seed(*, student_count, school_count, rng_seed):
    """Insert the dataset into the configured database; returns {role: [usernames]}."""
    from django.contrib.auth.hashers import make_password
    from django.db import connection, transaction
    from django.utils import timezone

    from apps.admissions.essay_lab.doc import doc_stats, validate_doc
    from apps.admissions.essay_lab.tabs import FIRST_TAB_TITLE
    from apps.admissions.models import (
        Achievement, Activity, ActivityLog, Application, Booking, ChallengeAttempt, ChannelMembership,
        ChannelMessage, CounselorRoadmap, CounselorRoadmapMission, CounselorRoadmapTemplate,
        CounselorRoadmapTemplateMission, Document, Essay, EssayCheckpoint, EssayDepthCheck, EssayFolder, EssayTab,
        EssayRevision, Honor, Internship, MessageChannel, Notification, ParentStudentLink, ProgramService,
        Project, RecommendationLetter, Research, RoadmapMission, Scholarship, School, ScreenTimeDaily,
        StudentProfile, SupportTicket, Task, University, XPTransaction,
    )
    from apps.admissions.services import (
        ROADMAP_APPROVAL_XP, TASK_XP_BY_PRIORITY, extend_level_one_roadmap, student_profile_defaults,
    )
    from apps.users.models import User

    rng = random.Random(rng_seed)
    now = timezone.now()
    today = timezone.localdate()
    password_hash = make_password(PASSWORD)
    accounts = {role: [] for role in ('student', 'counselor', 'organization', 'teacher', 'parent', 'admin')}

    def user(username, role, school=None, **extra):
        accounts[role].append(username)
        return User(
            username=username, email=f'{username}@loadtest.invalid', password=password_hash, role=role,
            first_name=rng.choice(FIRST), last_name=rng.choice(LAST), school=school, **extra,
        )

    with transaction.atomic():
        from django.core.management import call_command
        call_command('load_university_catalog', verbosity=0)
        regions = School.Region.values
        # One create() per school: the post_save signal gives every workspace its plan.
        schools = [
            School.objects.create(
                name=f'Loadtest Lyceum {index + 1}', code=f'loadtest-{index + 1}', region=regions[index % len(regions)],
            )
            for index in range(school_count)
        ]
        school_by_id = {school.pk: school for school in schools}
        universities = list(University.objects.all())
        universities += bulk(University, [
            University(
                name=f'{rng.choice(["Northern", "Eastern", "Royal", "National", "Technical", "Global"])} University {index}',
                country=rng.choice(COUNTRIES), city='City', ranking=rng.randint(20, 900),
                acceptance_rate=rng.randint(5, 80), tuition_usd=rng.randint(3000, 60000),
                popular_majors=','.join(rng.sample(MAJORS, 3)),
                application_deadline=today + timedelta(days=rng.randint(30, 200)),
            )
            for index in range(150 - len(universities))
        ])
        bulk(Scholarship, [
            Scholarship(
                title=f'Scholarship {index}', provider='Foundation', scholarship_type='merit',
                university=rng.choice(universities) if index % 2 else None,
                amount_usd=rng.randint(1000, 40000), deadline=today + timedelta(days=rng.randint(10, 300)),
            )
            for index in range(60)
        ])

        staff = [user('lt-admin-1', 'admin', is_staff=True), user('lt-admin-2', 'admin', is_staff=True)]
        per_school = {}
        for number, school in enumerate(schools, start=1):
            counselors = [user(f'lt-c-{number}-{i}', 'counselor', school) for i in range(1, 6)]
            teachers = [user(f'lt-t-{number}-{i}', 'teacher', school) for i in range(1, 5)]
            organization = user(f'lt-o-{number}', 'organization', school)
            per_school[school.pk] = {'counselors': counselors, 'teachers': teachers, 'organization': organization}
            staff += counselors + teachers + [organization]
        bulk(User, staff)
        admin = User.objects.get(username='lt-admin-1')
        for school in schools:
            group = per_school[school.pk]
            names = [u.username for u in group['counselors'] + group['teachers'] + [group['organization']]]
            loaded = {u.username: u for u in User.objects.filter(username__in=names)}
            group['counselors'] = [loaded[u.username] for u in group['counselors']]
            group['teachers'] = [loaded[u.username] for u in group['teachers']]
            group['organization'] = loaded[group['organization'].username]

        student_users = []
        for index in range(1, student_count + 1):
            school = schools[(index - 1) % len(schools)]
            student_users.append(user(f'lt-s-{index}', 'student', school))
        student_users = bulk(User, student_users)
        student_users = list(User.objects.filter(role='student').order_by('id'))

        profiles = []
        for index, account in enumerate(student_users):
            group = per_school[account.school_id]
            gpa = round(rng.uniform(3.0, 5.0), 2)
            profiles.append(StudentProfile(
                user=account, **student_profile_defaults(school_by_id[account.school_id]),
                assigned_counselor=group['counselors'][index // len(schools) % 5],
                grade=rng.choice(['9', '10', '11']), gpa=gpa, gpa_scale=5,
                ielts_score=rng.choice([None, 5.5, 6.0, 6.5, 7.0, 7.5]), sat_score=rng.choice([None, 1200, 1350, 1480]),
                target_major=rng.choice(MAJORS), target_countries=', '.join(rng.sample(COUNTRIES, 2)),
                budget_usd=rng.randint(5000, 50000),
                profile_completed_at=now, application_profile={'interests': rng.sample(MAJORS, 2)},
                notes=paragraph(rng, 2),
            ))
        profiles = bulk(StudentProfile, profiles)
        profiles = list(StudentProfile.objects.select_related('user', 'assigned_counselor').order_by('id'))
        print(f'{len(profiles)} students, {len(staff)} staff')

        tasks, applications, documents = [], [], []
        tiers = [value for value, _ in Application._meta.get_field('tier').choices]
        records = {model: [] for model in (Achievement, Research, Project, Internship, Activity, Honor,
                                           RecommendationLetter, Booking, Notification, ProgramService,
                                           ActivityLog, ChallengeAttempt, SupportTicket)}
        for profile in profiles:
            counselor_id = profile.assigned_counselor_id
            for number in range(12):
                status = rng.choice(['todo', 'todo', 'in_progress', 'submitted', 'approved', 'approved', 'late'])
                tasks.append(Task(
                    student=profile, assigned_by_id=counselor_id, title=TASK_TITLES[number],
                    description=paragraph(rng, 2), due_date=today + timedelta(days=rng.randint(-40, 90)),
                    priority=rng.choice(['low', 'medium', 'high', 'urgent']), status=status,
                    student_response=sentence(rng) if status in {'submitted', 'approved'} else '',
                ))
            for university in rng.sample(universities, 6):
                applications.append(Application(
                    student=profile, university=university, program=rng.choice(MAJORS),
                    status=rng.choice(['researching', 'shortlisted', 'applying', 'submitted', 'accepted']),
                    tier=rng.choice(tiers), deadline=today + timedelta(days=rng.randint(10, 150)),
                    notes=sentence(rng),
                ))
            for doc_type in ['passport', 'transcript', 'ielts', 'sat', 'cv', 'certificate', 'other']:
                documents.append(Document(
                    student=profile, title=doc_type.title(), document_type=doc_type,
                    status=rng.choice(['required', 'uploaded', 'reviewing', 'approved']),
                    counselor_comment=sentence(rng) if rng.random() < 0.3 else '',
                ))
            records[Achievement] += [Achievement(student=profile, title=f'Olympiad {n}',
                                                 category=Achievement.Category.OLYMPIAD,
                                                 description=paragraph(rng, 2), date=today - timedelta(days=90 * n))
                                     for n in range(3)]
            records[Research].append(Research(student=profile, title='Water quality study', summary=paragraph(rng, 3)))
            records[Project] += [Project(student=profile, title=f'Project {n}', description=paragraph(rng, 3))
                                 for n in range(2)]
            records[Internship].append(Internship(student=profile, organization='Tech Park', position='Intern',
                                                  description=paragraph(rng, 2)))
            records[Activity] += [Activity(student=profile, name=f'Club {n}', description=paragraph(rng, 2),
                                           hours_per_week=rng.randint(1, 10)) for n in range(4)]
            records[Honor] += [Honor(student=profile, title=f'Award {n}', description=sentence(rng)) for n in range(2)]
            records[RecommendationLetter] += [RecommendationLetter(student=profile, recommender_name='Teacher',
                                                                   notes=sentence(rng)) for _ in range(2)]
            records[Booking] += [Booking(student=profile, participant_id=counselor_id, topic='Essay review',
                                         starts_at=now + timedelta(days=rng.randint(-20, 30)),
                                         status=rng.choice(['pending', 'approved', 'completed']))
                                 for _ in range(3)]
            records[Notification] += [Notification(student=profile, title='Reminder', message=sentence(rng),
                                                   is_read=rng.random() < 0.6) for _ in range(8)]
            records[ProgramService] += [ProgramService(student=profile, name=name, mentor_id=counselor_id,
                                                       total_hours=20, used_hours=rng.randint(0, 20))
                                        for name in ('Essay coaching', 'SAT prep')]
            records[ActivityLog] += [ActivityLog(actor_id=counselor_id, student=profile, action='Task approved')
                                     for _ in range(5)]
            if rng.random() < 0.5:
                records[ChallengeAttempt].append(ChallengeAttempt(
                    student=profile, challenge='riasec', answers={str(q): rng.randint(1, 5) for q in range(30)},
                    scores={'R': 10, 'I': 20, 'A': 5}))
            if rng.random() < 0.2:
                records[SupportTicket].append(SupportTicket(requester=profile.user, category='technical',
                                                            subject='Cannot upload', message=paragraph(rng, 1)))
        bulk(Task, tasks)
        missions = []
        for profile in profiles:
            # The production Level 1 path (prerequisite chain included); progress
            # then runs in order: done, one in flight, the rest planned.
            chain, _ = extend_level_one_roadmap(
                student=profile, assigned_by=profile.assigned_counselor, start_date=today - timedelta(days=30),
            )
            done = rng.randint(0, len(chain))
            for position, mission in enumerate(chain):
                if position < done:
                    mission.status = RoadmapMission.Status.COMPLETED
                elif position == done:
                    mission.status = rng.choice([RoadmapMission.Status.IN_PROGRESS, RoadmapMission.Status.SUBMITTED])
            missions += chain
        RoadmapMission.objects.bulk_update(missions, ['status'], batch_size=BATCH)
        applications = bulk(Application, applications)
        bulk(Document, documents)
        for model, rows in records.items():
            bulk(model, rows)
        print(f'{len(tasks)} tasks, {len(missions)} missions, {len(applications)} applications')

        # Approval XP exactly as award_approval_xp records it, and each total
        # and level consistent with the student's transactions.
        xp_rows = [
            XPTransaction(student_id=task.student_id, source_type=XPTransaction.Source.TASK, source_id=task.pk,
                          amount=TASK_XP_BY_PRIORITY[task.priority], reason=f'Task approved: {task.title}',
                          awarded_by_id=task.assigned_by_id)
            for task in Task.objects.filter(status=Task.Status.APPROVED, is_self_assigned=False)
            .only('id', 'student_id', 'assigned_by_id', 'priority', 'title')
        ] + [
            XPTransaction(student_id=mission.student_id, source_type=XPTransaction.Source.ROADMAP,
                          source_id=mission.pk, amount=ROADMAP_APPROVAL_XP,
                          reason=f'Roadmap mission approved: {mission.title}', awarded_by_id=mission.assigned_by_id)
            for mission in missions if mission.status == RoadmapMission.Status.COMPLETED
        ]
        bulk(XPTransaction, xp_rows)
        xp_by_student = {}
        for row in xp_rows:
            xp_by_student[row.student_id] = xp_by_student.get(row.student_id, 0) + row.amount
        for profile in profiles:
            profile.xp_total = xp_by_student.get(profile.pk, 0)
            profile.level = rng.randint(1, profile.eligible_level)
        StudentProfile.objects.bulk_update(profiles, ['xp_total', 'level'], batch_size=BATCH)

        apps_by_student = {}
        for application in applications:
            apps_by_student.setdefault(application.student_id, []).append(application)
        folders = bulk(EssayFolder, [
            EssayFolder(student=profile, name=name, position=position)
            for profile in profiles for position, name in enumerate(('Common App', 'Scholarships'))
        ])
        folders_by_student = {}
        for folder in folders:
            folders_by_student.setdefault(folder.student_id, []).append(folder)
        essays, docs = [], []
        for profile in profiles:
            for number in range(4):
                doc = validate_doc(rich_doc(rng, rng.randint(450, 700)))
                stats = doc_stats(doc)
                docs.append((doc, stats))
                status = rng.choice(['draft', 'draft', 'reviewing', 'needs_revision'])
                essays.append(Essay(
                    student=profile, title=f'Essay {number + 1}', prompt=sentence(rng, 20), content=stats.content,
                    word_count=stats.word_count, preview=stats.preview,
                    essay_type=rng.choice(Essay.EssayType.values), word_limit=650,
                    application=rng.choice(apps_by_student[profile.pk]) if number == 1 else None,
                    folder=rng.choice(folders_by_student[profile.pk]) if number < 2 else None,
                    status=status, last_edited_at=now,
                    # Counselors only see essays the student shared; reviewed ones always are.
                    shared_with_counselor=status != 'draft', shared_at=now if status != 'draft' else None,
                ))
        essays = bulk(Essay, essays)
        # A one-tab document keeps the essay's text in its single tab, as the API creates it.
        tabs = bulk(EssayTab, [
            EssayTab(essay=essay, title=FIRST_TAB_TITLE, position=0, doc=doc, content=stats.content,
                     word_count=stats.word_count, char_count=stats.char_count,
                     char_count_no_spaces=stats.char_count_no_spaces, save_seq=rng.randint(5, 400), last_edited_at=now)
            for essay, (doc, stats) in zip(essays, docs)
        ])
        bulk(EssayRevision, [
            EssayRevision(essay=essay, version=essay.version, prompt=essay.prompt, content=essay.content,
                          status=essay.status, created_by_id=essay.student.user_id)
            for essay in essays
        ])
        checkpoints = []
        for tab in tabs:
            for n in range(6):
                checkpoints.append(EssayCheckpoint(essay_id=tab.essay_id, tab=tab, doc=tab.doc, content=tab.content,
                                                   word_count=tab.word_count, reason='auto'))
            if len(checkpoints) >= 12000:
                bulk(EssayCheckpoint, checkpoints)
                checkpoints = []
        bulk(EssayCheckpoint, checkpoints)
        bulk(EssayDepthCheck, [
            EssayDepthCheck(essay_id=tab.essay_id, tab=tab, save_seq=tab.save_seq, model='local',
                            result={'summary': sentence(rng), 'items': [{'kind': 'depth', 'note': sentence(rng)}] * 4})
            for tab in tabs[::3]
        ])
        print(f'{len(essays)} essays')

        screen_time = []
        for profile in profiles:
            for day in range(30):
                for page in rng.sample(PAGES, 3):
                    screen_time.append(ScreenTimeDaily(user_id=profile.user_id, date=today - timedelta(days=day),
                                                       page=page, active_seconds=rng.randint(30, 3000), sessions=3))
            if len(screen_time) >= 20000:
                bulk(ScreenTimeDaily, screen_time)
                screen_time = []
        bulk(ScreenTimeDaily, screen_time)

        parents, links = [], []
        for index, profile in enumerate(profiles[: int(len(profiles) * 0.4)]):
            parents.append(user(f'lt-p-{index + 1}', 'parent'))
        parents = bulk(User, parents)
        parents = list(User.objects.filter(role='parent').order_by('id'))
        for parent, profile in zip(parents, profiles):
            links.append(ParentStudentLink(parent=parent, student=profile, status='active', consented_at=now))
        bulk(ParentStudentLink, links)

        # Messaging: a direct chat per student and counselor, plus school channels.
        channels, memberships, messages = [], [], []
        for profile in profiles:
            low, high = sorted([profile.user_id, profile.assigned_counselor_id])
            channels.append(MessageChannel(kind='direct', direct_key=f'{low}:{high}', school_id=profile.school_id,
                                           created_by_id=profile.assigned_counselor_id))
        school_channels = []
        for school in schools:
            owner = per_school[school.pk]['counselors'][0]
            for kind, count in (('community', 2), ('discussion', 3), ('group', 5)):
                for n in range(count):
                    school_channels.append(MessageChannel(kind=kind, name=f'{kind.title()} {n + 1}', school=school,
                                                          created_by=owner, is_public=kind != 'group',
                                                          description=sentence(rng)))
        channels = bulk(MessageChannel, channels + school_channels)
        profile_by_user = {profile.user_id: profile for profile in profiles}
        students_by_school = {}
        for profile in profiles:
            students_by_school.setdefault(profile.school_id, []).append(profile.user_id)
        for channel in channels:
            if channel.kind == 'direct':
                student_id, counselor_id = (int(part) for part in channel.direct_key.split(':'))
                if student_id not in profile_by_user:
                    student_id, counselor_id = counselor_id, student_id
                members = [student_id, counselor_id]
                roles = {counselor_id: 'owner'}
                message_count = rng.randint(5, 25)
            else:
                group = per_school[channel.school_id]
                staff_ids = [u.pk for u in group['counselors'] + group['teachers']] + [group['organization'].pk]
                pupils = students_by_school[channel.school_id]
                size = {'community': len(pupils), 'discussion': 50, 'group': 30}[channel.kind]
                members = staff_ids + rng.sample(pupils, min(size, len(pupils)))
                roles = {channel.created_by_id: 'owner'}
                message_count = {'community': 400, 'discussion': 100, 'group': 150}[channel.kind]
            for member in members:
                memberships.append(ChannelMembership(channel=channel, user_id=member, role=roles.get(member, 'member'),
                                                     last_read_at=now - timedelta(days=rng.randint(0, 10))))
            for _ in range(message_count):
                messages.append(ChannelMessage(channel=channel, sender_id=rng.choice(members),
                                               body=sentence(rng, rng.randint(4, 30))))
            if len(messages) >= 20000:
                bulk(ChannelMessage, messages)
                messages = []
        bulk(ChannelMessage, messages)
        bulk(ChannelMembership, memberships)

        templates = bulk(CounselorRoadmapTemplate, [
            CounselorRoadmapTemplate(name=f'Template {n}', kind=kind, created_by=admin)
            for n, kind in enumerate(CounselorRoadmapTemplate.Kind.values)
        ])
        bulk(CounselorRoadmapTemplateMission, [
            CounselorRoadmapTemplateMission(template=template, title=f'Step {n}', sequence=n)
            for template in templates for n in range(1, 9)
        ])
        roadmaps = bulk(CounselorRoadmap, [
            CounselorRoadmap(counselor=counselor, school_id=counselor.school_id, template=templates[0],
                             title='Onboarding', kind=templates[0].kind, assigned_by=admin)
            for group in per_school.values() for counselor in group['counselors']
        ])
        bulk(CounselorRoadmapMission, [
            CounselorRoadmapMission(roadmap=roadmap, title=f'Step {n}', sequence=n,
                                    due_date=today + timedelta(days=n * 7))
            for roadmap in roadmaps for n in range(1, 9)
        ])

    if connection.vendor != 'postgresql':
        return accounts
    # Spread timestamps so orderings and "unread" windows behave like real data.
    with connection.cursor() as cursor:
        cursor.execute("UPDATE admissions_channelmessage SET created_at = now() - random() * interval '30 days'")
        cursor.execute(
            'UPDATE admissions_messagechannel c SET last_message_at = m.last '
            'FROM (SELECT channel_id, max(created_at) AS last FROM admissions_channelmessage GROUP BY channel_id) m '
            'WHERE m.channel_id = c.id'
        )
        cursor.execute("UPDATE admissions_essaycheckpoint SET created_at = now() - random() * interval '20 days'")
        cursor.execute("UPDATE admissions_essay SET updated_at = now() - random() * interval '20 days'")
        cursor.execute('ANALYZE')
    return accounts


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--students', type=int, default=5000)
    parser.add_argument('--schools', type=int, default=20)
    parser.add_argument('--out', default=str(ROOT / 'scripts' / 'loadtest' / '.accounts'))
    parser.add_argument('--seed', type=int, default=20260924)
    args = parser.parse_args()

    guard()
    setup_django()
    from apps.users.models import User

    if User.objects.exists():
        sys.exit('The database already has users; seed a freshly migrated database.')
    accounts = seed(student_count=args.students, school_count=args.schools, rng_seed=args.seed)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for role, usernames in accounts.items():
        with open(out / f'{role}.csv', 'w', newline='', encoding='utf-8') as handle:
            csv.writer(handle).writerows((name, PASSWORD) for name in usernames)
    print(f'Accounts written to {out}')


if __name__ == '__main__':
    main()
