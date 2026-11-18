"""Showcase data must be useful, connected and safe to rerun."""

from io import StringIO
from unittest import skipUnless

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from core.management.commands.seed_showcase import fixture_id
from core.models import (
    Announcement, AuditEvent, BackgroundJob, Case, CommunityCard, Event,
    EventAttendance, EventRSVP, Notification, OrgNode, OutboxEvent, PMAppointment,
    PollResponse, ProgressEntry, Project, ProjectMembership, ProjectRevision,
    Report, RoleGrant, User, WorkItem,
)
from core.showcase_catalog import DEMO_FOOTER, PEOPLE, PROJECTS

HAS_INSIGHTS = any(m.__name__ == "ProjectTeamPlan" for m in apps.get_models())


@override_settings(ATLAS_ENV="test")
class ShowcaseSeedTests(TestCase):
    def setUp(self):
        self.root = OrgNode.objects.create(code="ICT-CS", name="Cyber Security", kind="DIRECTORATE")
        self.units = {code: OrgNode.objects.create(code=f"ICT-CS-{code}", name=code, parent=self.root) for code in PEOPLE}
        self.people = {}
        for code, username in {**PEOPLE, "PM": "pm", "PUB": "fulladmin"}.items():
            user = User.objects.create_user(
                username=username, password="Example-test-password-2026!", profile_kind="DEMO",
                display_name=f"Demo · {code}", primary_org=self.units.get(code, self.units["SM"]),
            )
            self.people[code] = user
            RoleGrant.objects.create(user=user, role="DIRECTOR" if code == "PUB" else "EMPLOYEE",
                                     org_node=self.root if code == "PUB" else user.primary_org)
        PMAppointment.objects.create(user=self.people["PM"], governing_org=self.units["SM"], name="Demo portföy")

    def seed(self, **options):
        call_command("seed_showcase", stdout=StringIO(), stderr=StringIO(), **options)

    def project(self, key):
        return Project.objects.get(pk=fixture_id(Project, key))

    def test_portfolio_has_different_stages_with_explorable_details(self):
        self.seed()
        self.assertEqual(Project.objects.count(), 8)
        self.assertEqual(CommunityCard.objects.count(), 5)
        self.assertEqual(Event.objects.count(), 3)
        self.assertEqual(Case.objects.count(), 2)
        self.assertEqual(Announcement.objects.filter(status="PUBLISHED").count(), 2)
        self.assertEqual(Announcement.objects.filter(status="DRAFT").count(), 1)
        self.assertEqual(Report.objects.count(), 1)
        self.assertGreater(EventRSVP.objects.count(), 12)
        self.assertEqual(EventAttendance.objects.count(), 8)
        self.assertEqual(PollResponse.objects.count(), 10)
        self.assertSetEqual(set(Project.objects.values_list("status", flat=True)),
                            {"SUBMITTED", "PLANNED", "IN_PROGRESS", "WAITING", "COMPLETED"})
        self.assertGreater(len(set(Project.objects.values_list("progress", flat=True))), 5)
        for spec in PROJECTS:
            project = self.project(spec.key)
            self.assertEqual(project.progress, spec.progress)
            self.assertIn(DEMO_FOOTER, project.description)
            self.assertGreater(len(project.expected_outcome), 60)
            self.assertFalse(project.title.startswith("QA-"))
            self.assertEqual(project.tasks.count(), sum(len(t.deliveries) for t in spec.teams))
            self.assertEqual(project.revisions.count(), 1)
            self.assertEqual(project.contributions.count(), 2 * len(spec.teams))
            if project.status == "COMPLETED":
                self.assertFalse(project.tasks.exclude(status="COMPLETED").exists())
                self.assertEqual(project.progress, 100)
            if project.status in ("PLANNED", "SUBMITTED"):
                self.assertEqual(project.progress, 0)
        for task in WorkItem.objects.filter(status="COMPLETED"):
            self.assertTrue(task.result)
            self.assertIsNotNone(task.completed_at)
            self.assertLess(task.created_at, task.completed_at)
        for task in WorkItem.objects.filter(status="WAITING"):
            self.assertTrue(task.blocker)
            self.assertTrue(task.contributions.last().next_step)
        closed = Case.objects.get(status="CLOSED")
        self.assertNotEqual(closed.coordinator_id, closed.verifier_id)
        self.assertLess(closed.created_at, closed.closed_at)
        self.assertTrue(closed.verification_evidence)

    def test_rerun_preserves_edits_children_identities_and_credentials(self):
        self.seed()
        project = self.project("pam")
        project.title = "Kullanıcının kendi proje başlığı"
        project.progress = 73
        project.status = "WAITING"
        project.save()
        task = project.tasks.first()
        task.assigned_to = self.people["IS"]
        task.blocker = "Kullanıcı tarafından eklenen bağımlılık"
        task.save()
        card = CommunityCard.objects.first()
        card.body = "Kullanıcının paylaşımı"
        card.save()
        report = Report.objects.first()
        report.markdown = "Kullanıcının rapor düzenlemesi"
        report.save()
        models = (Project, WorkItem, ProjectRevision, ProjectMembership, CommunityCard,
                  Announcement, Event, Case, ProgressEntry, AuditEvent, Notification, Report)
        counts = [m.objects.count() for m in models]
        identities = list(User.objects.order_by("pk").values())
        grants = list(RoleGrant.objects.order_by("pk").values())
        self.seed()
        self.assertEqual([m.objects.count() for m in models], counts)
        for obj in (project, task, card, report):
            obj.refresh_from_db()
        self.assertEqual(project.title, "Kullanıcının kendi proje başlığı")
        self.assertEqual(project.progress, 73)
        self.assertEqual(project.status, "WAITING")
        self.assertEqual(task.assigned_to_id, self.people["IS"].pk)
        self.assertEqual(task.blocker, "Kullanıcı tarafından eklenen bağımlılık")
        self.assertEqual(card.body, "Kullanıcının paylaşımı")
        self.assertEqual(report.markdown, "Kullanıcının rapor düzenlemesi")
        self.assertEqual(list(User.objects.order_by("pk").values()), identities)
        self.assertEqual(list(RoleGrant.objects.order_by("pk").values()), grants)
        self.assertFalse(OutboxEvent.objects.exists())
        self.assertFalse(BackgroundJob.objects.exists())

    def test_matching_user_title_is_never_adopted_or_rewritten(self):
        real_user = User.objects.create_user(username="actual_ldap_user", profile_kind="LDAP", identity_source="ldap")
        existing = Project.objects.create(
            title=PROJECTS[0].title, description="Gerçek kullanıcının kaydı", progress=17,
            created_by=real_user, owner_org=self.units["IAM"],
            appointment=PMAppointment.objects.get(user=self.people["PM"]),
        )
        self.seed()
        existing.refresh_from_db()
        self.assertEqual(existing.description, "Gerçek kullanıcının kaydı")
        self.assertEqual(existing.progress, 17)
        self.assertNotEqual(existing.pk, self.project("pam").pk)
        self.assertFalse(ProjectMembership.objects.filter(project=existing).exists())

    def test_ldap_account_with_demo_username_aborts_without_partial_writes(self):
        person = self.people["CDC"]
        person.profile_kind = "LDAP"
        person.identity_source = "ldap"
        person.save()
        with self.assertRaises(CommandError):
            self.seed()
        self.assertFalse(Project.objects.exists())
        self.assertFalse(AuditEvent.objects.exists())

    @override_settings(ATLAS_ENV="production")
    def test_production_seed_is_rejected(self):
        with self.assertRaises(CommandError):
            self.seed()
        self.assertFalse(Project.objects.exists())

    def test_legacy_card_polish_requires_exact_old_text_and_demo_owner(self):
        prefix = "Demo senaryosu: kurumsal iş, vaka veya personel kaydından alınmamıştır. "
        old = "Ortak API kontrol listesini paylaşmak ve diğer ekiplerin deneyimlerini dinlemek istiyoruz."
        title = "API güvenliğinde birlikte üretelim"
        pristine = CommunityCard.objects.create(title=title, body=prefix + old, created_by=self.people["OS"], owner_org=self.units["OS"])
        edited = CommunityCard.objects.create(title=title, body=prefix + old + " Kullanıcı ekledi.", created_by=self.people["OS"], owner_org=self.units["OS"])
        self.seed(polish_legacy_cards=True)
        pristine.refresh_from_db()
        edited.refresh_from_db()
        self.assertTrue(pristine.body.startswith("API yetkilendirme"))
        self.assertTrue(pristine.body.endswith(DEMO_FOOTER))
        self.assertTrue(edited.body.endswith("Kullanıcı ekledi."))
        body = pristine.body
        self.seed(polish_legacy_cards=True)
        pristine.refresh_from_db()
        self.assertEqual(pristine.body, body)

    @skipUnless(HAS_INSIGHTS, "Project insights is an optional feature")
    def test_deliveries_trends_surveys_and_reports_are_consistent(self):
        from core.project_insights import project_metrics
        Delivery = apps.get_model("core", "ProjectDeliverable")
        InsightReport = apps.get_model("core", "ProjectInsightReport")
        self.seed()
        for spec in PROJECTS:
            if not spec.teams:
                continue
            project = self.project(spec.key)
            teams, scores = project_metrics(project)
            self.assertEqual(round(scores["delivery"]), project.progress)
            self.assertEqual(sum(t["weight"] for t in teams), 100)
            self.assertEqual(project.progress_snapshots.count(), 3)
            trend = list(project.progress_snapshots.order_by("created_at").values_list("scores", flat=True))
            self.assertLessEqual(trend[0]["delivery"], trend[1]["delivery"])
            self.assertLessEqual(trend[1]["delivery"], trend[2]["delivery"])
            self.assertEqual(project.insight_reports.count(), 1)
            self.assertIn(DEMO_FOOTER, project.insight_reports.get().markdown)
        completed = self.project("access-pilot")
        _, scores = project_metrics(completed)
        self.assertIsNotNone(scores["overall"])
        self.assertEqual(scores["coverage"]["response_rate"], 100)
        self.assertEqual(completed.closure_surveys.count(), 1)
        report = InsightReport.objects.filter(project=completed).get()
        report.markdown = "Kullanıcının kapanış raporu"
        report.save()
        delivery = Delivery.objects.filter(plan__project=self.project("pam")).first()
        delivery.progress = 42
        delivery.save()
        counts = (Delivery.objects.count(), InsightReport.objects.count())
        self.seed()
        report.refresh_from_db()
        delivery.refresh_from_db()
        self.assertEqual(report.markdown, "Kullanıcının kapanış raporu")
        self.assertEqual(delivery.progress, 42)
        self.assertEqual((Delivery.objects.count(), InsightReport.objects.count()), counts)
