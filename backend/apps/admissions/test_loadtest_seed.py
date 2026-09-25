"""The load-test seed (scripts/loadtest/seed.py) writes data in the production format.

It bulk-inserts for speed, so this runs it at a tiny size and checks the rows
against the same rules the application's own code paths follow.
"""
import contextlib
import importlib.util
import io
from pathlib import Path
from unittest import skipUnless

from django.apps import apps
from django.db.models import Sum
from django.test import TestCase

from apps.users.models import User, WorkspaceSubscription

from .essay_lab.doc import doc_stats, validate_doc
from .models import Essay, RoadmapMission, School, StudentProfile, XPTransaction
from .services import LEVEL_ONE_MISSIONS

SEED_PATH = Path(__file__).resolve().parents[3] / 'scripts' / 'loadtest' / 'seed.py'


def load_seed_module():
    spec = importlib.util.spec_from_file_location('loadtest_seed', SEED_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@skipUnless(SEED_PATH.exists(), 'the load-test scripts are not part of this checkout')
class LoadtestSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.accounts = load_seed_module().seed(student_count=4, school_count=2, rng_seed=7)

    def test_accounts_and_workspaces_look_like_production_ones(self):
        self.assertEqual(len(self.accounts['student']), 4)
        self.assertEqual(
            set(School.objects.values_list('pk', flat=True)),
            set(WorkspaceSubscription.objects.values_list('school_id', flat=True)),
        )
        self.assertFalse(User.objects.filter(role=User.Role.COUNSELOR, is_staff=True).exists())
        profiles = StudentProfile.objects.select_related('user', 'school', 'assigned_counselor')
        self.assertEqual(profiles.count(), 4)
        for profile in profiles:
            self.assertEqual(profile.user.school_id, profile.school_id)
            self.assertEqual(profile.school_name, profile.school.name)
            self.assertEqual(profile.assigned_counselor.school_id, profile.school_id)

    def test_progress_follows_the_approval_rules(self):
        for profile in StudentProfile.objects.all():
            earned = XPTransaction.objects.filter(student=profile).aggregate(total=Sum('amount'))['total'] or 0
            self.assertEqual(profile.xp_total, earned)
            self.assertLessEqual(profile.level, profile.eligible_level)
            chain = list(RoadmapMission.objects.filter(student=profile).order_by('sequence'))
            self.assertEqual([mission.title for mission in chain], [item['title'] for item in LEVEL_ONE_MISSIONS])
            previous = None
            for mission in chain:
                self.assertEqual(mission.prerequisite_id, previous.pk if previous else None)
                if mission.status in {RoadmapMission.Status.SUBMITTED, RoadmapMission.Status.COMPLETED} and previous:
                    self.assertEqual(previous.status, RoadmapMission.Status.COMPLETED)
                previous = mission

    def test_essays_hold_the_editors_document_format(self):
        essays = Essay.objects.select_related('application', 'folder').prefetch_related('tabs')
        self.assertTrue(essays.exists())
        for essay in essays:
            tabs = list(essay.tabs.all())
            self.assertEqual(len(tabs), 1)
            tab = tabs[0]
            self.assertEqual(validate_doc(tab.doc), tab.doc)
            stats = doc_stats(tab.doc)
            self.assertEqual(
                (tab.content, tab.word_count, tab.char_count, tab.char_count_no_spaces),
                (stats.content, stats.word_count, stats.char_count, stats.char_count_no_spaces),
            )
            self.assertEqual((essay.content, essay.word_count, essay.preview), stats[:3])
            if essay.application_id:
                self.assertEqual(essay.application.student_id, essay.student_id)
            if essay.folder_id:
                self.assertEqual(essay.folder.student_id, essay.student_id)

    def test_every_seeded_row_passes_model_validation(self):
        models = [*apps.get_app_config('admissions').get_models(), User]
        for model in models:
            for instance in model.objects.all()[:3]:
                with self.subTest(model=model.__name__, pk=instance.pk):
                    instance.full_clean()
