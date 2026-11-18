"""Create a coherent fictional portfolio without resetting a user's work."""

import hashlib
from collections import Counter
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Announcement, AuditEvent, Case, CommunityCard, Credential, Event,
    EventAttendance, EventRSVP, Notification, OrgNode, PMAppointment, Poll,
    PollResponse, ProgressEntry, Project, ProjectMembership, ProjectRevision,
    Report, User, WorkItem,
)
from core.showcase_catalog import CARDS, DEMO_FOOTER, PEOPLE, PROJECTS


def fixture_id(model, key):
    return uuid5(NAMESPACE_URL, f"onecs-showcase:v1:{model._meta.label_lower}:{key}")


def demo_text(text):
    return f"{text}\n\n{DEMO_FOOTER}"


class Command(BaseCommand):
    help = "Gerçekçi ve bağlantılı gösterim verileri ekler; mevcut kayıtları ve kullanıcı düzenlemelerini korur."

    def add_arguments(self, parser):
        parser.add_argument(
            "--polish-legacy-cards", action="store_true",
            help="Yalnız seed_demo'nun değişmemiş üç kartındaki eski açıklamaları iyileştirir.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.ONECS_ENV not in ("development", "demo", "test"):
            raise CommandError("Gösterim verileri üretim ortamına yüklenemez.")
        # Never adopt an LDAP, reference or personal account just because its
        # username happens to match a demo username. No identities/grants change.
        self.people = {}
        for code, username in {**PEOPLE, "PM": "pm"}.items():
            person = User.objects.filter(
                username=username, profile_kind="DEMO", identity_source="local", is_active=True,
            ).first()
            if not person:
                raise CommandError(f"Yerel demo hesabı eksik: {username}. Önce seed_demo çalıştırın.")
            self.people[code] = person
        self.pm = self.people["PM"]
        self.publisher = User.objects.filter(
            username="fulladmin", profile_kind="DEMO", identity_source="local", is_active=True,
            role_grants__role="DIRECTOR", role_grants__active=True,
        ).first()
        self.appointment = PMAppointment.objects.filter(user=self.pm, active=True).first()
        self.units = {code: OrgNode.objects.filter(code=f"ICT-CS-{code}", active=True).first() for code in PEOPLE}
        if not self.appointment or not self.publisher or not all(self.units.values()):
            raise CommandError("Örnek organizasyon veya etkin PM görevlendirmesi eksik.")
        self.now = timezone.now()
        self.counts = Counter()
        self.projects = {}
        # The most useful in-flight project appears first in updated-at lists.
        for spec in reversed(PROJECTS):
            self.project(spec)
        self.community()
        self.announcements()
        self.events()
        self.unit_work()
        self.cases()
        self.credentials()
        self.report()
        if options["polish_legacy_cards"]:
            self.polish_legacy_cards()
        summary = ", ".join(f"{model}: {count}" for model, count in sorted(self.counts.items()))
        self.stdout.write(self.style.SUCCESS(summary or "Yeni kayıt yok; mevcut düzenlemeler korundu."))

    def make(self, model, key, **values):
        obj, made = model.objects.get_or_create(pk=fixture_id(model, key), defaults=values)
        if made:
            self.counts[model.__name__] += 1
        return obj, made

    def provenance(self, obj, key):
        self.make(
            AuditEvent, f"seed:{obj._meta.label_lower}:{key}", actor=self.pm,
            action="demo.showcase.created", object_type=obj.__class__.__name__,
            object_id=str(obj.pk), data={"demo": True, "fixture": "showcase-v1", "key": key},
        )

    def contribution(self, obj, key, code, done, next_step, *, days=0, blocker="", previous=None):
        field = {"Project": "project", "WorkItem": "work", "Case": "case"}[obj.__class__.__name__]
        row, _ = self.make(
            ProgressEntry, key, **{field: obj}, author=self.people[code],
            author_org=self.units[code], done=done, next_step=next_step, blocker=blocker,
            previous=previous, created_at=self.now - timedelta(days=days),
        )
        return row

    def project(self, spec):
        approved = spec.status != "SUBMITTED"
        project, made = self.make(
            Project, spec.key, title=spec.title, description=demo_text(spec.description),
            expected_outcome=spec.outcome, created_by=self.people[spec.owner],
            owner_org=self.units[spec.owner], appointment=self.appointment,
            status=spec.status, priority=spec.priority, due_at=self.now + timedelta(days=spec.due_days),
            progress=spec.progress, progress_note=spec.note,
            published_revision=1 if approved else None, submitted_revision=1,
            approved_by=self.pm if approved else None,
            approval_note="Kapsam ve kabul ölçütleri değerlendirildi; ekip katkıları onaylandı." if approved else "",
            created_at=self.now - timedelta(days=42 if approved else 2),
        )
        self.projects[spec.key] = project
        if not made:
            return
        project.audience.set(self.units.values())
        self.make(
            ProjectRevision, spec.key, project=project, number=1, author=project.created_by,
            decision="APPROVE" if approved else "PENDING", decided_by=self.pm if approved else None,
            decision_note=project.approval_note,
            created_at=project.created_at,
            content={"title": project.title, "description": project.description,
                     "expected_outcome": project.expected_outcome, "due_at": project.due_at.isoformat()},
        )
        for code in dict.fromkeys([spec.owner, *(team.code for team in spec.teams)]):
            self.make(ProjectMembership, f"{spec.key}:{code}", project=project, user=self.people[code], accepted_by=self.pm)
        for team in spec.teams:
            initial = self.contribution(
                project, f"{spec.key}:{team.code}:kickoff", team.code,
                f"Kapsam ve kabul ölçütleri gözden geçirildi: {team.deliveries[0][0].lower()}.",
                f"İlk çalışma paketi: {team.deliveries[0][0]}.", days=28,
            )
            self.contribution(
                project, f"{spec.key}:{team.code}:latest", team.code, team.done, team.next_step,
                days=4 if spec.status == "COMPLETED" else 0, blocker=team.blocker, previous=initial,
            )
            for index, (title, progress, evidence) in enumerate(team.deliveries):
                status = "COMPLETED" if progress == 100 else "OPEN" if progress == 0 else "WAITING" if team.blocker else "IN_PROGRESS"
                due = project.due_at - timedelta(days=2 * (1 - index))
                task, _ = self.make(
                    WorkItem, f"{spec.key}:{team.code}:{index}", title=title,
                    description=demo_text(f"{spec.title} kapsamında {title.lower()}.\n\n{evidence}"),
                    expected_outcome=f"{title} için gözden geçirilmiş çıktı ve kabul notu.",
                    context="PROJECT_TASK", project=project, owner_org=self.units[team.code],
                    created_by=self.pm, assigned_to=self.people[team.code], priority=spec.priority,
                    status=status, due_at=due, result=evidence if progress == 100 else "",
                    blocker=team.blocker if status == "WAITING" else "",
                    completed_at=min(due, self.now - timedelta(days=1)) if progress == 100 else None,
                    created_at=project.created_at + timedelta(days=2),
                )
                self.contribution(
                    task, f"task:{spec.key}:{team.code}:{index}", team.code,
                    evidence if progress else "Çalışma paketi tanımlandı; uygulama adımı henüz başlamadı.",
                    "Kabul edildi; sonraki fazda kontrol listesi yeniden kullanılacak." if progress == 100 else team.next_step,
                    days=4 if spec.status == "COMPLETED" else 0, blocker=task.blocker,
                )
        self.insights(project, spec)
        self.provenance(project, spec.key)
        if not approved:
            self.make(
                Notification, f"proposal:{spec.key}", recipient=self.pm, title="Proje başvurusu değerlendirmenizi bekliyor",
                message=f"{project.title}: kapsam, kaynak ve başlangıç takvimi için karar bekleniyor.",
                resource_type="project", resource_id=str(project.pk), dedup_key=f"showcase:proposal:{project.pk}",
            )

    def insights(self, project, spec):
        # This fixture also works on installations predating project insights.
        try:
            Plan = apps.get_model("core", "ProjectTeamPlan")
        except LookupError:
            return
        if not spec.teams:
            return
        Delivery = apps.get_model("core", "ProjectDeliverable")
        Snapshot = apps.get_model("core", "ProjectProgressSnapshot")
        from core.project_insights import project_metrics, report_sources, fallback_markdown
        for team in spec.teams:
            plan, _ = self.make(Plan, f"{spec.key}:{team.code}", project=project, org=self.units[team.code], weight=team.weight)
            for index, (title, progress, evidence) in enumerate(team.deliveries):
                self.make(
                    Delivery, f"{spec.key}:{team.code}:{index}", plan=plan, title=title,
                    kind="MILESTONE" if index else "DELIVERABLE", weight=50, progress=progress,
                    evidence=demo_text(evidence) if progress else "",
                    quality_rating=(5 if index == 0 else 4) if progress == 100 else None,
                    due_at=project.due_at - timedelta(days=2 * (1 - index)), updated_by=self.pm,
                )
        # Historical frames are built from actual sample delivery states, then
        # final states are restored before generating reports. No invented
        # aggregate score is presented as a measured production result.
        deliveries = list(Delivery.objects.filter(plan__project=project))
        final_progress = {d.pk: d.progress for d in deliveries}
        final_ratings = {d.pk: d.quality_rating for d in deliveries}
        for step, (days, factor) in enumerate(((21, .35), (10, .65), (0, 1))):
            for delivery in deliveries:
                Delivery.objects.filter(pk=delivery.pk).update(
                    progress=round(final_progress[delivery.pk] * factor),
                    quality_rating=final_ratings[delivery.pk] if factor == 1 else None,
                )
            teams, scores = project_metrics(project)
            self.make(
                Snapshot, f"{spec.key}:{step}", project=project, created_by=self.pm,
                teams=[{key: team[key] for key in ("id", "version", "org_id", "weight", "progress", "coverage")} for team in teams],
                scores=scores, created_at=self.now - timedelta(days=days + (4 if spec.status == "COMPLETED" else 0)),
            )
        if spec.status == "COMPLETED":
            Survey = apps.get_model("core", "ProjectClosureSurvey")
            Response = apps.get_model("core", "ProjectSurveyResponse")
            questions = [{"id": str(uuid5(NAMESPACE_URL, f"showcase:{spec.key}:{key}")), "label": label} for key, label in (
                ("outcome", "Pilot beklenen güvenlik çıktısını karşıladı mı?"),
                ("handover", "Operasyon devri ve rehberler yeterli miydi?"),
                ("coordination", "Ekipler arası koordinasyonu nasıl değerlendirirsiniz?"),
            )]
            survey, _ = self.make(
                Survey, spec.key, project=project, title="Süreli erişim pilotu · kapanış değerlendirmesi",
                questions=questions, status="CLOSED", created_by=self.pm,
                closes_at=self.now - timedelta(days=4), created_at=self.now - timedelta(days=7),
            )
            invitees = [self.people[t.code] for t in spec.teams] + [self.pm]
            survey.invitees.set(invitees)
            for index, person in enumerate(invitees):
                self.make(Response, f"{spec.key}:{person.username}", survey=survey, user=person,
                          answers={q["id"]: 4 if (i + index) % 3 == 0 else 5 for i, q in enumerate(questions)},
                          created_at=self.now - timedelta(days=5))
            # The final frame includes the closure feedback as well as delivery.
            _, scores = project_metrics(project)
            Snapshot.objects.filter(pk=fixture_id(Snapshot, f"{spec.key}:2")).update(scores=scores)
        InsightReport = apps.get_model("core", "ProjectInsightReport")
        today = timezone.localdate()
        start, end = today - timedelta(days=7), today
        if spec.status == "COMPLETED":
            end = today - timedelta(days=4)
            start = end - timedelta(days=7)
        sources, scores, digest = report_sources(project, start, end)
        report, _ = self.make(
            InsightReport, spec.key, project=project, created_by=self.pm,
            kind="CLOSURE" if spec.status == "COMPLETED" else "WEEKLY", period_start=start, period_end=end,
            status="READY", generated_mode="RULE_BASED", computed_values=scores, sources=sources, source_hash=digest,
        )
        report.original_markdown = demo_text(fallback_markdown(report))
        report.markdown = report.original_markdown
        report.save(update_fields=["original_markdown", "markdown"])

    def community(self):
        for index, (key, code, title, kind, project_key, body) in enumerate(reversed(CARDS)):
            project = self.projects[project_key]
            card, made = self.make(
                CommunityCard, key, title=title, body=demo_text(body), kind=kind,
                created_by=self.people[code], owner_org=self.units[code],
                source_type="project", source_id=str(project.pk), source_version=project.version,
                status="PUBLISHED", all_cs=True, content_approved_by=self.pm, published_by=self.publisher,
                created_at=self.now - timedelta(hours=len(CARDS) - index),
            )
            if made:
                card.interests.set([self.people[c] for c in PEOPLE if c != code][:3])
                self.provenance(card, key)

    def announcements(self):
        specs = (
            ("api-session", "API güvenliği çalışma oturumu: test paketini birlikte gözden geçiriyoruz", "OS", "PUBLISHED", True,
             "Ürün ve güvenlik ekiplerini 18 API için hazırlanan kontrol paketini gözden geçirmeye davet ediyoruz. "
             "Gündem: nesne düzeyi yetki, çok kiracılı uç durumlar ve CI kontrol adımları. "
             "Etkinlikler sayfasından katılımınızı bildirin; örnek senaryolarınızı oturum öncesinde paylaşabilirsiniz."),
            ("pilot-closed", "Süreli erişim pilotu tamamlandı; ikinci dalga hazırlığı başladı", "IAM", "PUBLISHED", False,
             "Altı uygulamalık pilotun teknik ve operasyon kabulü tamamlandı. Rol matrisi, negatif test paketi ve "
             "devir kontrol listesi proje detaylarında. İkinci dalgaya katılacak ekiplerden uygulama sahibi ve bakım penceresi bilgisini bekliyoruz."),
            ("recovery-draft", "Kurtarma tatbikatı için servis sahibi katılımı", "IS", "DRAFT", False,
             "Kimlik ve güvenlik izleme hizmetlerinin masa başı kurtarma tatbikatı planlandı. "
             "Yayın onayı sonrasında servis sahiplerine kapsam ve hazırlık listesi duyurulacak. "
             "Katılımcılar bağımlılık haritasını ve acil erişim adımlarını oturum öncesinde gözden geçirecek."),
        )
        for key, title, code, status, pinned, body in specs:
            obj, made = self.make(
                Announcement, key, title=title, body=demo_text(body), created_by=self.people[code],
                owner_org=self.units[code], all_cs=True, status=status, pinned=pinned,
                starts_at=self.now - timedelta(hours=2), ends_at=self.now + timedelta(days=14),
            )
            if made:
                obj.audience.set(self.units.values())
                self.provenance(obj, key)

    def events(self):
        for key, title, code, days, body in (
            ("api-workshop", "API güvenliği: kontrol paketinden CI adımına", "OS", 3,
             "10.00 · Pilot sonuçları ve açık sorular\n10.15 · Yetkilendirme senaryolarını birlikte uygulama\n"
             "10.45 · CI kontrol adımları ve ürün ekibi geri bildirimi\n11.00 · Sorumlular ve sonraki adımlar"),
            ("recovery-tabletop", "Kurtarma tatbikatı · bağımlılık ve karar provası", "IS", 8,
             "14.00 · Servis bağımlılık haritası\n14.20 · Kimlik ve izleme kesintisi senaryosu\n"
             "14.50 · Acil erişim ve iletişim zinciri\n15.15 · İyileştirme aksiyonları ve sorumlular"),
            ("pilot-retro", "Süreli erişim pilotu · kapanış ve öğrenimler", "IAM", -5,
             "Pilotun kabul ölçütleri, iki vardiyadaki geri dönüş provası ve ikinci dalga için iyileştirmeler görüşüldü. "
             "Kararlar: rol sahipliği ilk adım olacak; acil erişim her vardiyada prova edilecek; kanıtlar tek kontrol listesinde toplanacak."),
        ):
            starts = (self.now + timedelta(days=days)).replace(hour=7 if code == "OS" else 11, minute=0, second=0, microsecond=0)
            event, made = self.make(
                Event, key, title=title, description=demo_text(body), location="CS ortak çalışma alanı · Hibrit oturum",
                starts_at=starts, ends_at=starts + timedelta(minutes=75),
                owner_org=self.units[code], created_by=self.people[code], status="COMPLETED" if days < 0 else "PLANNED",
                created_at=self.now - timedelta(days=14),
            )
            if not made:
                continue
            invitees = list(self.people.values())
            event.invitees.set(invitees)
            for index, person in enumerate(invitees):
                if index < 6:
                    self.make(EventRSVP, f"{key}:{person.username}", event=event, user=person, answer="MAYBE" if index == 4 else "YES")
                if days < 0:
                    self.make(EventAttendance, f"{key}:{person.username}", event=event, user=person, present=index != 4, recorded_by=self.people[code])
            if days > 0:
                poll, _ = self.make(
                    Poll, key, event=event, question="Hangi başlığa daha fazla zaman ayıralım?",
                    options=[{"id": "scenarios", "label": "Uygulamalı senaryo ve örnekler"}, {"id": "handover", "label": "Operasyon devri ve kontrol listesi"}, {"id": "questions", "label": "Ekiplerin açık soruları"}],
                    max_choices=1, closes_at=starts - timedelta(hours=12), elector_ids=[str(u.pk) for u in invitees],
                )
                for index, person in enumerate(invitees[:5]):
                    self.make(PollResponse, f"{key}:{person.username}", poll=poll, user=person, choices=[("scenarios", "handover", "questions")[index % 3]])
            self.provenance(event, key)

    def unit_work(self):
        specs = (
            ("rule-review", "IS", "Kullanılmayan güvenlik duvarı kurallarını kapatma planı", "IN_PROGRESS", 4,
             "90 günlük trafik kaydında kullanılmayan 36 kural gözden geçirildi. 28 kuralın sahibi kapatma için teyit verdi; sekiz kural için uygulama ekibi görüşü bekleniyor.",
             "Sahibi onaylamış kural listesi, bakım penceresi ve geri dönüş adımları.", "28 kuralın kapatılmasını bakım penceresinde uygulayıp trafik kontrolünü yapmak."),
            ("evidence-review", "SAA", "Erişim kontrolü kanıt paketinin son gözden geçirmesi", "IN_PROGRESS", 2,
             "12 kontrolün kanıtı dosyalandı. Tarih, kapsam ve kontrol sahibi eşleştirmesi tamamlandı; son kabul için paket hazır.",
             "Eksiksiz kontrol-kanıt matrisi ve gözden geçirme notu.", "Kontrol sahibinden son kabulü alıp kanıt paketini kapatmak."),
            ("service-owner", "IAM", "Sahibi bulunamayan servis hesaplarını netleştirme", "WAITING", 3,
             "Envanterdeki 14 hesabın 11'i iş sahibiyle eşleştirildi. Kalan üç hesabın bağlı uygulamasını ürün ekibi doğrulayacak.",
             "Her hesap için iş sahibi, kullanım amacı ve gözden geçirme tarihi.", "Ürün ekibiyle kalan üç hesabı doğrulayıp kullanılmayanları kapatma önerisine almak."),
            ("retest", "OS", "API rol ayrımı düzeltmesinin yeniden testi", "COMPLETED", -2,
             "Farklı rol ve nesne sahipliğiyle altı negatif senaryo çalıştırıldı. Yetkisiz isteklerin reddedildiği ve olayın kayda geçtiği doğrulandı.",
             "Altı senaryonun test sonucu ve kapanış kanıtı.", "Aynı negatif testleri bir sonraki sürüm kontrol listesine eklemek."),
            ("shift-guide", "CDC", "Şüpheli oturum alarmı için vardiya rehberini güncelleme", "IN_PROGRESS", 5,
             "Kullanıcı, cihaz ve oturum alanları alarm örneklerine eklendi. İlk iki vardiyanın geri bildirimi alındı; eşik kararları rehbere işleniyor.",
             "Bir sayfalık inceleme akışı, yanlış pozitif örnekleri ve eskalasyon ölçütleri.", "Son vardiyayla akışı prova edip rehberin sürümünü sabitlemek."),
        )
        for key, code, title, status, days, body, outcome, next_step in specs:
            obj, made = self.make(
                WorkItem, key, title=title, description=demo_text(body), expected_outcome=outcome,
                context="UNIT_WORK", owner_org=self.units[code], created_by=self.people[code],
                assigned_to=self.people[code], status=status, priority="HIGH", formal=False,
                due_at=self.now + timedelta(days=days), blocker="Üç hesap için ürün ekibinden sahiplik teyidi bekleniyor." if status == "WAITING" else "",
                result=body if status in ("VERIFYING", "COMPLETED") else "",
                completed_at=self.now - timedelta(days=2) if status == "COMPLETED" else None,
                created_at=self.now - timedelta(days=10),
            )
            if made:
                self.contribution(obj, key, code, body, next_step, blocker=obj.blocker)
                self.provenance(obj, key)

    def cases(self):
        for key, title, status, body in (
            ("session-alert", "Olağandışı oturum alarmı · ortak inceleme", "IN_PROGRESS",
             "Pilot izleme senaryosunda aynı hesap için kısa aralıkla farklı cihazlardan oturum açma alarmı oluştu. "
             "CDC zaman çizelgesini, IAM oturum ve MFA kayıtlarını, OS uygulama yetki sınırını birlikte inceliyor. "
             "Henüz veri erişimi veya hesap ele geçirme sonucuna varılmadı."),
            ("expired-token", "Süresi dolan erişim belirteciyle işlem denemesi", "CLOSED",
             "Kontrollü testte süresi dolan belirteçle yapılan istek reddedildi. Uygulama, kimlik sağlayıcı ve log kayıtları "
             "aynı zaman çizelgesinde eşleştirildi. Yetkisiz işlem gerçekleşmedi; gözlem bağımsız doğrulama sonrası kapatıldı."),
        ):
            closed = status == "CLOSED"
            case, made = self.make(
                Case, key, title=title, description=demo_text(body), status=status,
                priority="HIGH", created_by=self.people["CDC"], owner_org=self.units["CDC"],
                coordinator=self.people["CDC"], verifier=self.pm,
                closure_summary=body if closed else "", verification_evidence="Zaman çizelgesi, HTTP yanıtı ve erişim kayıtları birlikte kontrol edildi. " + DEMO_FOOTER if closed else "",
                closure_requested_by=self.people["CDC"] if closed else None,
                closed_at=self.now - timedelta(days=3) if closed else None,
                created_at=self.now - timedelta(days=12 if closed else 2),
            )
            if not made:
                continue
            case.members.set([self.people[c] for c in ("CDC", "IAM", "OS")] + [self.pm])
            for code, task_title, evidence in (
                ("CDC", "Alarm zaman çizelgesini ve cihaz bağlamını doğrulama", "Kimlik ve uygulama kayıtları aynı zaman aralığında eşleştirildi."),
                ("IAM", "Oturum, belirteç ve MFA kayıtlarını inceleme", "Belirteç süresi ve MFA kararı kontrol edildi; ilgili oturumlar listelendi."),
                ("OS", "Uygulama tarafında erişim sınırını yeniden test etme", "Farklı rol ve süresi dolan belirteç senaryoları kontrol paketine alındı."),
            ):
                done = closed or code == "CDC"
                task, _ = self.make(
                    WorkItem, f"{key}:{code}", title=task_title, description=demo_text(evidence),
                    expected_outcome="Zaman çizelgesiyle eşleşen kontrol çıktısı ve gerekçeli sonuç.",
                    context="CASE_ACTION", case=case, owner_org=self.units[code], created_by=case.coordinator,
                    assigned_to=self.people[code], status="COMPLETED" if done else "IN_PROGRESS", priority="HIGH",
                    due_at=self.now + timedelta(days=-3 if closed else 2),
                    result=evidence if done else "", completed_at=self.now - timedelta(days=3 if closed else 0, hours=2) if done else None,
                    created_at=case.created_at + timedelta(hours=1),
                )
                self.contribution(task, f"case-task:{key}:{code}", code, evidence,
                                  "Kontrol sonucu vaka koordinatörüyle paylaşıldı." if done else "Kalan kontrol adımlarını tamamlayıp kanıtı koordinatöre iletmek.", days=3 if closed else 0)
            self.contribution(case, key, "CDC", body,
                              "Kapanış öğrenimini tespit kontrol listesine aktarmak." if closed else "IAM ve OS kontrol sonuçlarını tek zaman çizelgesinde değerlendirmek.", days=3 if closed else 0)
            self.provenance(case, key)

    def credentials(self):
        for code, name, issuer, days in (
            ("OS", "Certified Information Systems Security Professional", "ISC2", 120),
            ("IAM", "Identity and Access Administrator Associate", "Microsoft", 24),
            ("SAA", "ISO/IEC 27001 Lead Auditor", "Örnek Eğitim Akademisi", 65),
            ("IS", "Cloud Security Professional", "Örnek Eğitim Akademisi", 210),
        ):
            self.make(
                Credential, code, user=self.people[code], name=name, issuer=issuer,
                issued_on=timezone.localdate() - timedelta(days=340), expires_on=timezone.localdate() + timedelta(days=days),
                important=True, verification_status="DECLARED", reference="Kurgusal demo kaydı; gerçek sertifika veya mesleki yeterlilik beyanı değildir.",
            )

    def report(self):
        today = timezone.localdate()
        markdown = "# Güvenlik portföyü · haftalık değerlendirme\n\n"
        for spec in PROJECTS:
            markdown += f"## {spec.title}\n\n{spec.note}\n\nİlerleme: %{spec.progress}. {spec.outcome}\n\n"
        markdown = demo_text(markdown)
        report, made = self.make(
            Report, "portfolio-weekly", title="Güvenlik portföyü · haftalık karar ve ilerleme özeti",
            created_by=self.pm, period_start=today - timedelta(days=today.weekday()), period_end=today,
            status="DRAFT", generated_mode="RULE_BASED", markdown=markdown,
            content_hash=hashlib.sha256(markdown.encode()).hexdigest(),
            sources=[{"id": str(self.projects[s.key].pk), "type": "project", "title": s.title,
                      "status": s.status, "version": 1, "summary": s.note} for s in PROJECTS],
        )
        if made:
            self.provenance(report, "portfolio-weekly")

    def polish_legacy_cards(self):
        # Exact old fixture text AND demo identity are required. Any user edit
        # makes the row ineligible, even if it still has the original title.
        prefix = "Demo senaryosu: kurumsal iş, vaka veya personel kaydından alınmamıştır. "
        for code, title, old, new in (
            ("OS", "API güvenliğinde birlikte üretelim", "Ortak API kontrol listesini paylaşmak ve diğer ekiplerin deneyimlerini dinlemek istiyoruz.",
             "API yetkilendirme testlerini ortak bir kontrol listesinde topluyoruz. Ürün ekiplerinden nesne sahipliği, rol ayrımı ve servisler arası erişim örneklerini bekliyoruz. Deneyimlerinizi çalışma oturumunda birlikte değerlendirelim."),
            ("IAM", "Erişim gözden geçirmesinden öğrendiklerimiz", "Süreli erişim ve açık rol sahipliğine ilişkin örnek deneyimleri konuşalım.",
             "Erişim gözden geçirmesinde hesap sahibini ilk adımda belirlemek kapanışı hızlandırdı. Süreli yetki, acil erişim ve rol değişikliği için kullandığımız kontrol listesini paylaşalım; kendi ekibinizin uç durumlarını da ekleyebiliriz."),
            ("IS", "Altyapı değişikliklerini birlikte planlayalım", "Güvenlik kuralı değişikliklerinde paydaş ekiplerden erken geri bildirim bekliyoruz.",
             "Güvenlik duvarı değişikliklerinden önce kural sahibini, etkilenen servisi ve geri dönüş adımını aynı notta topluyoruz. Bakım penceresinden önce paydaş görüşü alarak son dakika belirsizliklerini azaltmayı hedefliyoruz."),
        ):
            for card in CommunityCard.objects.select_for_update().filter(
                created_by=self.people[code], title=title, body=prefix + old,
            ):
                card.body = demo_text(new)
                card.save(update_fields=["body", "updated_at"])
                self.provenance(card, f"legacy:{code}")
                self.counts["LegacyCardPolished"] += 1
