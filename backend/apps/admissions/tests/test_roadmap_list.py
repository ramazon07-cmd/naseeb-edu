"""A page of missions says whether each one is locked, without extra queries."""
from rest_framework.test import APITestCase

from apps.admissions.models import RoadmapMission
from apps.admissions.test_audit_base import AuditBaseMixin


class MissionPrerequisiteStatusTests(AuditBaseMixin, APITestCase):
    def chain(self, length):
        previous = None
        for index in range(length):
            previous = RoadmapMission.objects.create(
                student=self.student, title=f'Step {index}', sequence=index + 1, prerequisite=previous,
                status=RoadmapMission.Status.COMPLETED if index == 0 else RoadmapMission.Status.PLANNED,
            )

    def test_prerequisite_status_is_listed_in_constant_queries(self):
        self.client.force_authenticate(self.counselor)
        self.chain(3)
        few, _ = self.get_counted('/api/roadmap-missions/?ordering=sequence')
        RoadmapMission.objects.all().delete()
        self.chain(9)
        many, response = self.get_counted('/api/roadmap-missions/?ordering=sequence')
        self.assertEqual(few, many)
        statuses = [(item['sequence'], item['prerequisite_status']) for item in self.results(response)]
        self.assertEqual(statuses[:3], [(1, None), (2, 'completed'), (3, 'planned')])
