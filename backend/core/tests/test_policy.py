"""Organization relationships must not grant implicit project authority."""

from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone

from core.models import (
    Case,
    CommunityCard,
    ProgressEntry,
    Project,
    ProjectAuthorityGrant,
    ProjectMembership,
    ProjectRevision,
    RoleGrant,
    WorkItem,
)
from core.policy import (
    can_approve_project,
    can_manage_org,
    can_manage_project,
    can_manage_work,
    can_open_case,
    can_read_case,
    can_read_progress,
    can_read_project,
    can_read_project_detail,
    can_read_work,
    manager_scope_ids,
    visible_cases,
    visible_cards,
    visible_projects,
    visible_work,
    report_source,
)
from core.serializers import ProjectSerializer
from core.tests.base import AtlasTestCase


class OrganizationPolicyTests(AtlasTestCase):
    def test_hierarchy_includes_direct_unit_employee_and_nested_team(self):
        self.assertTrue(can_manage_org(self.unit_head, self.unit))
        self.assertTrue(can_manage_org(self.unit_head, self.team))
        self.assertTrue(can_manage_org(self.team_manager, self.team))
        self.assertFalse(can_manage_org(self.team_manager, self.unit))
        self.assertFalse(can_manage_org(self.unit_head, self.other_unit))
        self.assertFalse(can_manage_org(self.employee, self.team))
        self.assertTrue(can_manage_org(self.director, self.other_unit))

    def test_role_scope_uses_relations_not_organization_code_prefix(self):
        self.other_unit.code = "ICT-CS-OS-PREFIX-TRAP"
        self.other_unit.save()
        self.team.code = "UNRELATED-DISPLAY-CODE"
        self.team.save()
        self.assertFalse(can_manage_org(self.unit_head, self.other_unit))
        self.assertTrue(can_manage_org(self.unit_head, self.team))

    def test_expired_and_disabled_grants_do_not_manage_children(self):
        grant = self.unit_head.role_grants.get(role="UNIT_HEAD")
        grant.expires_at = timezone.now() - timedelta(seconds=1)
        grant.save()
        self.assertEqual(manager_scope_ids(self.unit_head), set())
        grant.expires_at = None
        grant.active = False
        grant.save()
        self.assertFalse(can_manage_org(self.unit_head, self.unit))

    def test_non_descending_grant_stops_at_exact_organization(self):
        grant = self.unit_head.role_grants.get(role="UNIT_HEAD")
        grant.includes_descendants = False
        grant.save()
        self.assertTrue(can_manage_org(self.unit_head, self.unit))
        self.assertFalse(can_manage_org(self.unit_head, self.team))

    def test_inactive_actor_loses_organization_authority(self):
        self.unit_head.is_active = False
        self.unit_head.save()
        self.assertFalse(can_manage_org(self.unit_head, self.unit))
        self.assertEqual(manager_scope_ids(self.unit_head), set())

    def test_case_opening_is_not_ordinary_team_manager_authority(self):
        self.assertTrue(can_open_case(self.unit_head, self.team))
        self.assertTrue(can_open_case(self.director, self.unit))
        self.assertFalse(can_open_case(self.team_manager, self.team))
        self.assertFalse(can_open_case(self.employee, self.team))
        self.assertFalse(can_open_case(self.unit_head, self.other_unit))
        grant = self.team_manager.role_grants.get(role="TEAM_MANAGER")
        grant.permissions = ["case.create"]
        grant.save()
        self.assertTrue(can_open_case(self.team_manager, self.team))
        self.assertFalse(can_open_case(self.team_manager, self.other_unit))
        grant.expires_at = timezone.now() - timedelta(seconds=1)
        grant.save()
        self.assertFalse(can_open_case(self.team_manager, self.team))

    def test_case_creation_delegation_respects_non_descending_scope(self):
        grant = RoleGrant.objects.create(
            user=self.employee,
            role="CASE_CREATOR",
            org_node=self.unit,
            includes_descendants=False,
            permissions=["case.create"],
        )
        self.assertTrue(can_open_case(self.employee, self.unit))
        self.assertFalse(can_open_case(self.employee, self.team))
        grant.includes_descendants = True
        grant.save()
        self.assertTrue(can_open_case(self.employee, self.team))


class ProjectAuthorityTests(AtlasTestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            title="Cross-team programme",
            created_by=self.employee,
            owner_org=self.unit,
            appointment=self.appointment,
            status="SUBMITTED",
        )

    def test_pm_and_governing_unit_head_manage_but_contributing_unit_head_does_not(
        self,
    ):
        self.assertTrue(can_manage_project(self.pm, self.project))
        self.assertTrue(can_manage_project(self.pm_head, self.project))
        self.assertFalse(can_manage_project(self.unit_head, self.project))
        self.assertFalse(can_manage_project(self.team_manager, self.project))
        self.assertFalse(can_manage_project(self.employee, self.project))
        self.assertFalse(can_manage_project(self.admin, self.project))

    def test_director_read_role_is_not_implicit_project_approval(self):
        self.project.status = "PLANNED"
        self.project.published_revision = 1
        self.project.save()
        self.assertTrue(can_read_project(self.director, self.project))
        self.assertFalse(can_approve_project(self.director, self.project))

    def test_self_approval_uses_person_not_current_role(self):
        self.project.created_by = self.pm
        self.project.save()
        RoleGrant.objects.create(user=self.pm, role="UNIT_HEAD", org_node=self.pm_unit)
        self.assertTrue(can_manage_project(self.pm, self.project))
        self.assertFalse(can_approve_project(self.pm, self.project))
        self.assertTrue(can_approve_project(self.pm_head, self.project))

    def test_scoped_delegate_does_not_gain_unlisted_permissions(self):
        ProjectAuthorityGrant.objects.create(
            project=self.project,
            user=self.colleague,
            granted_by=self.pm,
            permissions=["read"],
            expires_at=timezone.now() + timedelta(days=1),
            reason="Read-only substitution",
        )
        self.assertTrue(can_manage_project(self.colleague, self.project, "read"))
        self.assertFalse(can_manage_project(self.colleague, self.project, "manage"))
        self.assertFalse(can_approve_project(self.colleague, self.project))

    def test_expired_delegate_and_revoked_grantor_are_rejected(self):
        grant = ProjectAuthorityGrant.objects.create(
            project=self.project,
            user=self.colleague,
            granted_by=self.pm_head,
            permissions=["approve"],
            expires_at=timezone.now() + timedelta(days=1),
            reason="Leave coverage",
        )
        self.assertTrue(can_approve_project(self.colleague, self.project))
        grant.expires_at = timezone.now() - timedelta(seconds=1)
        grant.save()
        self.assertFalse(can_approve_project(self.colleague, self.project))
        grant.expires_at = timezone.now() + timedelta(days=1)
        grant.save()
        self.pm_head.role_grants.filter(role="UNIT_HEAD").update(active=False)
        self.assertFalse(can_approve_project(self.colleague, self.project))

    def test_inactive_delegate_and_inactive_grantor_are_rejected(self):
        ProjectAuthorityGrant.objects.create(
            project=self.project,
            user=self.colleague,
            granted_by=self.pm_head,
            permissions=["manage"],
            expires_at=timezone.now() + timedelta(days=1),
            reason="Coverage",
        )
        self.colleague.is_active = False
        self.colleague.save()
        self.assertFalse(can_manage_project(self.colleague, self.project))
        self.colleague.is_active = True
        self.colleague.save()
        self.pm_head.is_active = False
        self.pm_head.save()
        self.assertFalse(can_manage_project(self.colleague, self.project))

    def test_pm_transfer_or_disable_does_not_leave_old_delegate_authority(self):
        ProjectAuthorityGrant.objects.create(
            project=self.project,
            user=self.colleague,
            granted_by=self.pm,
            permissions=["manage"],
            expires_at=timezone.now() + timedelta(days=1),
            reason="Coverage",
        )
        self.appointment.active = False
        self.appointment.save()
        self.assertFalse(can_manage_project(self.pm, self.project))
        self.assertFalse(can_manage_project(self.pm_head, self.project))
        self.assertFalse(can_manage_project(self.colleague, self.project))

    def test_private_draft_is_not_visible_to_pm_before_submission(self):
        self.project.status = "DRAFT"
        self.project.save()
        self.assertTrue(can_read_project(self.employee, self.project))
        self.assertFalse(can_read_project(self.pm, self.project))
        self.assertFalse(can_read_project(self.unit_head, self.project))


class ResourceVisibilityTests(AtlasTestCase):
    def test_other_unit_work_and_case_do_not_appear_in_employee_collections(self):
        own = WorkItem.objects.create(
            title="My task",
            created_by=self.unit_head,
            assigned_to=self.employee,
            owner_org=self.team,
        )
        hidden = WorkItem.objects.create(
            title="Hidden identity remediation",
            created_by=self.other_head,
            assigned_to=self.outsider,
            owner_org=self.other_unit,
        )
        hidden_case = Case.objects.create(
            title="Hidden case",
            created_by=self.other_head,
            coordinator=self.other_head,
            owner_org=self.other_unit,
        )
        self.assertSetEqual(
            set(visible_work(self.employee).values_list("id", flat=True)), {own.pk}
        )
        self.assertFalse(can_read_work(self.employee, hidden))
        self.assertFalse(
            visible_cases(self.employee).filter(pk=hidden_case.pk).exists()
        )

    def test_org_manager_does_not_manage_project_task_by_subordinate_assignment(self):
        project = Project.objects.create(
            title="Programme",
            created_by=self.employee,
            owner_org=self.unit,
            appointment=self.appointment,
            status="PLANNED",
            published_revision=1,
        )
        project.audience.add(self.unit)
        work = WorkItem.objects.create(
            title="Project action",
            created_by=self.pm,
            assigned_to=self.employee,
            owner_org=self.team,
            project=project,
            context="PROJECT_TASK",
        )
        self.assertTrue(can_read_project(self.unit_head, project))
        self.assertFalse(can_manage_work(self.unit_head, work))
        self.assertTrue(can_manage_work(self.pm, work))

    def test_submitted_proposal_is_hidden_from_employee_normal_manager(self):
        proposal = Project.objects.create(
            title="Private proposal",
            created_by=self.employee,
            owner_org=self.unit,
            appointment=self.appointment,
            status="SUBMITTED",
        )
        self.assertFalse(
            visible_projects(self.unit_head).filter(pk=proposal.pk).exists()
        )
        self.assertTrue(visible_projects(self.pm).filter(pk=proposal.pk).exists())

    def test_inactive_actor_cannot_read_previous_memberships_or_worker_report_sources(
        self,
    ):
        project = Project.objects.create(
            title="Previously readable",
            created_by=self.employee,
            owner_org=self.unit,
            appointment=self.appointment,
            status="PLANNED",
            published_revision=1,
        )
        ProjectMembership.objects.create(
            project=project, user=self.employee, accepted_by=self.unit_head
        )
        work = WorkItem.objects.create(
            title="Previously assigned",
            assigned_to=self.employee,
            created_by=self.unit_head,
            owner_org=self.team,
        )
        case = Case.objects.create(
            title="Previously coordinated",
            coordinator=self.employee,
            created_by=self.unit_head,
            owner_org=self.unit,
        )
        entry = ProgressEntry.objects.create(
            project=project,
            author=self.employee,
            author_org=self.team,
            done="Historical work",
        )
        CommunityCard.objects.create(
            title="Public card",
            body="Safe public text",
            created_by=self.unit_head,
            owner_org=self.unit,
            status="PUBLISHED",
            all_cs=True,
        )
        self.assertTrue(can_read_project(self.employee, project))
        self.assertTrue(can_read_work(self.employee, work))
        self.employee.is_active = False
        self.employee.save()
        self.assertFalse(can_read_project(self.employee, project))
        self.assertFalse(can_read_project_detail(self.employee, project))
        self.assertFalse(can_read_work(self.employee, work))
        self.assertFalse(can_read_case(self.employee, case))
        self.assertFalse(can_read_progress(self.employee, entry))
        for selector in (visible_projects, visible_work, visible_cases, visible_cards):
            self.assertFalse(selector(self.employee).exists())
        for kind, obj in (("project", project), ("work", work), ("case", case)):
            self.assertIsNone(report_source(self.employee, kind, obj.pk))


class PublishedProjectPrivacyTests(AtlasTestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            title="Unpublished internal title",
            description="RAW_INTERNAL_DESCRIPTION",
            expected_outcome="RAW_INTERNAL_OUTCOME",
            approval_note="PRIVATE_APPROVAL_NOTE",
            progress_note="PRIVATE_PROGRESS_NOTE",
            created_by=self.employee,
            owner_org=self.unit,
            appointment=self.appointment,
            status="IN_PROGRESS",
            published_revision=1,
        )
        self.project.audience.add(self.unit)
        ProjectRevision.objects.create(
            project=self.project,
            number=1,
            author=self.employee,
            decision="APPROVE",
            content={
                "title": "Approved programme summary",
                "expected_outcome": "Approved shareable outcome",
                "description": "PRIVATE_REVISION_DESCRIPTION",
            },
        )
        ProjectMembership.objects.create(
            project=self.project, user=self.employee, accepted_by=self.unit_head
        )
        ProjectMembership.objects.create(
            project=self.project, user=self.outsider, accepted_by=self.other_head
        )
        self.own_entry = ProgressEntry.objects.create(
            project=self.project,
            author=self.employee,
            author_org=self.team,
            done="OWN_TEAM_PROGRESS",
        )
        self.other_entry = ProgressEntry.objects.create(
            project=self.project,
            author=self.outsider,
            author_org=self.other_unit,
            done="OTHER_TEAM_PRIVATE_PROGRESS",
        )

    def serialized_for(self, user):
        return ProjectSerializer(
            self.project, context={"request": SimpleNamespace(user=user)}
        ).data

    def test_audience_nonmember_gets_only_reviewed_summary(self):
        self.assertTrue(can_read_project(self.colleague, self.project))
        self.assertFalse(can_read_project_detail(self.colleague, self.project))
        data = self.serialized_for(self.colleague)
        self.assertEqual(data["visibility"], "SUMMARY")
        self.assertEqual(data["title"], "Approved programme summary")
        self.assertEqual(data["expected_outcome"], "Approved shareable outcome")
        self.assertEqual(data["members"], [])
        self.assertEqual(data["contributions"], [])
        self.assertEqual(data["audience_ids"], [])
        for private_value in (
            "RAW_INTERNAL_DESCRIPTION",
            "RAW_INTERNAL_OUTCOME",
            "PRIVATE_APPROVAL_NOTE",
            "PRIVATE_PROGRESS_NOTE",
            "PRIVATE_REVISION_DESCRIPTION",
            "OWN_TEAM_PROGRESS",
            "OTHER_TEAM_PRIVATE_PROGRESS",
        ):
            self.assertNotIn(private_value, str(data))
        self.assertFalse(data["permissions"]["manage"])
        self.assertFalse(data["permissions"]["approve"])

    def test_resource_manager_sees_only_own_accepted_members_and_their_contributions(
        self,
    ):
        self.assertTrue(can_read_project(self.unit_head, self.project))
        self.assertFalse(can_read_project_detail(self.unit_head, self.project))
        data = self.serialized_for(self.unit_head)
        self.assertEqual(data["visibility"], "SUMMARY")
        self.assertSetEqual(
            {str(row["id"]) for row in data["members"]}, {str(self.employee.pk)}
        )
        self.assertSetEqual(
            {str(row["id"]) for row in data["contributions"]}, {str(self.own_entry.pk)}
        )
        self.assertNotIn("OTHER_TEAM_PRIVATE_PROGRESS", str(data))
        self.assertNotIn("PRIVATE_APPROVAL_NOTE", str(data))

    def test_pm_keeps_detailed_view_for_project_delivery(self):
        data = self.serialized_for(self.pm)
        self.assertEqual(data["visibility"], "DETAIL")
        self.assertEqual(data["description"], "RAW_INTERNAL_DESCRIPTION")
        self.assertEqual(len(data["members"]), 2)
        self.assertEqual(len(data["contributions"]), 2)
