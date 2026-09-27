"""Role isolation: roadmap missions, approvals, XP and progress."""
from datetime import date
from rest_framework import status
from ..models import (
    LevelApproval,
    RoadmapMission,
    Task,
    XPTransaction,
)
from .base import RoleIsolationBase


class RoadmapRoleIsolationTests(RoleIsolationBase):
    def test_student_can_submit_roadmap_mission_with_a_google_docs_link_only(self):
        """A written reflection or a Google Docs link is enough — neither is not."""
        own = RoadmapMission.objects.create(
            student=self.student_a,
            assigned_by=self.teacher,
            title='Docs-backed mission',
        )
        self.client.force_authenticate(self.student_a_user)
        empty = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {'status': RoadmapMission.Status.SUBMITTED},
            format='json',
        )
        self.assertEqual(empty.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Google Docs link', str(empty.data))
        submitted = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {
                'status': RoadmapMission.Status.SUBMITTED,
                'google_docs_url': 'https://docs.google.com/document/d/mission-doc/edit',
            },
            format='json',
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        own.refresh_from_db()
        self.assertEqual(own.status, RoadmapMission.Status.SUBMITTED)
        self.assertEqual(own.google_docs_url, 'https://docs.google.com/document/d/mission-doc/edit')

    def test_roadmap_stars_count_only_approved_missions(self):
        RoadmapMission.objects.create(student=self.student_a, title='Approved step', status=RoadmapMission.Status.COMPLETED)
        RoadmapMission.objects.create(student=self.student_a, title='Open step')
        self.client.force_authenticate(self.student_a_user)
        response = self.client.get('/api/students/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = response.data['results'][0]
        self.assertEqual(profile['roadmap_stars'], 1)

    def test_student_can_only_submit_roadmap_mission_with_reflection(self):
        other = RoadmapMission.objects.create(student=self.student_b, title='Private mission')
        own = RoadmapMission.objects.create(
            student=self.student_a,
            assigned_by=self.teacher,
            title='Teacher mission',
        )
        self.client.force_authenticate(self.student_a_user)
        created = self.client.post(
            '/api/roadmap-missions/',
            {
                'title': 'My application mission',
                'category': 'Applications',
                'status': RoadmapMission.Status.IN_PROGRESS,
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_403_FORBIDDEN)
        selected_status = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {
                'status': RoadmapMission.Status.IN_PROGRESS,
                'reflection': 'I started the assigned milestones.',
            },
            format='json',
        )
        self.assertEqual(selected_status.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Students cannot choose a mission status', str(selected_status.data))
        missing_reflection = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {'status': RoadmapMission.Status.SUBMITTED},
            format='json',
        )
        self.assertEqual(missing_reflection.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Add a reflection', str(missing_reflection.data))
        submitted = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {
                'status': RoadmapMission.Status.SUBMITTED,
                'reflection': 'I completed the assigned milestones.',
            },
            format='json',
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        own.refresh_from_db()
        self.assertEqual(own.status, RoadmapMission.Status.SUBMITTED)
        manual_progress = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {'progress_percent': 50},
            format='json',
        )
        self.assertEqual(manual_progress.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Manual mission progress has been removed', str(manual_progress.data))
        resubmitted = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {
                'status': RoadmapMission.Status.SUBMITTED,
                'reflection': 'Changed after submission.',
            },
            format='json',
        )
        self.assertEqual(resubmitted.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already submitted', str(resubmitted.data))
        tampered = self.client.patch(
            f'/api/roadmap-missions/{own.id}/',
            {'title': 'Student changed title'},
            format='json',
        )
        self.assertEqual(tampered.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self.client.patch(
                f'/api/roadmap-missions/{own.id}/',
                {'status': RoadmapMission.Status.COMPLETED},
                format='json',
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.delete(f'/api/roadmap-missions/{own.id}/').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        listed = self.results(self.client.get('/api/roadmap-missions/'))
        self.assertEqual([item['id'] for item in listed], [own.id])
        self.assertFalse(any(item['id'] == other.id for item in listed))

    def test_teacher_controls_tasks_and_roadmap_only_within_own_school(self):
        self.client.force_authenticate(self.teacher)
        students = self.results(self.client.get('/api/students/'))
        self.assertEqual([item['id'] for item in students], [self.student_a.id])

        task = self.client.post(
            '/api/tasks/',
            {
                'student': self.student_a.id,
                'title': 'Teacher task',
                'due_date': date(2027, 12, 1),
                'status': Task.Status.TODO,
            },
            format='json',
        )
        self.assertEqual(task.status_code, status.HTTP_201_CREATED)
        self.assertEqual(task.data['assigned_by'], self.teacher.id)

        mission = self.client.post(
            '/api/roadmap-missions/',
            {
                'student': self.student_a.id,
                'title': 'Teacher roadmap mission',
                'status': RoadmapMission.Status.PLANNED,
            },
            format='json',
        )
        self.assertEqual(mission.status_code, status.HTTP_201_CREATED)
        self.assertEqual(mission.data['assigned_by'], self.teacher.id)

        cross_school_task = self.client.post(
            '/api/tasks/',
            {
                'student': self.student_b.id,
                'title': 'Forbidden teacher task',
                'due_date': date(2027, 12, 1),
            },
            format='json',
        )
        self.assertEqual(cross_school_task.status_code, status.HTTP_400_BAD_REQUEST)
        cross_school_mission = self.client.post(
            '/api/roadmap-missions/',
            {'student': self.student_b.id, 'title': 'Forbidden teacher mission'},
            format='json',
        )
        self.assertEqual(cross_school_mission.status_code, status.HTTP_400_BAD_REQUEST)

    def test_staff_can_extend_level_one_without_duplicates_and_students_follow_order(self):
        self.client.force_authenticate(self.teacher)
        extended = self.client.post(
            '/api/roadmap-missions/extend-level-one/',
            {'student': self.student_a.id},
            format='json',
        )
        self.assertEqual(extended.status_code, status.HTTP_200_OK)
        self.assertEqual(extended.data['created_count'], 8)
        self.assertEqual(extended.data['total_count'], 8)
        self.assertEqual(
            [item['sequence'] for item in extended.data['missions']],
            list(range(1, 9)),
        )
        self.assertIsNone(extended.data['missions'][0]['prerequisite'])
        self.assertEqual(
            extended.data['missions'][1]['prerequisite'],
            extended.data['missions'][0]['id'],
        )

        repeated = self.client.post(
            '/api/roadmap-missions/extend-level-one/',
            {'student': self.student_a.id},
            format='json',
        )
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated.data['created_count'], 0)
        self.assertEqual(RoadmapMission.objects.filter(student=self.student_a, level=1).count(), 8)

        outside_scope = self.client.post(
            '/api/roadmap-missions/extend-level-one/',
            {'student': self.student_b.id},
            format='json',
        )
        self.assertEqual(outside_scope.status_code, status.HTTP_403_FORBIDDEN)

        first, second = RoadmapMission.objects.filter(student=self.student_a).order_by('sequence')[:2]
        self.client.force_authenticate(self.student_a_user)
        locked = self.client.patch(
            f'/api/roadmap-missions/{second.id}/',
            {
                'status': RoadmapMission.Status.SUBMITTED,
                'reflection': 'I completed the second mission.',
            },
            format='json',
        )
        self.assertEqual(locked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('previous Level 1 mission', str(locked.data))

        student_extend = self.client.post(
            '/api/roadmap-missions/extend-level-one/',
            {'student': self.student_a.id},
            format='json',
        )
        self.assertEqual(student_extend.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_or_counselor_approval_is_required_for_submitted_work(self):
        task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.teacher,
            title='Submitted task',
            due_date=date(2027, 12, 1),
            status=Task.Status.SUBMITTED,
        )
        mission = RoadmapMission.objects.create(
            student=self.student_a,
            assigned_by=self.teacher,
            title='Submitted mission',
            status=RoadmapMission.Status.SUBMITTED,
        )
        self.client.force_authenticate(self.teacher)
        approved_task = self.client.post(f'/api/tasks/{task.id}/approve/', {}, format='json')
        approved_mission = self.client.post(f'/api/roadmap-missions/{mission.id}/approve/', {}, format='json')
        self.assertEqual(approved_task.status_code, status.HTTP_200_OK)
        self.assertEqual(approved_task.data['status'], Task.Status.APPROVED)
        self.assertEqual(approved_mission.status_code, status.HTTP_200_OK)
        self.assertEqual(approved_mission.data['status'], RoadmapMission.Status.COMPLETED)
        self.assertNotIn('progress_percent', approved_mission.data)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.xp_total, 125)
        self.assertEqual(self.student_a.level, 1)
        self.assertEqual(self.student_a.eligible_level, 2)
        self.assertTrue(self.student_a.level_up_pending)
        self.assertEqual(XPTransaction.objects.filter(student=self.student_a).count(), 2)

        repeated_task = self.client.post(f'/api/tasks/{task.id}/approve/', {}, format='json')
        repeated_mission = self.client.post(f'/api/roadmap-missions/{mission.id}/approve/', {}, format='json')
        self.assertEqual(repeated_task.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated_task.data['xp_awarded'], 0)
        self.assertEqual(repeated_mission.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated_mission.data['xp_awarded'], 0)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.xp_total, 125)

        self.client.force_authenticate(self.student_a_user)
        student_approval = self.client.post(f'/api/students/{self.student_a.id}/approve-level/', {}, format='json')
        self.assertEqual(student_approval.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.teacher)
        level_approval = self.client.post(f'/api/students/{self.student_a.id}/approve-level/', {}, format='json')
        self.assertEqual(level_approval.status_code, status.HTTP_200_OK)
        self.assertEqual(level_approval.data['level'], 2)
        self.assertFalse(level_approval.data['level_up_pending'])
        self.assertEqual(LevelApproval.objects.get(student=self.student_a).approved_by, self.teacher)

    def test_approved_status_cannot_bypass_xp_ledger(self):
        task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.teacher,
            title='Approval action required',
            due_date=date(2027, 12, 1),
            status=Task.Status.SUBMITTED,
        )
        mission = RoadmapMission.objects.create(
            student=self.student_a,
            assigned_by=self.teacher,
            title='Roadmap approval action required',
            status=RoadmapMission.Status.SUBMITTED,
        )
        self.client.force_authenticate(self.teacher)
        direct_task = self.client.patch(
            f'/api/tasks/{task.id}/',
            {'status': Task.Status.APPROVED},
            format='json',
        )
        direct_mission = self.client.patch(
            f'/api/roadmap-missions/{mission.id}/',
            {'status': RoadmapMission.Status.COMPLETED},
            format='json',
        )
        self.assertEqual(direct_task.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(direct_mission.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(XPTransaction.objects.exists())

    def test_task_roadmap_and_journey_progress_are_computed(self):
        Task.objects.create(student=self.student_a, title='Working task', due_date=date(2027, 12, 1), status=Task.Status.IN_PROGRESS)
        Task.objects.create(student=self.student_a, title='Approved task', due_date=date(2027, 12, 1), status=Task.Status.APPROVED)
        RoadmapMission.objects.create(student=self.student_a, title='Planned mission', status=RoadmapMission.Status.PLANNED)
        RoadmapMission.objects.create(student=self.student_a, title='Done mission', status=RoadmapMission.Status.COMPLETED)
        self.assertEqual(self.student_a.task_progress_percent, 70)
        self.assertEqual(self.student_a.roadmap_progress_percent, 50)
        self.assertEqual(self.student_a.journey_progress_percent, 60)
        self.client.force_authenticate(self.student_a_user)
        profile = self.results(self.client.get('/api/students/'))[0]
        self.assertEqual(profile['task_progress_percent'], 70)
        self.assertEqual(profile['roadmap_progress_percent'], 50)
        self.assertEqual(profile['journey_progress_percent'], 60)
        self.assertEqual(profile['task_status_counts']['approved'], 1)
        self.assertEqual(profile['roadmap_status_counts']['completed'], 1)

    def test_dashboard_exposes_progress_and_risk_summary(self):
        Task.objects.create(student=self.student_a, title='Late task', due_date=date(2025, 1, 1), status=Task.Status.LATE)
        RoadmapMission.objects.create(student=self.student_a, title='Current mission', status=RoadmapMission.Status.IN_PROGRESS)
        self.client.force_authenticate(self.counselor)
        response = self.client.get('/api/dashboard/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('average_task_progress', response.data)
        self.assertIn('average_roadmap_progress', response.data)
        self.assertIn('average_journey_progress', response.data)
        self.assertEqual(response.data['students_at_risk'], 1)
