"""Reference organization plus explicitly fictional, idempotent demo scenarios."""

import os
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from core.models import (
    Announcement,
    Case,
    CommunityCard,
    Credential,
    Event,
    OrgNode,
    PMAppointment,
    Poll,
    Project,
    ProjectMembership,
    ProjectRevision,
    ReportSelection,
    RoleGrant,
    SLAPolicy,
    User,
    WorkItem,
)
from core.services import audit, contribute, create_sla, enqueue_notification

# Codes are stable onecs identifiers; the supplied chart establishes names and
# reporting lines, not a verified HR directory identifier or authentication map.
OFFICIAL_UNITS = [
    ("IS", "Infrastructure Security", "Hakan Tokay", "infrastructure_head"),
    ("SAA", "Security Assurance & Architecture", "Mert Deva", "assurance_head"),
    ("CDC", "Cyber Defence Center", "Abdurrahman Şakar", "cdchead"),
    ("IAM", "Identity Access Management", "Alper Eryılmaz", "iamhead"),
    ("OS", "Offensive Security", "Necati Ersen Şişeci", "unithead"),
    ("SM", "Security Management", "Kerem Kılıç", "pm_head"),
    ("MSS", "Managed Security Services", "Hakan Tokay", "infrastructure_head"),
]
OFFICIAL_TEAMS = [
    ("IS-SSM", "SECURITY SERVICES MANAGEMENT", "IS", "Murat Karaaslan"),
    ("IS-SSO", "SECURITY SERVICES OPERATIONS", "IS", "Selami Sağlam"),
    ("IAM-IMO", "IDENTITY MANAGEMENT OPERATIONS", "IAM", "Hüseyin İğde"),
    ("IAM-AMO", "ACCESS MANAGEMENT OPERATIONS", "IAM", "Sefa Yıldız"),
    ("CDC-ANL", "CYBER DEFENCE CENTER ANALYSIS", "CDC", "Fatih Demirbaş"),
    ("CDC-DFIR", "DIGITAL FORENSICS INCIDENT RESPONSE", "CDC", "Gökhan Koç"),
]
LEGACY_CODES = {
    "ICT-CS-FW",
    "ICT-CS-SA",
    "ICT-CS-PMO",
    "ICT-CS-ARCH",
    "ICT-CS-GRC",
    "ICT-CS-APP",
    "ICT-CS-CLOUD",
    "ICT-CS-CTI",
    "ICT-CS-ENG",
}
DEMO_NOTE = "Demo senaryosu: kurumsal iş, vaka veya personel kaydından alınmamıştır. "
EMPLOYEES = {
    "IS": ("demo_is", "Demo · Ada (Infrastructure Security)"),
    "SAA": ("demo_saa", "Demo · Deniz (Security Assurance & Architecture)"),
    "CDC": ("demo_cdc", "Demo · Eren (Cyber Defence Center)"),
    "IAM": ("iamemployee", "Demo · İpek (Identity Access Management)"),
    "OS": ("demo_os", "Demo · Ece (Offensive Security)"),
    "SM": ("demo_sm", "Demo · Öykü (Security Management)"),
    "MSS": ("demo_mss", "Demo · Yağız (Managed Security Services)"),
}


class Command(BaseCommand):
    help = "Resmî şema referansı ve açıkça işaretli örnek hesaplarla onecs demosunu kurar; mevcut işleri sıfırlamaz."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-demo-team",
            action="store_true",
            help="Resmî olduğu iddia edilmeyen örnek alt ekip ve Team Manager ekler.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.ONECS_ENV not in ("development", "demo", "test"):
            raise CommandError("Demo seed üretim ortamında çalıştırılamaz.")
        password = os.environ.get("ONECS_DEMO_PASSWORD")
        if not password or len(password) < 10:
            raise CommandError("ONECS_DEMO_PASSWORD en az 10 karakter olmalıdır.")
        if (
            OrgNode.objects.filter(code__in=LEGACY_CODES).exists()
            or User.objects.filter(username__regex=r"^cs[0-9]{3}$").exists()
        ):
            raise CommandError(
                "Eski sentetik organizasyon algılandı. Seed veri silmez. Yerel yedeği aldıktan sonra yalnız demo veritabanını kontrollü temizleyip yeniden çalıştırın."
            )
        root, _ = OrgNode.objects.get_or_create(
            code="ICT-CS",
            defaults={
                "name": "Cyber Security",
                "kind": "DIRECTORATE",
                "description": "Paylaşılan organizasyon şemasındaki direktörlük referansı; örnek yerel hesaplar gerçek kurumsal kimlik doğrulaması değildir.",
            },
        )
        units = {}
        for code, name, manager_name, username in OFFICIAL_UNITS:
            units[code], _ = OrgNode.objects.get_or_create(
                code=f"ICT-CS-{code}",
                defaults={
                    "name": name,
                    "kind": "UNIT",
                    "parent": root,
                    "contact": manager_name,
                    "description": "Paylaşılan organizasyon şemasındaki unit referansı. İş örnekleri ve örnek uzmanlık etiketleri demo verisidir.",
                    "expertise": [],
                },
            )
        hashed = make_password(password)

        def person(username, name, org, kind="DEMO", role=None, login=True):
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "display_name": name,
                    "primary_org": org,
                    "profile_kind": kind,
                    "email": ""
                    if kind == "OFFICIAL_REFERENCE"
                    else f"{username}@example.test",
                    "password": hashed if login else make_password(None),
                },
            )
            if created:
                RoleGrant.objects.get_or_create(
                    user=user, role="EMPLOYEE", org_node=org
                )
            if role:
                RoleGrant.objects.get_or_create(
                    user=user, role=role, org_node=org, defaults={"active": True}
                )
            return user

        director = person(
            "director", "Emin İslam Tatlı", root, "OFFICIAL_REFERENCE", "DIRECTOR"
        )
        managers = {}
        for code, name, manager_name, username in OFFICIAL_UNITS:
            manager = person(username, manager_name, units[code], "OFFICIAL_REFERENCE")
            RoleGrant.objects.get_or_create(
                user=manager, role="UNIT_HEAD", org_node=units[code]
            )
            managers[code] = manager
        employees = {
            code: person(username, name, units[code])
            for code, (username, name) in EMPLOYEES.items()
        }
        ast, _ = OrgNode.objects.get_or_create(
            code="ICT-CS-OS-AST",
            defaults={
                "name": "APPLICATION SECURITY TESTING",
                "parent": units["OS"],
                "kind": "TEAM",
                "description": "Kurum organizasyon sayfasında doğrulanan ekip referansı. Yerel referans hesapları kurumsal kimlik doğrulaması değildir.",
            },
        )
        actual_team_manager = person(
            "teammanager", "Emre Uzun", ast, "OFFICIAL_REFERENCE", "TEAM_MANAGER"
        )
        actual_employee = person(
            "employee", "Muhammed Eren Uygun", ast, "OFFICIAL_REFERENCE"
        )
        reference_names = [
            "Ahmet Buğra Demirel",
            "Oğuzhan Duran",
            "Emir Arda Eker",
            "Emrecan Gerede",
            "Mert Karababa",
            "Sefa Bora Sezgin",
            "Enes Subaş",
            "Murat Yeşiltepe",
            "Çağrı Yiğit",
            "Eray Çakın",
            "Mürşit Kağan Özsoy",
            "Şahende Şimşek (PT)",
        ]
        from django.utils.text import slugify

        for name in reference_names:
            person(
                "ref_" + slugify(name).replace("-", "_"),
                name,
                ast,
                "OFFICIAL_REFERENCE",
                login=False,
            )
        for code, name, parent_code, manager_name in OFFICIAL_TEAMS:
            team, _ = OrgNode.objects.get_or_create(
                code="ICT-CS-" + code,
                defaults={
                    "name": name,
                    "parent": units[parent_code],
                    "kind": "TEAM",
                    "description": "Kurum organizasyon sayfasında doğrulanan ekip referansı. Kod onecs içi sabit tanımlayıcıdır.",
                },
            )
            person(
                "ref_" + slugify(manager_name).replace("-", "_"),
                manager_name,
                team,
                "OFFICIAL_REFERENCE",
                "TEAM_MANAGER",
                login=False,
            )
        if options["with_demo_team"]:
            team, _ = OrgNode.objects.get_or_create(
                code="ICT-CS-OS-DEMO",
                defaults={
                    "name": "Demo Alt Ekip · Güvenlik Testleri",
                    "parent": units["OS"],
                    "kind": "TEAM",
                    "is_demo": True,
                    "description": "Yalnız hiyerarşi akışını göstermek için örnek ekip; resmî organizasyon kaydı değildir.",
                },
            )
            person(
                "demo_teammanager",
                "Demo · Güvenlik Testleri Yöneticisi",
                team,
                role="TEAM_MANAGER",
            )
            # The option is an initial setup choice; never relocate a person on a rerun.
            if (
                not WorkItem.objects.filter(assigned_to=employees["OS"]).exists()
                and employees["OS"].primary_org_id == units["OS"].pk
            ):
                employees["OS"].primary_org = team
                employees["OS"].save(update_fields=["primary_org"])
        pm = person("pm", "Demo · Proje Yöneticisi", units["SM"])
        person("admin", "Demo · Teknik Sistem Yöneticisi", root, role="SYSTEM_ADMIN")
        fulladmin = person(
            "fulladmin", "Demo · Yetki Yöneticisi", root, role="SYSTEM_ADMIN"
        )
        RoleGrant.objects.get_or_create(user=fulladmin, role="DIRECTOR", org_node=root)
        appt, _ = PMAppointment.objects.get_or_create(
            user=pm,
            governing_org=units["SM"],
            defaults={"name": "CS Stratejik Projeler · Demo Portföy"},
        )
        for priority, amount, unit in [
            ("CRITICAL", 24, "HOURS"),
            ("HIGH", 7, "DAYS"),
            ("NORMAL", 1, "MONTHS"),
        ]:
            SLAPolicy.objects.get_or_create(
                priority=priority,
                context="ALL",
                active=True,
                defaults={"amount": amount, "unit": unit},
            )

        project_specs = [
            (
                "Ayrıcalıklı erişimlerin sadeleştirilmesi",
                "IAM",
                ["OS", "IAM", "IS"],
                68,
                "CRITICAL",
                "Kritik erişim rollerinin gözden geçirilmesi ve gereksiz kalıcı yetkilerin kaldırılması.",
                "Pilot sistemlerde süreli erişim ve doğrulanmış rol matrisi.",
            ),
            (
                "Dışa açık API güvenlik standardı",
                "OS",
                ["OS", "SAA", "CDC"],
                35,
                "HIGH",
                "Kimlik doğrulama, yetkilendirme ve güvenlik kayıtlarının ortak kontrol listesiyle doğrulanması.",
                "Ürün ekiplerine sunulacak kaynaklı API kontrol standardı.",
            ),
            (
                "Yönetilen güvenlik hizmeti geçiş hazırlığı",
                "MSS",
                ["MSS", "IS", "SM"],
                20,
                "NORMAL",
                "Hizmet kapsamı, eskalasyon zinciri ve operasyonel sorumlulukların netleştirilmesi.",
                "Kabul ölçütleri belirlenmiş hizmet geçiş planı.",
            ),
        ]
        projects = []
        for (
            title,
            owner_code,
            member_codes,
            progress,
            priority,
            description,
            outcome,
        ) in project_specs:
            author = employees[owner_code]
            project, made = Project.objects.get_or_create(
                title=title,
                created_by=author,
                defaults={
                    "description": DEMO_NOTE + description,
                    "expected_outcome": outcome,
                    "owner_org": units[owner_code],
                    "appointment": appt,
                    "status": "IN_PROGRESS",
                    "priority": priority,
                    "progress": progress,
                    "progress_note": "Örnek pilot değerlendirmesi güncellendi.",
                    "due_at": timezone.now() + timedelta(days=18),
                    "published_revision": 1,
                    "submitted_revision": 1,
                    "approved_by": pm,
                },
            )
            projects.append(project)
            if made:
                project.audience.set([units[code] for code in member_codes])
                ProjectRevision.objects.create(
                    project=project,
                    number=1,
                    author=author,
                    decision="APPROVE",
                    decided_by=pm,
                    content={
                        "title": title,
                        "description": project.description,
                        "expected_outcome": outcome,
                        "due_at": project.due_at.isoformat(),
                    },
                )
                for code in member_codes:
                    ProjectMembership.objects.create(
                        project=project,
                        user=employees[code],
                        accepted_by=managers[code],
                    )
                contribute(
                    author,
                    project,
                    {
                        "done": "Örnek çalışma: kapsam ve mevcut kontroller değerlendirildi.",
                        "next_step": "Paydaş ekiplerle sonuç doğrulaması yapılacak.",
                    },
                )
                audit(
                    pm,
                    "project.reviewed",
                    project,
                    {"decision": "APPROVE", "demo": True},
                )
        proposal, made = Project.objects.get_or_create(
            title="Sertifika ve lisans yenileme erken uyarısı",
            created_by=employees["SAA"],
            defaults={
                "description": DEMO_NOTE
                + "Önemli sertifika ve ürün yenilemelerini ortak takipte toplama önerisi.",
                "expected_outcome": "Yenileme planını önceden görünür kılan yönetim özeti.",
                "owner_org": units["SAA"],
                "appointment": appt,
                "status": "SUBMITTED",
                "submitted_revision": 1,
                "priority": "NORMAL",
                "due_at": timezone.now() + timedelta(days=30),
            },
        )
        if made:
            proposal.audience.add(units["SAA"])
            ProjectRevision.objects.create(
                project=proposal,
                number=1,
                author=employees["SAA"],
                content={
                    "title": proposal.title,
                    "description": proposal.description,
                    "expected_outcome": proposal.expected_outcome,
                },
            )
            enqueue_notification(
                pm,
                "Proje onayınızı bekliyor",
                "project",
                proposal.pk,
                f"project-submit:{proposal.pk}:1:{pm.pk}",
            )
        work_specs = [
            ("IS", "Güvenlik duvarı kural yaşam döngüsü gözden geçirmesi", "HIGH", 36),
            ("SAA", "Denetim kanıt paketinin son kontrolü", "HIGH", 72),
            ("CDC", "Kimlik avı alarm akışının doğrulanması", "CRITICAL", 8),
            ("IAM", "Ayrıcalıklı servis hesapları erişim gözden geçirmesi", "HIGH", -6),
            ("OS", "Kritik API bulgusunun kapanış doğrulaması", "CRITICAL", -4),
            ("SM", "Üst yönetim karar gündeminin hazırlanması", "NORMAL", 120),
            ("MSS", "Müşteri hizmet eskalasyon planının değerlendirilmesi", "HIGH", 48),
        ]
        for code, title, priority, hours in work_specs:
            employee = employees[code]
            work, made = WorkItem.objects.get_or_create(
                title=title,
                created_by=managers[code],
                defaults={
                    "description": DEMO_NOTE
                    + "Sorumlu, hedef çıktı ve kapanış kanıtı birlikte takip edilir.",
                    "expected_outcome": "Doğrulanmış sonuç ve kaynaklı yönetim notu.",
                    "assigned_to": employee,
                    "owner_org": employee.primary_org,
                    "formal": True,
                    "priority": priority,
                    "status": "IN_PROGRESS",
                },
            )
            if made:
                sla = create_sla(work=work)
                sla.current_due_at = timezone.now() + timedelta(hours=hours)
                sla.original_due_at = sla.current_due_at
                sla.started_at = sla.current_due_at - timedelta(
                    hours=24 if priority == "CRITICAL" else 168
                )
                sla.save()
                work.due_at = sla.current_due_at
                work.save(update_fields=["due_at"])
                contribute(
                    employee,
                    work,
                    {
                        "done": "Örnek çalışma: ilk değerlendirme tamamlandı.",
                        "next_step": "Kontrol çıktısı ekip yöneticisiyle doğrulanacak.",
                    },
                )
                enqueue_notification(
                    employee,
                    "Size bir iş atandı",
                    "work",
                    work.pk,
                    f"assign:{work.pk}:1",
                )
        commitment, made = WorkItem.objects.get_or_create(
            title="Üst yönetim güvenlik değerlendirmesi hazırlığı",
            created_by=director,
            defaults={
                "description": DEMO_NOTE
                + "Direktör tarafından unit düzeyinde takip edilen örnek taahhüt.",
                "expected_outcome": "Yönetim toplantısı için doğrulanmış özet.",
                "assigned_to": managers["OS"],
                "owner_org": units["OS"],
                "formal": True,
                "priority": "HIGH",
                "kind": "COMMITMENT",
                "status": "IN_PROGRESS",
            },
        )
        if made:
            create_sla(work=commitment)
            child = WorkItem.objects.create(
                title="Kritik bulguların yönetim özetini derle",
                description=DEMO_NOTE,
                expected_outcome="Kaynaklı bulgu listesi",
                created_by=managers["OS"],
                assigned_to=employees["OS"],
                owner_org=employees["OS"].primary_org,
                parent=commitment,
                formal=True,
                priority="HIGH",
                shared_parent_summary="Üst yönetim toplantısı için kritik bulguların özetlenmesi.",
            )
            create_sla(work=child)
            enqueue_notification(
                employees["OS"],
                "Size bir alt iş atandı",
                "work",
                child.pk,
                f"assign:{child.pk}:1",
            )
        alias_work, made = WorkItem.objects.get_or_create(
            title="API yetkilendirme kontrol listesinin hazırlanması",
            created_by=actual_team_manager,
            defaults={
                "description": DEMO_NOTE
                + "Yerel kullanıcı akışını göstermek için örnek atama.",
                "expected_outcome": "Yetkilendirme test adımlarının kaynaklı özeti.",
                "assigned_to": actual_employee,
                "owner_org": ast,
                "formal": True,
                "priority": "HIGH",
                "status": "OPEN",
            },
        )
        if made:
            create_sla(work=alias_work)
            enqueue_notification(
                actual_employee,
                "Size bir iş atandı",
                "work",
                alias_work.pk,
                f"assign:{alias_work.pk}:1",
            )
        WorkItem.objects.get_or_create(
            title="Ekipler arası API güvenliği paylaşımına hazırlan",
            created_by=employees["OS"],
            defaults={
                "description": DEMO_NOTE,
                "assigned_to": employees["OS"],
                "owner_org": employees["OS"].primary_org,
                "due_at": timezone.now() + timedelta(days=3),
            },
        )
        case, made = Case.objects.get_or_create(
            title="Kimlik avı şüphesi · ortak ekip koordinasyonu",
            created_by=managers["CDC"],
            defaults={
                "description": DEMO_NOTE
                + "CDC analizi, IAM erişim doğrulaması ve Offensive Security uygulama kontrolü tek vaka altında izlenir.",
                "owner_org": units["CDC"],
                "coordinator": managers["CDC"],
                "priority": "CRITICAL",
                "status": "IN_PROGRESS",
            },
        )
        if made:
            case.members.add(
                managers["CDC"], employees["CDC"], employees["IAM"], employees["OS"]
            )
            create_sla(case=case)
            for code, title in [
                ("CDC", "Alarm zaman çizelgesini doğrula"),
                ("IAM", "Şüpheli oturumları ve erişimleri değerlendir"),
                ("OS", "Etkilenen uygulama kontrolünü tamamla"),
            ]:
                action = WorkItem.objects.create(
                    title=title,
                    description=DEMO_NOTE,
                    context="CASE_ACTION",
                    case=case,
                    assigned_to=employees[code],
                    owner_org=employees[code].primary_org,
                    created_by=managers["CDC"],
                    priority="CRITICAL",
                    status="IN_PROGRESS",
                )
                enqueue_notification(
                    employees[code],
                    "Yeni vaka aksiyonu",
                    "work",
                    action.pk,
                    f"assign:{action.pk}:1",
                )
            contribute(
                employees["CDC"],
                case,
                {
                    "done": "Örnek alarm incelemesi tamamlandı; paydaş ekip aksiyonları belirlendi.",
                    "next_step": "IAM ve Offensive Security doğrulaması bekleniyor.",
                },
            )
        Announcement.objects.get_or_create(
            title="CS bilgi paylaşım haftası",
            created_by=managers["SAA"],
            defaults={
                "body": DEMO_NOTE
                + "Ekipler deneyimlerini kısa oturumlarda paylaşıyor; uygun etkinliğe katılımınızı bildirebilirsiniz.",
                "owner_org": units["SAA"],
                "all_cs": True,
                "status": "PUBLISHED",
                "ends_at": timezone.now() + timedelta(days=7),
            },
        )
        for code, title, body in [
            (
                "OS",
                "API güvenliğinde birlikte üretelim",
                "Ortak API kontrol listesini paylaşmak ve diğer ekiplerin deneyimlerini dinlemek istiyoruz.",
            ),
            (
                "IAM",
                "Erişim gözden geçirmesinden öğrendiklerimiz",
                "Süreli erişim ve açık rol sahipliğine ilişkin örnek deneyimleri konuşalım.",
            ),
            (
                "IS",
                "Altyapı değişikliklerini birlikte planlayalım",
                "Güvenlik kuralı değişikliklerinde paydaş ekiplerden erken geri bildirim bekliyoruz.",
            ),
        ]:
            CommunityCard.objects.get_or_create(
                title=title,
                created_by=employees[code],
                defaults={
                    "body": DEMO_NOTE + body,
                    "owner_org": units[code],
                    "kind": "HELP",
                    "all_cs": True,
                    "status": "PUBLISHED",
                    "published_by": managers[code],
                },
            )
        event, made = Event.objects.get_or_create(
            title="CS buluşması · API ve kimlik güvenliği",
            created_by=director,
            defaults={
                "description": DEMO_NOTE
                + "Ekipler arası kısa bilgi paylaşımı ve tanışma oturumu.",
                "owner_org": root,
                "location": "Örnek CS toplantı alanı · Hibrit",
                "starts_at": timezone.now() + timedelta(days=3),
                "ends_at": timezone.now() + timedelta(days=3, hours=1),
            },
        )
        if made:
            event.invitees.set(User.objects.filter(is_active=True))
            Poll.objects.create(
                event=event,
                question="Hangi oturum size uygun?",
                options=[
                    {"id": "morning", "label": "10.00 · Sabah"},
                    {"id": "afternoon", "label": "14.00 · Öğleden sonra"},
                ],
                max_choices=1,
                closes_at=timezone.now() + timedelta(days=2),
                elector_ids=[
                    str(pk) for pk in event.invitees.values_list("id", flat=True)
                ],
            )
        for code, name, issuer, expires in [
            ("OS", "CISSP · Örnek sertifika", "ISC2", 18),
            ("IAM", "SC-300 · Örnek sertifika", "Microsoft", 90),
            (
                "SAA",
                "ISO 27001 Lead Auditor · Örnek sertifika",
                "Örnek eğitim kurumu",
                25,
            ),
        ]:
            Credential.objects.get_or_create(
                user=employees[code],
                name=name,
                defaults={
                    "issuer": issuer,
                    "issued_on": timezone.localdate() - timedelta(days=200),
                    "expires_on": timezone.localdate() + timedelta(days=expires),
                    "important": True,
                    "verification_status": "DECLARED",
                },
            )
        ReportSelection.objects.get_or_create(
            user=director,
            source_type="project",
            source_id=projects[0].pk,
            week_start=timezone.localdate()
            - timedelta(days=timezone.localdate().weekday()),
        )
        call_command("seed_project_insights", stdout=self.stdout)
        self.stdout.write(
            self.style.SUCCESS(
                f"onecs hazır: 7 unit, 6 farklı unit yöneticisi ve direktör şema referansı; {len(employees)} açıkça işaretli örnek çalışan. Örnek alt ekip: {'açık' if options['with_demo_team'] else 'kapalı'}. Mevcut iş akışları korunmuştur."
            )
        )
