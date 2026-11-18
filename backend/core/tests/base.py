"""Synthetic organization shared by Atlas policy and workflow tests."""

from django.test import TestCase
from rest_framework.test import APIClient

from core.models import OrgNode, PMAppointment, RoleGrant, User


class AtlasTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.directorate = OrgNode.objects.create(
            code="ICT-CS", name="Siber Güvenlik", kind="DIRECTORATE"
        )
        cls.unit = OrgNode.objects.create(
            code="ICT-CS-OS",
            name="Offensive Security",
            kind="UNIT",
            parent=cls.directorate,
        )
        cls.team = OrgNode.objects.create(
            code="ICT-CS-OS-AST",
            name="Application Security",
            kind="TEAM",
            parent=cls.unit,
        )
        cls.other_unit = OrgNode.objects.create(
            code="ICT-CS-IAM", name="Identity", kind="UNIT", parent=cls.directorate
        )
        cls.pm_unit = OrgNode.objects.create(
            code="ICT-CS-PMO",
            name="Project Office",
            kind="UNIT",
            parent=cls.directorate,
        )

        def person(username, org, role=None, role_org=None):
            user = User.objects.create_user(
                username=username,
                password=None,
                email=f"{username}@atlas.example.test",
                display_name=username.title(),
                primary_org=org,
            )
            RoleGrant.objects.create(user=user, role="EMPLOYEE", org_node=org)
            if role:
                RoleGrant.objects.create(user=user, role=role, org_node=role_org or org)
            return user

        cls.director = person("director", cls.directorate, "DIRECTOR")
        cls.unit_head = person("unit-head", cls.unit, "UNIT_HEAD")
        cls.team_manager = person("team-manager", cls.team, "TEAM_MANAGER")
        cls.employee = person("employee", cls.team)
        cls.colleague = person("colleague", cls.team)
        cls.direct_employee = person("unit-employee", cls.unit)
        cls.other_head = person("other-head", cls.other_unit, "UNIT_HEAD")
        cls.outsider = person("outsider", cls.other_unit)
        cls.pm_head = person("pm-head", cls.pm_unit, "UNIT_HEAD")
        cls.pm = person("project-manager", cls.pm_unit)
        cls.admin = person("system-admin", cls.directorate, "SYSTEM_ADMIN")
        cls.appointment = PMAppointment.objects.create(
            user=cls.pm, governing_org=cls.pm_unit
        )

    def setUp(self):
        self.client = APIClient()

    def as_user(self, user):
        # Exercise the real session path, including Django's request.user used
        # by the transaction/idempotency wrapper before DRF dispatch.
        self.client.force_login(user)
        return self.client

    @staticmethod
    def rows(response):
        """Accept a paginated collection without coupling tests to page size."""
        data = response.json()
        return data.get("results", data) if isinstance(data, dict) else data
