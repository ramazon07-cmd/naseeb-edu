from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.users.models import User
from apps.admissions.models import (
    Achievement, Activity, Application, Booking, CommunityPost, Document, Essay,
    ChannelMembership, ChannelMessage, Honor, Internship, MeetingNote, MessageChannel,
    Notification, OpportunityProgram, ProgramService, Project,
    RecommendationLetter, Research, ResourceLibraryItem, RoadmapMission, School,
    Scholarship, StoreItem, StudentMessage, StudentProfile, Task, University,
)


class Command(BaseCommand):
    help = 'Create Naseeb Edu demo data.'

    def handle(self, *args, **options):
        if not settings.DEMO_ACCOUNTS_ENABLED:
            raise CommandError('Demo accounts are disabled in this environment.')

        school, _ = School.objects.get_or_create(
            code='naseeb-edu-demo',
            defaults={
                'name': 'Naseeb Edu Demo School',
                'contact_email': 'school@naseeb.local',
                'contact_phone': '+998971230586',
            },
        )
        counselor, _ = User.objects.get_or_create(
            username='counselor',
            defaults={
                'email': 'counselor@naseeb.local',
                'first_name': 'Madina',
                'last_name': 'Counselor',
                'role': User.Role.COUNSELOR,
                'is_staff': True,
            },
        )
        counselor.set_password(settings.DEMO_COUNSELOR_PASSWORD)
        counselor.save()

        organization, _ = User.objects.get_or_create(
            username='schooladmin',
            defaults={
                'email': 'schooladmin@naseeb.local',
                'first_name': 'Naseeb Edu',
                'last_name': 'School',
                'role': User.Role.ORGANIZATION,
                'school': school,
            },
        )
        organization.role = User.Role.ORGANIZATION
        organization.school = school
        organization.set_password(settings.DEMO_ORGANIZATION_PASSWORD)
        organization.save()

        universities = [
            {
                'name': 'National University of Singapore', 'country': 'Singapore', 'city': 'Singapore', 'ranking': 8,
                'institution_type': 'public', 'campus_setting': 'urban', 'acceptance_rate': 8.0,
                'sat_min': 1430, 'sat_max': 1550, 'tuition_usd': 29000, 'net_price_usd': 18000,
                'average_aid_usd': 18000, 'students_receiving_aid_percent': 62, 'undergrad_enrollment': 32000,
                'student_faculty_ratio': '14:1', 'test_optional': False, 'offers_need_based_aid': True,
                'offers_merit_aid': True, 'offers_international_aid': True, 'meets_full_need': False,
                'aid_application_notes': 'Financial declaration and scholarship application may be required.',
                'popular_majors': 'Computer Science,Engineering,Business',
                'application_deadline': '2027-02-01', 'scholarship_deadline': '2027-01-15',
            },
            {
                'name': 'Nanyang Technological University', 'country': 'Singapore', 'city': 'Singapore', 'ranking': 15,
                'institution_type': 'public', 'campus_setting': 'suburban', 'acceptance_rate': 16.0,
                'sat_min': 1380, 'sat_max': 1520, 'tuition_usd': 27000, 'net_price_usd': 17000,
                'average_aid_usd': 15000, 'students_receiving_aid_percent': 55, 'undergrad_enrollment': 24000,
                'student_faculty_ratio': '15:1', 'offers_need_based_aid': True, 'offers_merit_aid': True,
                'offers_international_aid': True, 'popular_majors': 'Engineering,Data Science,Communication',
                'application_deadline': '2027-01-20', 'scholarship_deadline': '2027-01-10',
            },
            {
                'name': 'The Chinese University of Hong Kong', 'country': 'Hong Kong', 'city': 'Hong Kong', 'ranking': 36,
                'institution_type': 'public', 'campus_setting': 'suburban', 'acceptance_rate': 18.0,
                'sat_min': 1350, 'sat_max': 1510, 'tuition_usd': 19000, 'net_price_usd': 12500,
                'average_aid_usd': 14000, 'students_receiving_aid_percent': 48, 'undergrad_enrollment': 18000,
                'student_faculty_ratio': '13:1', 'offers_merit_aid': True, 'offers_international_aid': True,
                'popular_majors': 'Economics,Medicine,Data Science',
                'application_deadline': '2027-01-05', 'scholarship_deadline': '2026-12-15',
            },
            {
                'name': 'University of British Columbia', 'country': 'Canada', 'city': 'Vancouver', 'ranking': 38,
                'institution_type': 'public', 'campus_setting': 'urban', 'acceptance_rate': 53.0,
                'sat_min': 1270, 'sat_max': 1470, 'tuition_usd': 35000, 'net_price_usd': 22000,
                'average_aid_usd': 12000, 'students_receiving_aid_percent': 58, 'undergrad_enrollment': 59000,
                'student_faculty_ratio': '18:1', 'test_optional': True, 'offers_need_based_aid': True,
                'offers_merit_aid': True, 'offers_international_aid': True,
                'popular_majors': 'Business,Biology,Computer Science',
                'application_deadline': '2027-01-15', 'scholarship_deadline': '2026-12-01',
            },
            {
                'name': 'Duke University', 'country': 'USA', 'city': 'Durham', 'ranking': 57,
                'institution_type': 'private', 'campus_setting': 'suburban', 'acceptance_rate': 6.3,
                'sat_min': 1490, 'sat_max': 1570, 'act_min': 34, 'act_max': 35,
                'tuition_usd': 69000, 'net_price_usd': 25000, 'average_aid_usd': 56000,
                'students_receiving_aid_percent': 51, 'undergrad_enrollment': 6800, 'student_faculty_ratio': '6:1',
                'test_optional': True, 'offers_need_based_aid': True, 'offers_merit_aid': True,
                'offers_athletic_aid': True, 'offers_international_aid': True, 'meets_full_need': True,
                'css_profile_required': True, 'aid_application_notes': 'CSS Profile and supporting income documents may be required.',
                'popular_majors': 'Computer Science,Public Policy,Economics',
                'application_deadline': '2027-01-02', 'scholarship_deadline': '2027-01-02',
            },
        ]
        uni_objs = []
        for item in universities:
            lookup = {'name': item['name'], 'country': item['country']}
            defaults = {key: value for key, value in item.items() if key not in lookup}
            uni, _ = University.objects.update_or_create(**lookup, defaults=defaults)
            uni_objs.append(uni)

        scholarship_rows = [
            ('Naseeb Global Excellence Award', 'Naseeb Education', 'merit', 'fixed', 'international', 10000, 'Tuition contribution', 4.5, 6.5, 1350, True, True, False),
            ('Future Leaders Full Scholarship', 'Global Learning Foundation', 'leadership', 'full', 'international', None, 'Tuition, housing and learning materials', 4.7, 7.0, None, True, True, True),
            ('STEM Research Grant', 'Central Asia Science Network', 'research', 'partial', 'national', 5000, 'Research and program costs', 4.2, 6.0, None, True, False, False),
            ('Need-based Access Award', 'Education Access Fund', 'need_based', 'partial', 'international', 15000, 'Tuition support based on demonstrated need', None, None, None, True, True, True),
            ('National Academic Merit Award', 'Naseeb Education', 'merit', 'fixed', 'national', 3000, 'Program fees and mentorship', 4.4, None, 1250, False, True, False),
            ('Young Innovator Full Ride', 'Innovation Bridge', 'full_ride', 'full', 'international', None, 'Full program fee and accommodation', 4.6, 6.5, 1300, True, True, False),
        ]
        for index, row in enumerate(scholarship_rows):
            title, provider, scholarship_type, funding_level, scope, amount, coverage, min_gpa, min_ielts, min_sat, essay, recommendation, finance = row
            Scholarship.objects.update_or_create(
                title=title,
                provider=provider,
                defaults={
                    'university': uni_objs[index % len(uni_objs)] if index > 2 else None,
                    'scholarship_type': scholarship_type,
                    'funding_level': funding_level,
                    'scope': scope,
                    'amount_usd': amount,
                    'coverage': coverage,
                    'eligible_countries': 'Uzbekistan,Central Asia',
                    'eligible_grades': '10,11,gap',
                    'min_gpa': min_gpa,
                    'min_ielts': min_ielts,
                    'min_sat': min_sat,
                    'requires_essay': essay,
                    'requires_recommendation': recommendation,
                    'requires_financial_documents': finance,
                    'requires_transcript': True,
                    'requires_cv': True,
                    'deadline': f'2027-0{(index % 4) + 1}-15',
                    'application_url': 'https://example.com/scholarships',
                    'is_active': True,
                },
            )

        program_rows = [
            ('Tashkent Research Sprint', 'Naseeb Research Lab', 'national', 'Research', 'Uzbekistan', 'Tashkent', 'hybrid', 0, True),
            ('Young Leaders Academy', 'Youth Development Center', 'national', 'Leadership', 'Uzbekistan', 'Samarkand', 'onsite', 250, True),
            ('National Olympiad Preparation', 'Academic Excellence Hub', 'national', 'Competition', 'Uzbekistan', 'Tashkent', 'online', 120, False),
            ('Tech Innovation Bootcamp', 'Digital Generation Lab', 'national', 'Technology', 'Uzbekistan', 'Tashkent', 'hybrid', 300, True),
            ('Global Summer Research', 'International Student Network', 'international', 'Research', 'Singapore', 'Singapore', 'onsite', 2200, True),
            ('International Case Competition', 'Global Business League', 'international', 'Competition', 'United Kingdom', 'London', 'hybrid', 500, True),
            ('Virtual Policy Fellowship', 'Future Policy Institute', 'international', 'Fellowship', 'Online', '', 'online', 0, False),
            ('Asia Student Innovation Camp', 'Asia Education Alliance', 'international', 'Summer program', 'Malaysia', 'Kuala Lumpur', 'onsite', 1600, True),
        ]
        for index, row in enumerate(program_rows):
            title, provider, program_type, category, country, city, mode, fee, aid = row
            OpportunityProgram.objects.update_or_create(
                title=title,
                provider=provider,
                defaults={
                    'program_type': program_type,
                    'category': category,
                    'country': country,
                    'city': city,
                    'delivery_mode': mode,
                    'description': 'Profile-building program with structured projects, mentor feedback and a final outcome.',
                    'eligible_grades': '9,10,11,gap',
                    'deadline': f'2027-0{(index % 5) + 1}-20',
                    'fee_usd': fee,
                    'scholarship_available': aid,
                    'aid_details': 'Need-based and merit discounts available.' if aid else '',
                    'requirements': 'Transcript, short motivation response and activity summary.',
                    'application_url': 'https://example.com/programs',
                    'is_active': True,
                },
            )

        student_data = [
            ('ramazon', 'Ramazon', 'Ergashev', 'ramazon@rbis.uz', 'Computer Science', 'Singapore,Hong Kong,USA', 4.90, 7.0, 1450),
            ('aziza', 'Aziza', 'Karimova', 'aziza@rbis.uz', 'Economics', 'USA,Canada', 4.75, 7.5, 1410),
            ('muhammad', 'Muhammad', 'Aliyev', 'muhammad@rbis.uz', 'Data Science', 'Singapore,UK', 4.60, 6.5, 1360),
            ('sevara', 'Sevara', 'Toshmatova', 'sevara@rbis.uz', 'Business Analytics', 'Hong Kong,Canada', 4.80, 7.0, 1390),
        ]

        today = timezone.localdate()

        resources = [
            ('College Search', 'School resources', 'Find and compare universities', 'college_search', 1),
            ('Essay Lab', 'Essays', 'Essay drafts, feedback, and revision history', 'essay_lab', 1),
            ('Application Tracker', 'Applications', 'University applications and deadline tracking', 'applications', 1),
            ('Activities & Honors', 'Profile building', 'Activities, honors, and achievements', 'student_center', 1),
            ('Application Roadmap', 'Planning', 'Missions, tasks, and reflections', 'roadmap', 1),
            ('National & International Programs', 'Programs', 'National and international program catalog', 'programs', 1),
            ('Documents & Certificates', 'Documents', 'Application documents and certificates', 'student_center', 1),
        ]
        for title, category, description, destination, order in resources:
            ResourceLibraryItem.objects.get_or_create(
                title=title,
                defaults={
                    'category': category,
                    'description': description,
                    'destination': destination,
                    'sort_order': order,
                },
            )

        store_items = [
            ('SAT Strategy Sprint', 'Test preparation', 'Personal diagnostic, study plan and weekly review.', 'Consultation'),
            ('Essay Review Pack', 'Application support', 'Structured review for a personal statement and supplements.', 'Consultation'),
            ('University Match Session', 'School selection', 'Profile-based university shortlist with scholarship focus.', 'Included'),
            ('Interview Practice', 'Application support', 'Mock interview, feedback and next-step checklist.', 'Consultation'),
        ]
        for title, category, description, price_label in store_items:
            StoreItem.objects.get_or_create(
                title=title,
                defaults={
                    'category': category,
                    'description': description,
                    'price_label': price_label,
                    'is_featured': title == 'University Match Session',
                },
            )

        for idx, (username, first, last, email, major, countries, gpa, ielts, sat) in enumerate(student_data):
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={'email': email, 'first_name': first, 'last_name': last, 'role': User.Role.STUDENT},
            )
            user.set_password(settings.DEMO_STUDENT_PASSWORD)
            user.role = User.Role.STUDENT
            user.school = school
            user.save()
            student, _ = StudentProfile.objects.get_or_create(
                user=user,
                defaults={
                    'assigned_counselor': counselor,
                    'school': school,
                    'school_name': school.name,
                    'grade': StudentProfile.Grade.GRADE_11,
                    'gpa': gpa,
                    'ielts_score': ielts,
                    'sat_score': sat,
                    'target_major': major,
                    'target_countries': countries,
                    'budget_usd': 12000,
                    'scholarship_needed': True,
                    'notes': 'Strong profile, needs essay polishing and deadline discipline.',
                },
            )

            for j, uni in enumerate(uni_objs[idx:idx+3] or uni_objs[:3]):
                Application.objects.get_or_create(
                    student=student,
                    university=uni,
                    program=major,
                    defaults={
                        'tier': ['dream', 'target', 'safety'][j % 3],
                        'status': ['applying', 'shortlisted', 'researching'][j % 3],
                        'deadline': uni.application_deadline,
                        'scholarship_deadline': uni.scholarship_deadline,
                        'notes': 'Check scholarship form and recommendation requirements.',
                    },
                )

            tasks = [
                ('Personal Statement 1-draft', today + timedelta(days=5), 'urgent', 'in_progress'),
                ('IELTS certificate upload', today + timedelta(days=2), 'high', 'todo'),
                ('Activities list final version', today + timedelta(days=9), 'medium', 'todo'),
                ('Recommendation letter request', today - timedelta(days=1), 'urgent', 'late'),
            ]
            for title, due, priority, status in tasks:
                Task.objects.get_or_create(
                    student=student,
                    title=title,
                    defaults={'assigned_by': counselor, 'due_date': due, 'priority': priority, 'status': status},
                )

            for doc_title, doc_type, status in [
                ('Passport scan', 'passport', 'approved'),
                ('Academic transcript', 'transcript', 'reviewing'),
                ('IELTS certificate', 'ielts', 'required'),
                ('Academic excellence certificate', 'certificate', 'approved'),
                ('CV / Resume', 'cv', 'uploaded'),
            ]:
                Document.objects.get_or_create(student=student, title=doc_title, defaults={'document_type': doc_type, 'status': status})

            Achievement.objects.get_or_create(
                student=student,
                title=f'{major} portfolio project',
                defaults={
                    'category': 'project',
                    'description': f'Built a practical project connected to {major}.',
                    'impact': 'Demonstrates initiative, leadership, and technical execution.',
                    'date': today - timedelta(days=60),
                    'verified': idx % 2 == 0,
                },
            )

            Project.objects.get_or_create(
                student=student,
                title=f'{major} practical project',
                defaults={
                    'role': 'Founder / Lead Developer',
                    'description': f'Built a practical product connected to {major}.',
                    'impact': 'Validated with real users and documented measurable results.',
                    'technologies': 'Python, Django, JavaScript',
                    'date': today - timedelta(days=75),
                    'verified': idx % 2 == 0,
                },
            )
            Research.objects.get_or_create(
                student=student,
                title=f'{major} research exploration',
                defaults={
                    'field': major,
                    'role': 'Student researcher',
                    'summary': 'Investigated a real problem, reviewed evidence, and presented findings.',
                    'outcome': 'School presentation and written report.',
                    'start_date': today - timedelta(days=120),
                    'end_date': today - timedelta(days=45),
                    'verified': True,
                },
            )
            Internship.objects.get_or_create(
                student=student,
                organization='Naseeb Edu Career Lab',
                position='Project Intern',
                defaults={
                    'description': 'Worked on a supervised applied project and weekly deliverables.',
                    'start_date': today - timedelta(days=90),
                    'end_date': today - timedelta(days=30),
                    'supervisor': 'School Counselor',
                    'verified': True,
                },
            )
            Activity.objects.get_or_create(
                student=student,
                name='Community education initiative',
                defaults={
                    'activity_type': Activity.Type.LEADERSHIP,
                    'role': 'Team lead',
                    'description': 'Organized peer-learning sessions and coordinated volunteers.',
                    'impact': 'Delivered four sessions for younger students.',
                    'hours_per_week': 3,
                    'weeks_per_year': 20,
                    'start_date': today - timedelta(days=180),
                    'verified': True,
                },
            )
            Honor.objects.get_or_create(
                student=student,
                title='Academic Excellence Recognition',
                defaults={
                    'issuer': 'Naseeb Edu',
                    'level': Honor.Level.SCHOOL,
                    'award_date': today - timedelta(days=40),
                    'description': 'Recognition for academic performance and initiative.',
                    'verified': True,
                },
            )
            RecommendationLetter.objects.get_or_create(
                student=student,
                recommender_name='Subject Teacher',
                defaults={
                    'recommender_title': 'Academic Teacher',
                    'recommender_email': 'teacher@rbis.uz',
                    'relationship': 'Taught the student for two academic years',
                    'status': RecommendationLetter.Status.DRAFTING,
                    'deadline': today + timedelta(days=21),
                },
            )

            first_app = Application.objects.filter(student=student).first()
            Essay.objects.get_or_create(
                student=student,
                application=first_app,
                title='Main Personal Statement',
                defaults={
                    'prompt': 'Tell us about your academic journey, motivation, and future goals.',
                    'content': 'Draft is being prepared by the student.',
                    'status': 'needs_revision',
                    'counselor_comment': 'Needs a stronger opening story and clearer impact metrics.',
                },
            )

            MeetingNote.objects.get_or_create(
                student=student,
                title=f'{first} application review meeting',
                defaults={
                    'counselor': counselor,
                    'meeting_date': today,
                    'summary': 'Reviewed target universities, document status, and essay priorities.',
                    'next_steps': 'Finish priority task, upload missing documents, and update application tracker.',
                },
            )

            Notification.objects.get_or_create(
                student=student,
                title='Deadline alert',
                defaults={'message': 'Recommendation letter request is late. Follow up today.', 'channel': 'system'},
            )

            RoadmapMission.objects.get_or_create(
                student=student,
                title='Build a balanced university shortlist',
                defaults={
                    'assigned_by': counselor,
                    'category': 'Applications',
                    'description': 'Compare reach, target and safety options with scholarship deadlines.',
                    'due_date': today + timedelta(days=14),
                    'status': RoadmapMission.Status.IN_PROGRESS,
                    'progress_percent': 55,
                },
            )
            RoadmapMission.objects.get_or_create(
                student=student,
                title='Complete personal statement package',
                defaults={
                    'assigned_by': counselor,
                    'category': 'Essays',
                    'description': 'Finish the main essay and prepare the first supplement outline.',
                    'due_date': today + timedelta(days=28),
                    'status': RoadmapMission.Status.PLANNED,
                    'progress_percent': 20,
                },
            )

            ProgramService.objects.get_or_create(
                student=student,
                name='Undergraduate Admissions Strategy',
                defaults={
                    'category': 'Admissions consulting',
                    'mentor': counselor,
                    'unlimited': True,
                    'status': ProgramService.Status.ACTIVE,
                },
            )
            ProgramService.objects.get_or_create(
                student=student,
                name='Application Essay Mentor',
                defaults={
                    'category': 'Essay support',
                    'mentor': counselor,
                    'total_hours': 10,
                    'used_hours': idx + 1,
                    'status': ProgramService.Status.ACTIVE,
                },
            )

            Booking.objects.get_or_create(
                student=student,
                topic='Application strategy check-in',
                defaults={
                    'counselor': counselor,
                    'starts_at': timezone.now() + timedelta(days=idx + 2),
                    'duration_minutes': 45,
                    'status': Booking.Status.CONFIRMED,
                    'notes': 'Review university list and next deadlines.',
                },
            )

            StudentMessage.objects.get_or_create(
                student=student,
                sender=counselor,
                recipient=user,
                body='Welcome to your Naseeb Edu student portal. I have added your next priorities to the roadmap.',
            )
            StudentMessage.objects.get_or_create(
                student=student,
                sender=user,
                recipient=counselor,
                body='Thank you. I will update the essay draft and document checklist.',
            )

            CommunityPost.objects.get_or_create(
                author=student,
                title=f'{major} applicants: useful resources',
                defaults={
                    'post_type': CommunityPost.Type.DISCUSSION,
                    'body': 'Share one reliable resource or planning method that helped your application progress.',
                },
            )

        student_users = list(User.objects.filter(
            role=User.Role.STUDENT,
            student_profile__school=school,
        ).order_by('id'))

        community_channel, _ = MessageChannel.objects.get_or_create(
            kind=MessageChannel.Kind.COMMUNITY,
            school=school,
            name='Naseeb Edu Demo Community',
            defaults={
                'description': 'School announcements, clubs and shared opportunities.',
                'created_by': organization,
                'is_public': True,
            },
        )
        ChannelMembership.objects.get_or_create(
            channel=community_channel,
            user=organization,
            defaults={'role': ChannelMembership.Role.OWNER},
        )
        ChannelMembership.objects.get_or_create(
            channel=community_channel,
            user=counselor,
            defaults={'role': ChannelMembership.Role.MODERATOR},
        )
        for member in student_users:
            ChannelMembership.objects.get_or_create(channel=community_channel, user=member)
        community_message, _ = ChannelMessage.objects.get_or_create(
            channel=community_channel,
            sender=organization,
            body='Welcome! Share verified opportunities, club updates and useful admissions resources here.',
        )
        community_channel.last_message_at = community_message.created_at
        community_channel.save(update_fields=['last_message_at', 'updated_at'])

        group_channel, _ = MessageChannel.objects.get_or_create(
            kind=MessageChannel.Kind.GROUP,
            school=school,
            name='Grade 11 Application Sprint',
            defaults={
                'description': 'Private weekly priorities for the Grade 11 cohort.',
                'created_by': counselor,
                'is_public': False,
            },
        )
        ChannelMembership.objects.get_or_create(
            channel=group_channel,
            user=counselor,
            defaults={'role': ChannelMembership.Role.OWNER},
        )
        for member in student_users:
            ChannelMembership.objects.get_or_create(channel=group_channel, user=member)
        group_message, _ = ChannelMessage.objects.get_or_create(
            channel=group_channel,
            sender=counselor,
            body='This week: update your university shortlist and submit the personal statement draft.',
        )
        group_channel.last_message_at = group_message.created_at
        group_channel.save(update_fields=['last_message_at', 'updated_at'])

        if student_users:
            discussion_channel, _ = MessageChannel.objects.get_or_create(
                kind=MessageChannel.Kind.DISCUSSION,
                school=school,
                name='How do I make my personal statement specific?',
                defaults={
                    'description': 'A Q&A thread with anonymous posting and accepted answers.',
                    'created_by': student_users[0],
                    'is_public': True,
                },
            )
            ChannelMembership.objects.get_or_create(
                channel=discussion_channel,
                user=student_users[0],
                defaults={'role': ChannelMembership.Role.OWNER},
            )
            ChannelMembership.objects.get_or_create(channel=discussion_channel, user=counselor)
            question, _ = ChannelMessage.objects.get_or_create(
                channel=discussion_channel,
                sender=student_users[0],
                body='How can I connect one personal experience to my academic goal?',
                defaults={'is_anonymous': True},
            )
            answer, _ = ChannelMessage.objects.get_or_create(
                channel=discussion_channel,
                sender=counselor,
                parent=question,
                body='Start with one concrete moment, explain what changed, then connect that lesson to the work you want to do.',
                defaults={'is_accepted_answer': True},
            )
            discussion_channel.last_message_at = answer.created_at
            discussion_channel.save(update_fields=['last_message_at', 'updated_at'])

            first_id, second_id = sorted([counselor.id, student_users[0].id])
            direct_channel, _ = MessageChannel.objects.get_or_create(
                direct_key=f'{first_id}:{second_id}',
                defaults={
                    'kind': MessageChannel.Kind.DIRECT,
                    'school': school,
                    'created_by': counselor,
                    'is_public': False,
                },
            )
            ChannelMembership.objects.get_or_create(
                channel=direct_channel,
                user=counselor,
                defaults={'role': ChannelMembership.Role.OWNER},
            )
            ChannelMembership.objects.get_or_create(channel=direct_channel, user=student_users[0])
            direct_message, _ = ChannelMessage.objects.get_or_create(
                channel=direct_channel,
                sender=counselor,
                body='Your roadmap is updated. Send your draft here when it is ready for review.',
            )
            direct_channel.last_message_at = direct_message.created_at
            direct_channel.save(update_fields=['last_message_at', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(
            'Demo data created. Credentials are configured through local DEMO_*_PASSWORD variables.'
        ))
