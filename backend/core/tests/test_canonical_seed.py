"""The reference directory is explicit; synthetic people are labelled as demo."""

import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from core.models import Case, OrgNode, Project, RoleGrant, User, WorkItem


class CanonicalSeedTests(TestCase):
    expected_managers = {
        "ICT-CS-IS": ("infrastructure_head", "Hakan Tokay"),
        "ICT-CS-SAA": ("assurance_head", "Mert Deva"),
        "ICT-CS-CDC": ("cdchead", "Abdurrahman Şakar"),
        "ICT-CS-IAM": ("iamhead", "Alper Eryılmaz"),
        "ICT-CS-OS": ("unithead", "Necati Ersen Şişeci"),
        "ICT-CS-SM": ("pm_head", "Kerem Kılıç"),
        "ICT-CS-MSS": ("infrastructure_head", "Hakan Tokay"),
    }
    expected_demo_people = {
        "demo_os": "ICT-CS-OS",
        "iamemployee": "ICT-CS-IAM",
        "demo_is": "ICT-CS-IS",
        "demo_saa": "ICT-CS-SAA",
        "demo_cdc": "ICT-CS-CDC",
        "demo_sm": "ICT-CS-SM",
        "demo_mss": "ICT-CS-MSS",
    }

    def setUp(self):
        self.environment = patch.dict(
            os.environ, {"ONECS_DEMO_PASSWORD": "Onecs-canonical-test-2026!"}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def seed(self, **options):
        call_command("seed_demo", stdout=StringIO(), stderr=StringIO(), **options)

    def test_default_directory_has_seven_reference_units_and_six_unique_unit_managers(self):
        self.seed()
        root = OrgNode.objects.get(code="ICT-CS")
        self.assertEqual(root.kind, "DIRECTORATE")
        self.assertFalse(root.is_demo)
        units = OrgNode.objects.filter(kind="UNIT", active=True)
        self.assertSetEqual(set(units.values_list("code", flat=True)), set(self.expected_managers))
        self.assertFalse(units.filter(is_demo=True).exists())
        ast = OrgNode.objects.get(code="ICT-CS-OS-AST")
        self.assertEqual(ast.kind, "TEAM")
        self.assertEqual(ast.parent.code, "ICT-CS-OS")
        self.assertFalse(ast.is_demo)
        team_manager = RoleGrant.objects.get(role="TEAM_MANAGER", org_node=ast, active=True).user
        self.assertEqual(team_manager.display_name, "Emre Uzun")
        self.assertEqual(team_manager.profile_kind, "OFFICIAL_REFERENCE")
        for code, (username, display_name) in self.expected_managers.items():
            with self.subTest(unit=code):
                unit = units.get(code=code)
                self.assertEqual(unit.parent_id, root.pk)
                grants = RoleGrant.objects.filter(role="UNIT_HEAD", org_node=unit, active=True)
                self.assertEqual(grants.count(), 1)
                manager = grants.get().user
                self.assertEqual(manager.username, username)
                self.assertEqual(manager.display_name, display_name)
                self.assertEqual(manager.profile_kind, "OFFICIAL_REFERENCE")
        self.assertEqual(RoleGrant.objects.filter(role="UNIT_HEAD", active=True).values("user_id").distinct().count(), 6)
        hakan = User.objects.get(username="infrastructure_head")
        self.assertEqual(User.objects.filter(display_name="Hakan Tokay").count(), 1)
        self.assertSetEqual(set(hakan.role_grants.filter(role="UNIT_HEAD", active=True).values_list("org_node__code", flat=True)), {"ICT-CS-IS", "ICT-CS-MSS"})
        director = User.objects.get(username="director")
        self.assertEqual(director.display_name, "Emin İslam Tatlı")
        self.assertEqual(director.profile_kind, "OFFICIAL_REFERENCE")
        self.assertTrue(director.role_grants.filter(role="DIRECTOR", org_node=root, active=True).exists())

    def test_default_examples_are_labelled_demo_without_a_fabricated_large_directory(self):
        self.seed()
        self.assertLess(User.objects.count(), 50)
        self.assertFalse(User.objects.filter(username__iregex=r"^cs[0-9]{3}$").exists())
        for username, code in self.expected_demo_people.items():
            with self.subTest(username=username):
                person = User.objects.get(username=username)
                self.assertEqual(person.primary_org.code, code)
                self.assertEqual(person.profile_kind, "DEMO")
                self.assertIn("DEMO", person.display_name.upper())
        for username in ("admin", "fulladmin"):
            self.assertEqual(User.objects.get(username=username).profile_kind, "DEMO")
        employee = User.objects.get(username="employee")
        self.assertEqual(employee.display_name, "Muhammed Eren Uygun")
        self.assertEqual(employee.profile_kind, "OFFICIAL_REFERENCE")
        self.assertEqual(employee.primary_org.code, "ICT-CS-OS-AST")
        manager_ids = RoleGrant.objects.filter(role="TEAM_MANAGER", org_node__code="ICT-CS-OS-AST", active=True).values_list("user_id", flat=True)
        reference_people = User.objects.filter(primary_org__code="ICT-CS-OS-AST", profile_kind="OFFICIAL_REFERENCE").exclude(username="employee").exclude(pk__in=manager_ids)
        self.assertEqual(reference_people.count(), 12)
        self.assertTrue(all(not person.has_usable_password() for person in reference_people))

    def test_optional_demo_team_is_explicit_and_does_not_add_a_reference_unit(self):
        self.seed(with_demo_team=True)
        self.assertEqual(OrgNode.objects.filter(kind="UNIT", active=True).count(), 7)
        team = OrgNode.objects.get(kind="TEAM", is_demo=True)
        self.assertEqual(team.parent.code, "ICT-CS-OS")
        self.assertIn("DEMO", team.name.upper())
        grant = RoleGrant.objects.get(role="TEAM_MANAGER", org_node=team, active=True)
        self.assertEqual(grant.user.profile_kind, "DEMO")
        self.assertIn("DEMO", grant.user.display_name.upper())
        self.assertTrue(OrgNode.objects.filter(code="ICT-CS-OS-AST", is_demo=False).exists())

    def test_rerunning_seed_keeps_existing_password_and_workflow_state(self):
        self.seed()
        user = User.objects.get(username="employee")
        user.set_password("A-user-changed-password-2026!")
        user.save()
        work = WorkItem.objects.first()
        project = Project.objects.first()
        self.assertIsNotNone(work)
        self.assertIsNotNone(project)
        WorkItem.objects.filter(pk=work.pk).update(status="WAITING", blocker="Keep this real progress")
        Project.objects.filter(pk=project.pk).update(status="IN_PROGRESS", progress=37)
        models = (User, OrgNode, WorkItem, Project, Case)
        before = tuple(model.objects.count() for model in models)
        self.seed()
        self.assertEqual(tuple(model.objects.count() for model in models), before)
        user.refresh_from_db()
        work.refresh_from_db()
        project.refresh_from_db()
        self.assertTrue(user.check_password("A-user-changed-password-2026!"))
        self.assertEqual(work.status, "WAITING")
        self.assertEqual(work.blocker, "Keep this real progress")
        self.assertEqual(project.status, "IN_PROGRESS")
        self.assertEqual(project.progress, 37)

    def test_legacy_unit_is_reported_without_deleting_or_partially_reseeding(self):
        legacy = OrgNode.objects.create(code="ICT-CS-PMO", name="Legacy directory", kind="UNIT")
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(OrgNode.objects.count(), 1)
        self.assertTrue(OrgNode.objects.filter(pk=legacy.pk).exists())
        self.assertFalse(User.objects.exists())

    def test_legacy_generated_account_is_reported_without_deletion(self):
        org = OrgNode.objects.create(code="ICT-CS-OS", name="Existing unit", kind="UNIT")
        legacy = User.objects.create_user(username="cs001", primary_org=org, display_name="Legacy synthetic account")
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(User.objects.count(), 1)
        self.assertTrue(User.objects.filter(pk=legacy.pk).exists())
        self.assertEqual(OrgNode.objects.count(), 1)
