"""Add clearly fictional project metrics without resetting existing user edits."""

from datetime import timedelta
from uuid import uuid5, NAMESPACE_URL

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    OrgNode,
    PMAppointment,
    Project,
    ProjectClosureSurvey,
    ProjectDeliverable,
    ProjectInsightReport,
    ProjectMembership,
    ProjectRevision,
    ProjectSurveyResponse,
    ProjectTeamPlan,
    User,
    WorkItem,
)
from core.project_insights import fallback_markdown, record_progress, report_sources
from core.services import audit, contribute


class Command(BaseCommand):
    help = "Dört ekipli ilerleme ve kapanış anketi örneklerini ekler; mevcut kayıtları değiştirmez."

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.ONECS_ENV not in ("development", "demo", "test"):
            raise CommandError("Demo seed üretimde çalıştırılamaz.")
        pm = User.objects.filter(username="pm").first()
        appointment = PMAppointment.objects.filter(user=pm, active=True).first()
        if not appointment:
            raise CommandError("Önce seed_demo ile örnek organizasyonu kurun.")
        people = {
            code: User.objects.get(username=username)
            for code, username in [
                ("OS", "demo_os"),
                ("IAM", "iamemployee"),
                ("CDC", "demo_cdc"),
                ("SAA", "demo_saa"),
            ]
        }
        units = {code: OrgNode.objects.get(code=f"ICT-CS-{code}") for code in people}
        now = timezone.now()
        today = timezone.localdate()
        for completed in (False, True):
            title = (
                "Güvenli Erişim Pilot Kapanışı · Demo"
                if completed
                else "Kurumsal API Güvenliği Dönüşümü · Demo"
            )
            project, made = Project.objects.get_or_create(
                title=title,
                created_by=people["OS"],
                defaults={
                    "description": "Demo senaryosu: gerçek kurumsal proje veya ölçüm değildir. Dört ekibin teslimatlarını, kanıtlarını ve paydaş görüşünü tek yerde izler.",
                    "expected_outcome": "Ortak güvenlik kontrolleri, doğrulanmış teslimatlar ve gerekçeli kapanış değerlendirmesi.",
                    "owner_org": units["OS"],
                    "appointment": appointment,
                    "status": "COMPLETED" if completed else "IN_PROGRESS",
                    "priority": "HIGH",
                    "progress": 100 if completed else 62,
                    "progress_note": "Örnek PM beyanı; aşağıdaki ağırlıklı teslimat ölçümünden bağımsızdır.",
                    "due_at": now + timedelta(days=-1 if completed else 21),
                    "published_revision": 1,
                    "submitted_revision": 1,
                    "approved_by": pm,
                },
            )
            # All initialization is creation-only. Re-running cannot undo a demo
            # participant's edited report, score, answer, assignment or plan.
            if not made:
                continue
            project.audience.set(units.values())
            ProjectRevision.objects.create(
                project=project,
                number=1,
                author=people["OS"],
                decision="APPROVE",
                decided_by=pm,
                content={
                    "title": title,
                    "description": project.description,
                    "expected_outcome": project.expected_outcome,
                },
            )
            for code, person in people.items():
                ProjectMembership.objects.create(
                    project=project,
                    user=person,
                    accepted_by=pm,
                )
            # The signed-in reference employee has concrete project work to
            # inspect. This membership is fictional and explicitly labelled.
            employee = User.objects.get(username="employee")
            ProjectMembership.objects.create(
                project=project, user=employee, accepted_by=pm
            )
            specifications = [
                ("OS", "API test kapsamı", "Kritik bulgu yeniden testi", 85, 65, 5),
                (
                    "IAM",
                    "Servis hesabı envanteri",
                    "Süreli erişim kontrolleri",
                    70,
                    50,
                    4,
                ),
                ("CDC", "Tespit senaryoları", "Alarm doğrulama paketi", 60, 40, 4),
                ("SAA", "Kontrol eşleştirmesi", "Kapanış kanıt paketi", 50, 30, 3),
            ]
            for code, first, second, p1, p2, rating in specifications:
                plan = ProjectTeamPlan.objects.create(
                    project=project, org=units[code], weight=25
                )
                for index, (label, progress) in enumerate(((first, p1), (second, p2))):
                    ProjectDeliverable.objects.create(
                        plan=plan,
                        title=f"{label} · Örnek",
                        kind="MILESTONE" if index else "DELIVERABLE",
                        weight=60 if index == 0 else 40,
                        progress=100 if completed else progress,
                        evidence=f"Sentetik demo kanıtı: {code} kontrol listesi ve örnek doğrulama notu. Gerçek test sonucu değildir.",
                        quality_rating=rating if completed else None,
                        due_at=project.due_at,
                        updated_by=pm,
                    )
                contribute(
                    people[code],
                    project,
                    {
                        "done": f"Demo: {first} için örnek çıktı kaydedildi.",
                        "next_step": "Paydaş doğrulaması tamamlandı."
                        if completed
                        else f"Demo: {second} üzerinde çalışılacak.",
                    },
                )
            task = WorkItem.objects.create(
                title="API kontrol listesi doğrulaması · Demo",
                context="PROJECT_TASK",
                project=project,
                created_by=pm,
                assigned_to=employee,
                owner_org=employee.primary_org,
                status="COMPLETED" if completed else "IN_PROGRESS",
                due_at=project.due_at,
                mandatory=True,
                description="Sentetik proje görevi: gerçek performans değerlendirmesi değildir.",
                expected_outcome="Örnek test senaryoları ve doğrulama notu.",
                result="Örnek kanıt paketi kontrol edildi." if completed else "",
                completed_at=now if completed else None,
            )
            contribute(
                employee,
                task,
                {
                    "done": "Demo: kontrol listesi ve kapsam notu hazırlandı.",
                    "next_step": "Kapanış doğrulaması."
                    if completed
                    else "Örnek yeniden test çıktıları eklenecek.",
                },
            )
            questions = [
                {
                    "id": str(uuid5(NAMESPACE_URL, f"onecs-demo:{project.pk}:{key}")),
                    "label": label,
                }
                for key, label in [
                    ("outcome", "Proje beklenen çıktıyı karşıladı mı?"),
                    ("quality", "Teslimatların kalitesini nasıl değerlendirirsiniz?"),
                    ("coordination", "Ekipler arası koordinasyon yeterli miydi?"),
                ]
            ]
            survey = ProjectClosureSurvey.objects.create(
                project=project,
                title="Örnek paydaş değerlendirmesi",
                questions=questions,
                created_by=pm,
                closes_at=now + timedelta(days=7),
                status="CLOSED" if completed else "OPEN",
            )
            invitees = [*people.values(), employee]
            survey.invitees.set(invitees)
            for index, person in enumerate(invitees if completed else invitees[:2]):
                ProjectSurveyResponse.objects.create(
                    survey=survey,
                    user=person,
                    answers={q["id"]: (5 if index == 0 else 4) for q in questions},
                )
            record_progress(project, pm)
            for kind, start in [
                ("DAILY", today),
                ("WEEKLY", today - timedelta(days=today.weekday())),
                *([("CLOSURE", today - timedelta(days=7))] if completed else []),
            ]:
                sources, scores, digest = report_sources(project, start, today)
                report = ProjectInsightReport.objects.create(
                    project=project,
                    created_by=pm,
                    kind=kind,
                    period_start=start,
                    period_end=today,
                    status="READY",
                    generated_mode="RULE_BASED",
                    computed_values=scores,
                    sources=sources,
                    source_hash=digest,
                )
                report.original_markdown = fallback_markdown(report)
                report.markdown = report.original_markdown
                report.save(update_fields=["original_markdown", "markdown"])
            audit(
                pm, "project.insights.demo_seeded", project, {"demo": True, "teams": 4}
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Dört ekipli iki proje ve düzenlenebilir örnek raporlar hazır. Mevcut düzenlemeler korunmuştur."
            )
        )
