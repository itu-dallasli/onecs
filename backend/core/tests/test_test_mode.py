"""The synthetic admin bypass and effective-user simulation are disjoint."""

from django.test import override_settings
from core.models import AuditEvent, WorkItem
from core.tests.base import AtlasTestCase


class TestIdentityFlowTests(AtlasTestCase):
    def private_work(self):
        return WorkItem.objects.create(
            title="Private other-unit task",
            created_by=self.other_head,
            assigned_to=self.outsider,
            owner_org=self.other_unit,
        )

    @override_settings(ATLAS_ENV="demo", ATLAS_TEST_GOD_MODE=True)
    def test_god_mode_simulation_and_exit_keep_the_real_actor(self):
        hidden = self.private_work()
        self.as_user(self.admin)
        self.assertEqual(
            self.client.post(
                "/api/v1/test-mode/", {"mode": "god"}, format="json"
            ).status_code,
            200,
        )
        response = self.client.get(f"/api/v1/work/{hidden.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            self.client.post(
                "/api/v1/test-mode/",
                {"mode": "simulate", "user_id": str(self.employee.pk)},
                format="json",
            ).status_code,
            200,
        )
        me = self.client.get("/api/v1/auth/me/").json()
        self.assertEqual(me["id"], str(self.employee.pk))
        self.assertFalse(me["permissions"]["system_admin"])
        self.assertFalse(me["test_mode"]["god_mode"])
        self.assertEqual(me["test_mode"]["real_actor_id"], str(self.admin.pk))
        self.assertEqual(self.client.get(f"/api/v1/work/{hidden.pk}/").status_code, 404)
        created = self.client.post(
            "/api/v1/work/",
            {"title": "Simulated personal task", "personal": True},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        event = AuditEvent.objects.get(
            action="work.created", object_id=created.json()["id"]
        )
        self.assertEqual(event.actor_id, self.employee.pk)
        self.assertEqual(event.real_actor_id, self.admin.pk)
        stopped = self.client.post(
            "/api/v1/test-mode/", {"mode": "stop"}, format="json"
        )
        self.assertEqual(stopped.status_code, 200, stopped.content)
        self.assertEqual(
            self.client.get("/api/v1/auth/me/").json()["id"], str(self.admin.pk)
        )
        self.assertEqual(self.client.get(f"/api/v1/work/{hidden.pk}/").status_code, 404)

    @override_settings(ATLAS_ENV="production", ATLAS_TEST_GOD_MODE=True)
    def test_production_cannot_activate_bypass_even_with_a_test_flag(self):
        hidden = self.private_work()
        self.as_user(self.admin)
        response = self.client.post(
            "/api/v1/test-mode/", {"mode": "god"}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        session = self.client.session
        session["atlas_god_mode"] = True
        session.save()
        self.assertEqual(self.client.get(f"/api/v1/work/{hidden.pk}/").status_code, 404)
