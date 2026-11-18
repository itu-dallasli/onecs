"""Project routing remains recoverable after an accountable PM leaves."""

from core.models import PMAppointment, Project, User
from core.policy import can_approve_project, can_read_project, can_reroute_project
from core.tests.base import AtlasTestCase


class ProjectContinuityTests(AtlasTestCase):
    def proposal(self, status="SUBMITTED"):
        return Project.objects.create(
            title="Pending charter",
            description="A scoped proposal",
            created_by=self.employee,
            owner_org=self.unit,
            appointment=self.appointment,
            status=status,
        )

    def test_unit_governing_pm_can_reroute_disabled_pm_but_cannot_publish(self):
        project = self.proposal()
        self.pm.is_active = False
        self.pm.save(update_fields=["is_active"])
        project.refresh_from_db()
        self.assertTrue(can_read_project(self.pm_head, project))
        self.assertTrue(can_reroute_project(self.pm_head, project))
        self.assertFalse(can_approve_project(self.pm_head, project))
        replacement = User.objects.create_user(
            username="replacement-pm", primary_org=self.pm_unit
        )
        appointment = PMAppointment.objects.create(
            user=replacement, governing_org=self.pm_unit
        )
        response = self.as_user(self.pm_head).post(
            f"/api/v1/projects/{project.pk}/transfer/",
            {
                "version": project.version,
                "appointment_id": str(appointment.pk),
                "reason": "PM account retired",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        project.refresh_from_db()
        self.assertEqual(project.appointment_id, appointment.pk)
        self.assertFalse(can_read_project(self.pm, project))

    def test_other_unit_head_cannot_take_over_disabled_pm_project(self):
        project = self.proposal()
        self.pm.is_active = False
        self.pm.save(update_fields=["is_active"])
        project.refresh_from_db()
        self.assertFalse(can_reroute_project(self.other_head, project))
        self.assertFalse(can_read_project(self.other_head, project))
        response = self.as_user(self.other_head).post(
            f"/api/v1/projects/{project.pk}/transfer/",
            {
                "version": project.version,
                "appointment_id": str(self.appointment.pk),
                "reason": "Unauthorized",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_recovery_authority_does_not_expose_unsent_private_drafts(self):
        project = self.proposal("DRAFT")
        self.pm.is_active = False
        self.pm.save(update_fields=["is_active"])
        project.refresh_from_db()
        self.assertFalse(can_read_project(self.pm_head, project))
        self.assertFalse(can_read_project(self.director, project))
