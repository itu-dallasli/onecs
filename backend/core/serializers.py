from rest_framework import serializers
from .models import (
    Announcement,
    ApiClient,
    AuditEvent,
    Case,
    CaseNotice,
    CommunityCard,
    Credential,
    Event,
    Notification,
    OrgNode,
    PMAppointment,
    ParticipationRequest,
    Poll,
    ProgressEntry,
    Project,
    Report,
    ReportSelection,
    RoleGrant,
    SLAInstance,
    SLAPolicy,
    User,
    WorkItem,
)
from .policy import (
    active_grants,
    can_publish_announcement,
    can_approve_project,
    can_manage_case,
    can_manage_org,
    can_manage_project,
    can_manage_work,
    can_read_progress,
    can_read_project_detail,
    can_read_work,
    can_update_work,
    can_verify_case,
    descendants_ids,
    project_resource_scope_ids,
    report_source,
)
from django.db.models import Q
from django.utils import timezone


class PersonSerializer(serializers.ModelSerializer):
    primary_org_name = serializers.CharField(source="primary_org.name", default="")
    primary_org_id = serializers.UUIDField(read_only=True)
    roles = serializers.SerializerMethodField()
    role_label = serializers.SerializerMethodField()

    def get_roles(self, obj) -> list:
        return [
            {
                "role": grant.role,
                "org_id": str(grant.org_node_id) if grant.org_node_id else None,
                "org_name": grant.org_node.name if grant.org_node_id else "",
                "includes_descendants": grant.includes_descendants,
                "expires_at": grant.expires_at.isoformat()
                if grant.expires_at
                else None,
            }
            for grant in active_grants(obj)
            .select_related("org_node")
            .order_by("role", "org_node__code")
        ]

    def get_role_label(self, obj) -> str:
        roles = {grant["role"] for grant in self.get_roles(obj)}
        labels = [
            ("DIRECTOR", "Direktör"),
            ("UNIT_HEAD", "Birim yöneticisi"),
            ("TEAM_MANAGER", "Ekip yöneticisi"),
        ]
        for role, label in labels:
            if role in roles:
                return label
        if obj.pm_appointments.filter(active=True).exists():
            return "Proje Yöneticisi"
        return "Sistem Yöneticisi" if "SYSTEM_ADMIN" in roles else "Çalışan"

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "display_name",
            "email",
            "primary_org_id",
            "primary_org_name",
            "expertise",
            "is_active",
            "identity_source",
            "profile_kind",
            "roles",
            "role_label",
        ]


class OrgSerializer(serializers.ModelSerializer):
    parent_id = serializers.UUIDField(read_only=True)
    manager_name = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    manager_ids = serializers.SerializerMethodField()
    manager_id = serializers.SerializerMethodField()
    managers = serializers.SerializerMethodField()

    def manager_users(self, obj):
        if not hasattr(self, "_manager_rows"):
            self._manager_rows = {}
        if obj.pk not in self._manager_rows:
            ids = (
                RoleGrant.objects.filter(
                    org_node=obj,
                    active=True,
                    user__is_active=True,
                    role__in=["DIRECTOR", "UNIT_HEAD", "TEAM_MANAGER"],
                )
                .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
                .values_list("user_id", flat=True)
            )
            users = list(
                User.objects.filter(pk__in=ids)
                .select_related("primary_org")
                .order_by("display_name")
            )
            references = [
                user for user in users if user.profile_kind == "OFFICIAL_REFERENCE"
            ]
            self._manager_rows[obj.pk] = references or users
        return self._manager_rows[obj.pk]

    def get_manager_ids(self, obj) -> list:
        return [str(user.pk) for user in self.manager_users(obj)]

    def get_manager_id(self, obj):
        ids = self.get_manager_ids(obj)
        return ids[0] if ids else None

    def get_managers(self, obj) -> list:
        return PersonSerializer(
            self.manager_users(obj), many=True, context=self.context
        ).data

    def get_manager_name(self, obj) -> str:
        return " · ".join(
            user.display_name or user.username for user in self.manager_users(obj)
        )

    def get_member_count(self, obj) -> int:
        scope = descendants_ids(obj.pk)
        managerial_membership = Q(
            role_grants__org_node_id__in=scope,
            role_grants__active=True,
            role_grants__role__in=["DIRECTOR", "UNIT_HEAD", "TEAM_MANAGER"],
        ) & (
            Q(role_grants__expires_at__isnull=True)
            | Q(role_grants__expires_at__gt=timezone.now())
        )
        return (
            User.objects.filter(is_active=True)
            .filter(Q(primary_org_id__in=scope) | managerial_membership)
            .distinct()
            .count()
        )

    class Meta:
        model = OrgNode
        fields = [
            "id",
            "code",
            "name",
            "kind",
            "parent_id",
            "active",
            "description",
            "expertise",
            "contact",
            "version",
            "manager_name",
            "manager_id",
            "manager_ids",
            "managers",
            "is_demo",
            "member_count",
        ]


class PMSerializer(serializers.ModelSerializer):
    user = PersonSerializer(read_only=True)
    governing_org_name = serializers.CharField(source="governing_org.name")

    class Meta:
        model = PMAppointment
        fields = [
            "id",
            "user",
            "governing_org_id",
            "governing_org_name",
            "name",
            "active",
        ]


class ProgressSerializer(serializers.ModelSerializer):
    author = PersonSerializer(read_only=True)
    author_org_name = serializers.CharField(source="author_org.name")

    class Meta:
        model = ProgressEntry
        fields = [
            "id",
            "done",
            "next_step",
            "blocker",
            "author",
            "author_org_name",
            "created_at",
            "version",
            "previous_id",
        ]


class PersonProgressSerializer(ProgressSerializer):
    def to_representation(self, obj):
        data = super().to_representation(obj)
        project = obj.project if obj.project_id else (obj.work.project if obj.work_id and obj.work.context == "PROJECT_TASK" else None)
        summary = bool(project and not can_read_project_detail(self.context["request"].user, project))
        data["visibility"] = "SUMMARY" if summary else "DETAIL"
        data["context_type"] = "project" if obj.project_id else ("work" if obj.work_id else "case")
        data["context_id"] = str(obj.project_id or obj.work_id or obj.case_id)
        if summary:
            data["done"] = "Proje katkısının teknik ayrıntıları sınırlı erişimdedir."
            data["next_step"] = ""
            data["blocker"] = ""
        return data


class SLASerializer(serializers.ModelSerializer):
    is_overdue = serializers.SerializerMethodField()

    def get_is_overdue(self, obj):
        return obj.stopped_at is None and obj.current_due_at < timezone.now()

    class Meta:
        model = SLAInstance
        fields = [
            "id",
            "started_at",
            "original_due_at",
            "current_due_at",
            "stopped_at",
            "breached_at",
            "revision",
            "policy_snapshot",
            "is_overdue",
            "version",
        ]


class WorkSerializer(serializers.ModelSerializer):
    assigned_to = PersonSerializer(read_only=True)
    assigned_to_id = serializers.UUIDField(read_only=True)
    owner_org_name = serializers.CharField(source="owner_org.name")
    owner_name = serializers.CharField(source="assigned_to.display_name")
    sla = SLASerializer(read_only=True)
    contributions = ProgressSerializer(many=True, read_only=True)
    permissions = serializers.SerializerMethodField()
    parent_id = serializers.SerializerMethodField()

    def get_parent_id(self, obj):
        return (
            str(obj.parent_id)
            if obj.parent_id and can_read_work(self.context["request"].user, obj.parent)
            else None
        )

    def get_permissions(self, obj):
        u = self.context["request"].user
        return {
            "manage": can_manage_work(u, obj),
            "update": can_update_work(u, obj),
            "accept": can_manage_work(u, obj) and obj.assigned_to_id != u.id,
        }

    class Meta:
        model = WorkItem
        fields = [
            "id",
            "title",
            "description",
            "expected_outcome",
            "context",
            "kind",
            "project_id",
            "case_id",
            "parent_id",
            "shared_parent_summary",
            "mandatory",
            "owner_org_id",
            "owner_org_name",
            "assigned_to",
            "assigned_to_id",
            "owner_name",
            "created_by_id",
            "assignment_version",
            "formal",
            "priority",
            "status",
            "due_at",
            "result",
            "blocker",
            "completed_at",
            "version",
            "created_at",
            "updated_at",
            "sla",
            "contributions",
            "permissions",
        ]


class PersonWorkSerializer(WorkSerializer):
    """Resource visibility does not expose the project's technical work notes."""

    def to_representation(self, obj):
        data = super().to_representation(obj)
        user = self.context["request"].user
        summary_only = obj.context == "PROJECT_TASK" and not can_read_project_detail(user, obj.project)
        data["visibility"] = "SUMMARY" if summary_only else "DETAIL"
        if summary_only:
            for field in ("description", "expected_outcome", "result", "blocker", "shared_parent_summary"):
                data[field] = ""
            data["contributions"] = []
        return data


class ProjectSerializer(serializers.ModelSerializer):
    pm = PersonSerializer(source="appointment.user", read_only=True)
    appointment_id = serializers.UUIDField(read_only=True)
    owner_org_name = serializers.CharField(source="owner_org.name")
    owner_name = serializers.CharField(source="appointment.user.display_name")
    members = serializers.SerializerMethodField()
    contributions = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    audience_ids = serializers.SerializerMethodField()

    def get_audience_ids(self, obj):
        return list(obj.audience.values_list("id", flat=True))

    def get_members(self, obj):
        user = self.context["request"].user
        members = obj.members.filter(projectmembership__active=True, is_active=True)
        if not can_read_project_detail(user, obj):
            scope = project_resource_scope_ids(user, obj)
            members = (
                members.filter(primary_org_id__in=scope) if scope else members.none()
            )
        return PersonSerializer(members, many=True).data

    def get_contributions(self, obj):
        user = self.context["request"].user
        entries = [
            entry
            for entry in obj.contributions.select_related("author", "author_org")
            if can_read_progress(user, entry)
        ]
        return ProgressSerializer(entries, many=True, context=self.context).data

    def to_representation(self, obj):
        data = super().to_representation(obj)
        user = self.context["request"].user
        full = can_read_project_detail(user, obj)
        data["visibility"] = "DETAIL" if full else "SUMMARY"
        if not full:
            revision = obj.revisions.filter(number=obj.published_revision).first()
            content = revision.content if revision else {}
            data["title"] = content.get("title", obj.title)
            data["expected_outcome"] = content.get("expected_outcome", "")
            data["description"] = content.get("expected_outcome", "")
            data["progress_note"] = ""
            data["approval_note"] = ""
            data["audience_ids"] = []
            data["submitted_revision"] = None
        return data

    def get_permissions(self, obj):
        u = self.context["request"].user
        return {
            "manage": can_manage_project(u, obj),
            "approve": can_approve_project(u, obj),
            "submit": obj.created_by_id == u.id and obj.status in ["DRAFT", "REVISION"],
            "edit": (obj.created_by_id == u.id and obj.status in ["DRAFT", "REVISION"])
            or can_manage_project(u, obj),
        }

    class Meta:
        model = Project
        fields = [
            "id",
            "title",
            "description",
            "expected_outcome",
            "created_by_id",
            "owner_org_id",
            "owner_org_name",
            "appointment_id",
            "pm",
            "owner_name",
            "status",
            "priority",
            "due_at",
            "progress",
            "progress_note",
            "published_revision",
            "submitted_revision",
            "approval_note",
            "members",
            "audience_ids",
            "version",
            "created_at",
            "updated_at",
            "contributions",
            "permissions",
        ]


class CaseSerializer(serializers.ModelSerializer):
    coordinator = PersonSerializer(read_only=True)
    owner_name = serializers.CharField(source="coordinator.display_name")
    owner_org_name = serializers.CharField(source="owner_org.name")
    members = PersonSerializer(many=True, read_only=True)
    sla = SLASerializer(read_only=True)
    contributions = ProgressSerializer(many=True, read_only=True)
    permissions = serializers.SerializerMethodField()

    def get_permissions(self, obj):
        u = self.context["request"].user
        return {"manage": can_manage_case(u, obj), "verify": can_verify_case(u, obj)}

    class Meta:
        model = Case
        fields = [
            "id",
            "title",
            "description",
            "kind",
            "priority",
            "status",
            "owner_org_id",
            "owner_org_name",
            "created_by_id",
            "coordinator",
            "owner_name",
            "verifier_id",
            "members",
            "closure_summary",
            "verification_evidence",
            "closed_at",
            "sla",
            "contributions",
            "permissions",
            "version",
            "created_at",
            "updated_at",
        ]


class PersonCaseSerializer(CaseSerializer):
    due_at = serializers.DateTimeField(source="sla.current_due_at", read_only=True, default=None)

    class Meta(CaseSerializer.Meta):
        fields = CaseSerializer.Meta.fields + ["due_at"]


class NoticeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseNotice
        fields = [
            "id",
            "title",
            "description",
            "created_by_id",
            "owner_org_id",
            "status",
            "case_id",
            "version",
            "created_at",
        ]


class ParticipationSerializer(serializers.ModelSerializer):
    user = PersonSerializer(read_only=True)
    target_org_name = serializers.CharField(source="target_org.name")

    class Meta:
        model = ParticipationRequest
        fields = [
            "id",
            "project_id",
            "case_id",
            "user",
            "target_org_id",
            "target_org_name",
            "summary",
            "status",
            "decision_note",
            "decided_by_id",
            "version",
            "created_at",
        ]


class AnnouncementSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="created_by.display_name")
    permissions = serializers.SerializerMethodField()

    def get_permissions(self, obj) -> dict:
        request = self.context.get("request")
        if not request or getattr(request, "auth", None):
            return {"publish": False, "withdraw": False}
        return {
            "publish": (
                obj.status == "DRAFT"
                and (obj.ends_at is None or obj.ends_at > timezone.now())
                and can_publish_announcement(request.user, obj)
            ),
            "withdraw": obj.status != "WITHDRAWN" and can_manage_org(request.user, obj.owner_org_id),
        }

    class Meta:
        model = Announcement
        fields = [
            "id",
            "title",
            "body",
            "owner_org_id",
            "all_cs",
            "status",
            "starts_at",
            "ends_at",
            "pinned",
            "author_name",
            "permissions",
            "version",
            "created_at",
        ]


class CardSerializer(serializers.ModelSerializer):
    author = PersonSerializer(source="created_by", read_only=True)
    owner_org_name = serializers.CharField(source="owner_org.name")
    interest_count = serializers.SerializerMethodField()
    interested = serializers.SerializerMethodField()
    source_accessible = serializers.SerializerMethodField()
    source_id = serializers.SerializerMethodField()
    source_type = serializers.SerializerMethodField()

    def get_interest_count(self, obj):
        return obj.interests.count()

    def get_interested(self, obj):
        return obj.interests.filter(pk=self.context["request"].user.pk).exists()

    def get_source_accessible(self, obj):
        return bool(
            obj.source_id
            and report_source(
                self.context["request"].user, obj.source_type, obj.source_id
            )
        )

    def get_source_id(self, obj):
        return obj.source_id if self.get_source_accessible(obj) else None

    def get_source_type(self, obj):
        return obj.source_type if self.get_source_accessible(obj) else None

    class Meta:
        model = CommunityCard
        fields = [
            "id",
            "title",
            "body",
            "kind",
            "author",
            "owner_org_name",
            "owner_org_id",
            "source_type",
            "source_id",
            "source_accessible",
            "status",
            "all_cs",
            "interest_count",
            "interested",
            "version",
            "created_at",
        ]


class PollSerializer(serializers.ModelSerializer):
    result = serializers.SerializerMethodField()
    my_choices = serializers.SerializerMethodField()

    def get_result(self, obj):
        counts = {str(o["id"]): 0 for o in obj.options}
        responses = list(obj.responses.all())
        for r in responses:
            for c in r.choices:
                counts[str(c)] = counts.get(str(c), 0) + 1
        return {
            "options": counts,
            "responded": len(responses),
            "eligible": len(obj.elector_ids),
            "unanswered": max(0, len(obj.elector_ids) - len(responses)),
            "elector_version": obj.elector_version,
        }

    def get_my_choices(self, obj):
        r = obj.responses.filter(user=self.context["request"].user).first()
        return r.choices if r else None

    class Meta:
        model = Poll
        fields = [
            "id",
            "question",
            "options",
            "max_choices",
            "closes_at",
            "result",
            "my_choices",
            "version",
        ]


class EventSerializer(serializers.ModelSerializer):
    polls = PollSerializer(many=True, read_only=True)
    rsvp = serializers.SerializerMethodField()
    counts = serializers.SerializerMethodField()
    owner_org_name = serializers.CharField(source="owner_org.name")
    permissions = serializers.SerializerMethodField()
    invitee_ids = serializers.SerializerMethodField()
    my_attendance = serializers.SerializerMethodField()

    def get_permissions(self, obj) -> dict:
        user = self.context["request"].user
        return {
            "manage": can_manage_org(user, obj.owner_org_id),
            "rsvp": obj.invitees.filter(pk=user.pk).exists(),
        }

    def get_invitee_ids(self, obj) -> list[str]:
        if not can_manage_org(self.context["request"].user, obj.owner_org_id):
            return []
        return [str(pk) for pk in obj.invitees.values_list("id", flat=True)]

    def get_my_attendance(self, obj) -> bool | None:
        return (
            obj.attendance.filter(user=self.context["request"].user)
            .values_list("present", flat=True)
            .first()
        )

    def get_rsvp(self, obj):
        r = obj.responses.filter(user=self.context["request"].user).first()
        return r.answer if r else None

    def get_counts(self, obj):
        counts = {
            a: obj.responses.filter(answer=a).count() for a in ["YES", "NO", "MAYBE"]
        }
        counts["unanswered"] = obj.invitees.count() - obj.responses.count()
        counts["attended"] = obj.attendance.filter(present=True).count()
        counts["invited"] = obj.invitees.count()
        return counts

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "description",
            "location",
            "starts_at",
            "ends_at",
            "owner_org_id",
            "owner_org_name",
            "created_by_id",
            "status",
            "polls",
            "rsvp",
            "counts",
            "permissions",
            "invitee_ids",
            "my_attendance",
            "invitee_version",
            "version",
            "created_at",
        ]


class CredentialSerializer(serializers.ModelSerializer):
    user = PersonSerializer(read_only=True)
    permissions = serializers.SerializerMethodField()

    def get_permissions(self, obj) -> dict:
        return {
            "manage": can_manage_org(
                self.context["request"].user, obj.user.primary_org_id
            )
        }

    class Meta:
        model = Credential
        fields = [
            "id",
            "user",
            "name",
            "issuer",
            "issued_on",
            "expires_on",
            "no_expiry",
            "important",
            "verification_status",
            "reference",
            "alert_days",
            "permissions",
            "version",
            "created_at",
        ]


class ReportSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="created_by.display_name")
    job_status = serializers.CharField(source="job.status", default=None)
    permissions = serializers.SerializerMethodField()

    def get_permissions(self, obj) -> dict:
        request = self.context["request"]
        return {
            "manage": not bool(getattr(request, "auth", None))
            and obj.created_by_id == request.user.pk
        }

    class Meta:
        model = Report
        fields = [
            "id",
            "title",
            "period_start",
            "period_end",
            "status",
            "sources",
            "markdown",
            "generated_mode",
            "content_hash",
            "approved_by_id",
            "job_id",
            "job_status",
            "author_name",
            "created_by_id",
            "permissions",
            "version",
            "created_at",
            "updated_at",
        ]


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    def get_is_read(self, obj) -> bool:
        return obj.read_at is not None

    def get_url(self, obj) -> str | None:
        urls = self.context.get("notification_urls", {})
        if str(obj.pk) in urls:
            return urls[str(obj.pk)]
        request = self.context.get("request")
        if not request:
            return None
        from .notifications import notification_access
        return notification_access(request.user, obj)[1]

    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "resource_type",
            "resource_id",
            "read_at",
            "is_read",
            "url",
            "created_at",
        ]


class AuditSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.display_name", default="Sistem")

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "created_at",
            "actor_name",
            "action",
            "object_type",
            "object_id",
            "data",
        ]


class SLAPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = SLAPolicy
        fields = [
            "id",
            "priority",
            "context",
            "amount",
            "unit",
            "warning_percent",
            "active",
            "version",
            "created_at",
        ]


class ApiClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiClient
        fields = ["id", "name", "scopes", "org_node_id", "active", "version"]


class ReportSelectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportSelection
        fields = ["id", "source_type", "source_id", "week_start", "version"]
