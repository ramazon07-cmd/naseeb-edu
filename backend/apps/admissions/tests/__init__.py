"""Admissions API tests, split by domain.

The former ``tests.RoleIsolationTests`` class is now one fixture
(``base.RoleIsolationBase``) plus a test class per domain module. Every old
name stays importable from ``apps.admissions.tests``: ``RoleIsolationTests``
is re-assembled below from the domain classes, so labels such as
``apps.admissions.tests.RoleIsolationTests.test_student_only_lists_own_profile``
still run. ``load_tests`` makes discovery load each test exactly once (from
its module), never the re-exported aliases.
"""
import importlib
import pkgutil
import unittest

from .base import RoleIsolationBase  # noqa: F401
from .test_accounts import AccountRoleIsolationTests
from .test_assignment import AssignmentRoleIsolationTests
from .test_assistant import AssistantRoleIsolationTests
from .test_catalog_research import CatalogResearchRoleIsolationTests
from .test_messaging import MessagingRoleIsolationTests
from .test_organizations import OrganizationRoleIsolationTests
from .test_parents import ParentRoleIsolationTests
from .test_portal import PortalRoleIsolationTests
from .test_public_reach import PublicReachTests  # noqa: F401
from .test_records import RecordRoleIsolationTests
from .test_roadmaps import RoadmapRoleIsolationTests
from .test_school_regions import SchoolRegionWritePermissionTests  # noqa: F401
from .test_support import SupportRoleIsolationTests


class RoleIsolationTests(
    AccountRoleIsolationTests,
    RecordRoleIsolationTests,
    OrganizationRoleIsolationTests,
    AssignmentRoleIsolationTests,
    RoadmapRoleIsolationTests,
    MessagingRoleIsolationTests,
    PortalRoleIsolationTests,
    CatalogResearchRoleIsolationTests,
    AssistantRoleIsolationTests,
    SupportRoleIsolationTests,
    ParentRoleIsolationTests,
):
    """Backwards-compatible alias with every former RoleIsolationTests test."""


def load_tests(loader, standard_tests, pattern):
    # Every test module in this package, so a new file can never be skipped
    # by the full run just because nobody listed it here.
    suite = unittest.TestSuite()
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda item: item.name):
        if info.name.startswith('test'):
            suite.addTests(loader.loadTestsFromModule(importlib.import_module(f'{__name__}.{info.name}')))
    return suite
