import uuid
from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class Record(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True


class OrgNode(Record):
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=180)
    kind = models.CharField(max_length=20, default="UNIT")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    active = models.BooleanField(default=True)
    is_demo = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    expertise = models.JSONField(default=list)
    contact = models.CharField(max_length=180, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(max_length=160, blank=True)
    primary_org = models.ForeignKey(
        OrgNode, null=True, blank=True, on_delete=models.PROTECT, related_name="people"
    )
    expertise = models.JSONField(default=list)
    identity_source = models.CharField(max_length=20, default="local")
    profile_kind = models.CharField(
        max_length=24,
        choices=[
            ("LOCAL", "Yerel kullanıcı"),
            ("LDAP", "Kurumsal dizin"),
            ("OFFICIAL_REFERENCE", "Organizasyon şeması referansı"),
            ("DEMO", "Örnek kullanıcı"),
        ],
        default="LOCAL",
    )
    access_version = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.display_name or self.username


class RoleGrant(Record):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_grants")
    role = models.CharField(max_length=40)
    org_node = models.ForeignKey(
        OrgNode, null=True, blank=True, on_delete=models.PROTECT
    )
    includes_descendants = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    granted_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    permissions = models.JSONField(default=list)


class PMAppointment(Record):
    user = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="pm_appointments"
    )
    governing_org = models.ForeignKey(OrgNode, on_delete=models.PROTECT)
    name = models.CharField(max_length=160, default="Siber Güvenlik Portföyü")
    active = models.BooleanField(default=True)


class Project(Record):
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    expected_outcome = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="proposals"
    )
    owner_org = models.ForeignKey(OrgNode, on_delete=models.PROTECT)
    appointment = models.ForeignKey(PMAppointment, on_delete=models.PROTECT)
    status = models.CharField(max_length=30, default="DRAFT")
    priority = models.CharField(max_length=20, default="NORMAL")
    due_at = models.DateTimeField(null=True, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    progress_note = models.TextField(blank=True)
    published_revision = models.PositiveIntegerField(null=True)
    submitted_revision = models.PositiveIntegerField(null=True)
    approval_note = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="+"
    )
    audience = models.ManyToManyField(
        OrgNode, related_name="published_projects", blank=True
    )
    members = models.ManyToManyField(
        User,
        through="ProjectMembership",
        through_fields=("project", "user"),
        related_name="projects",
    )

    class Meta:
        ordering = ["-updated_at"]


class ProjectRevision(Record):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="revisions"
    )
    number = models.PositiveIntegerField()
    content = models.JSONField()
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    decision = models.CharField(max_length=20, default="PENDING")
    decided_by = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="+"
    )
    decision_note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "number"], name="project_revision_unique"
            )
        ]


class ProjectMembership(Record):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    role = models.CharField(max_length=30, default="MEMBER")
    active = models.BooleanField(default=True)
    accepted_by = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user"], name="project_member_unique"
            )
        ]


class ProjectAuthorityGrant(Record):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="authorities"
    )
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    granted_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    permissions = models.JSONField(default=list)
    expires_at = models.DateTimeField()
    active = models.BooleanField(default=True)
    reason = models.TextField()


class ParticipationRequest(Record):
    project = models.ForeignKey(
        Project, null=True, on_delete=models.CASCADE, related_name="resource_requests"
    )
    case = models.ForeignKey(
        "Case", null=True, on_delete=models.CASCADE, related_name="resource_requests"
    )
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    target_org = models.ForeignKey(OrgNode, on_delete=models.PROTECT)
    summary = models.TextField()
    status = models.CharField(max_length=20, default="PENDING")
    decision_note = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(project__isnull=False, case__isnull=True)
                    | Q(project__isnull=True, case__isnull=False)
                ),
                name="participation_one_context",
            )
        ]


class Case(Record):
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=30, default="SECURITY_INCIDENT")
    priority = models.CharField(max_length=20, default="HIGH")
    status = models.CharField(max_length=30, default="NEW")
    owner_org = models.ForeignKey(OrgNode, on_delete=models.PROTECT)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    coordinator = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="coordinated_cases"
    )
    verifier = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="+"
    )
    members = models.ManyToManyField(User, related_name="case_memberships", blank=True)
    closure_summary = models.TextField(blank=True)
    verification_evidence = models.TextField(blank=True)
    closure_requested_by = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="+"
    )
    closed_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-updated_at"]


class CaseNotice(Record):
    title = models.CharField(max_length=240)
    description = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    owner_org = models.ForeignKey(OrgNode, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default="PENDING")
    case = models.ForeignKey(Case, null=True, on_delete=models.PROTECT)


class WorkItem(Record):
    CONTEXTS = [
        ("UNIT_WORK", "Unit işi"),
        ("PROJECT_TASK", "Proje görevi"),
        ("CASE_ACTION", "Vaka aksiyonu"),
    ]
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    expected_outcome = models.TextField(blank=True)
    context = models.CharField(max_length=20, choices=CONTEXTS, default="UNIT_WORK")
    kind = models.CharField(max_length=20, default="TASK")
    project = models.ForeignKey(
        Project, null=True, on_delete=models.PROTECT, related_name="tasks"
    )
    case = models.ForeignKey(
        Case, null=True, on_delete=models.PROTECT, related_name="actions"
    )
    parent = models.ForeignKey(
        "self", null=True, on_delete=models.PROTECT, related_name="children"
    )
    shared_parent_summary = models.TextField(blank=True)
    mandatory = models.BooleanField(default=True)
    owner_org = models.ForeignKey(OrgNode, on_delete=models.PROTECT)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_work"
    )
    assigned_to = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="assigned_work"
    )
    assignment_version = models.PositiveIntegerField(default=1)
    formal = models.BooleanField(default=False)
    priority = models.CharField(max_length=20, default="NORMAL")
    status = models.CharField(max_length=30, default="OPEN")
    due_at = models.DateTimeField(null=True, blank=True)
    result = models.TextField(blank=True)
    blocker = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True)
    accepted_by = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(context="UNIT_WORK", project__isnull=True, case__isnull=True)
                    | Q(
                        context="PROJECT_TASK", project__isnull=False, case__isnull=True
                    )
                    | Q(context="CASE_ACTION", project__isnull=True, case__isnull=False)
                ),
                name="work_one_context",
            )
        ]


class SLAPolicy(Record):
    priority = models.CharField(max_length=20)
    context = models.CharField(max_length=20, default="ALL")
    amount = models.PositiveIntegerField()
    unit = models.CharField(max_length=15)
    warning_percent = models.PositiveSmallIntegerField(default=80)
    active = models.BooleanField(default=True)


class SLAInstance(Record):
    work = models.OneToOneField(
        WorkItem, null=True, on_delete=models.CASCADE, related_name="sla"
    )
    case = models.OneToOneField(
        Case, null=True, on_delete=models.CASCADE, related_name="sla"
    )
    policy_snapshot = models.JSONField()
    started_at = models.DateTimeField()
    original_due_at = models.DateTimeField()
    current_due_at = models.DateTimeField()
    stopped_at = models.DateTimeField(null=True)
    breached_at = models.DateTimeField(null=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(work__isnull=False, case__isnull=True)
                    | Q(work__isnull=True, case__isnull=False)
                ),
                name="sla_one_context",
            )
        ]


class SLAEvent(Record):
    sla = models.ForeignKey(
        SLAInstance, on_delete=models.CASCADE, related_name="events"
    )
    key = models.CharField(max_length=180, unique=True)
    kind = models.CharField(max_length=30)
    threshold_at = models.DateTimeField()
    data = models.JSONField(default=dict)


class ProgressEntry(Record):
    project = models.ForeignKey(
        Project, null=True, on_delete=models.PROTECT, related_name="contributions"
    )
    case = models.ForeignKey(
        Case, null=True, on_delete=models.PROTECT, related_name="contributions"
    )
    work = models.ForeignKey(
        WorkItem, null=True, on_delete=models.PROTECT, related_name="contributions"
    )
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    author_org = models.ForeignKey(OrgNode, on_delete=models.PROTECT)
    done = models.TextField()
    next_step = models.TextField(blank=True)
    blocker = models.TextField(blank=True)
    previous = models.ForeignKey("self", null=True, on_delete=models.PROTECT)


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    actor = models.ForeignKey(User, null=True, on_delete=models.PROTECT)
    real_actor = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="+"
    )
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    data = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]


class Notification(Record):
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    resource_type = models.CharField(max_length=60, blank=True)
    resource_id = models.CharField(max_length=80, blank=True)
    read_at = models.DateTimeField(null=True)
    dedup_key = models.CharField(max_length=240, unique=True)


class OutboxEvent(Record):
    key = models.CharField(max_length=240, unique=True)
    recipient = models.ForeignKey(User, on_delete=models.PROTECT)
    channel = models.CharField(max_length=20, default="email")
    title = models.CharField(max_length=200)
    resource_type = models.CharField(max_length=60)
    resource_id = models.CharField(max_length=80)
    status = models.CharField(max_length=32, default="PENDING")
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    lease_until = models.DateTimeField(null=True)
    lease_token = models.UUIDField(null=True)
    last_error = models.CharField(max_length=300, blank=True)
    sent_at = models.DateTimeField(null=True)


class BackgroundJob(Record):
    kind = models.CharField(max_length=50)
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default="PENDING")
    checkpoint = models.JSONField(default=dict)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    lease_until = models.DateTimeField(null=True)
    lease_token = models.UUIDField(null=True)
    result = models.JSONField(default=dict)
    last_error = models.CharField(max_length=300, blank=True)


class IdempotencyRecord(Record):
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    key = models.UUIDField()
    operation = models.CharField(max_length=180)
    payload_hash = models.CharField(max_length=64)
    access_fingerprint = models.CharField(max_length=64, blank=True)
    response = models.JSONField(default=dict)
    status_code = models.PositiveSmallIntegerField(default=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "key"], name="idempotency_actor_key"
            )
        ]


class Announcement(Record):
    title = models.CharField(max_length=240)
    body = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    owner_org = models.ForeignKey(OrgNode, on_delete=models.PROTECT)
    audience = models.ManyToManyField(OrgNode, blank=True, related_name="+")
    all_cs = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="DRAFT")
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True)
    pinned = models.BooleanField(default=False)


class CommunityCard(Record):
    title = models.CharField(max_length=240)
    body = models.TextField()
    kind = models.CharField(max_length=30, default="SUCCESS")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    owner_org = models.ForeignKey(OrgNode, on_delete=models.PROTECT)
    source_type = models.CharField(max_length=30, blank=True)
    source_id = models.CharField(max_length=80, blank=True)
    source_version = models.PositiveIntegerField(null=True)
    status = models.CharField(max_length=20, default="DRAFT")
    audience = models.ManyToManyField(OrgNode, blank=True, related_name="+")
    all_cs = models.BooleanField(default=False)
    published_by = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="+"
    )
    content_approved_by = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="+"
    )
    interests = models.ManyToManyField(
        User, blank=True, related_name="interested_cards"
    )


class Event(Record):
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    starts_at = models.DateTimeField(null=True)
    ends_at = models.DateTimeField(null=True)
    owner_org = models.ForeignKey(OrgNode, on_delete=models.PROTECT)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default="PLANNED")
    invitees = models.ManyToManyField(User, related_name="invited_events", blank=True)
    invitee_version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["starts_at"]


class EventRSVP(Record):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="responses")
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    answer = models.CharField(max_length=20)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "user"], name="event_rsvp_unique")
        ]


class EventAttendance(Record):
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="attendance"
    )
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    present = models.BooleanField()
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"], name="event_attendance_unique"
            )
        ]


class Poll(Record):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="polls")
    question = models.CharField(max_length=300)
    options = models.JSONField(default=list)
    max_choices = models.PositiveSmallIntegerField(default=1)
    closes_at = models.DateTimeField()
    elector_ids = models.JSONField(default=list)
    elector_version = models.PositiveIntegerField(default=1)


class PollResponse(Record):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="responses")
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    choices = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["poll", "user"], name="poll_response_unique"
            )
        ]


class Credential(Record):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="credentials")
    name = models.CharField(max_length=200)
    issuer = models.CharField(max_length=180)
    issued_on = models.DateField(null=True)
    expires_on = models.DateField(null=True)
    no_expiry = models.BooleanField(default=False)
    important = models.BooleanField(default=False)
    verification_status = models.CharField(max_length=20, default="DECLARED")
    reference = models.CharField(max_length=300, blank=True)
    alert_days = models.PositiveIntegerField(default=30)


class ReportSelection(Record):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    source_type = models.CharField(max_length=30)
    source_id = models.UUIDField()
    week_start = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "source_type", "source_id", "week_start"],
                name="report_selection_unique",
            )
        ]


class Report(Record):
    title = models.CharField(max_length=240)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, default="DRAFT")
    sources = models.JSONField(default=list)
    markdown = models.TextField(blank=True)
    generated_mode = models.CharField(max_length=30, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    approved_by = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="+"
    )
    job = models.ForeignKey(BackgroundJob, null=True, on_delete=models.SET_NULL)


class ApiClient(Record):
    name = models.CharField(max_length=180)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    scopes = models.JSONField(default=list)
    active = models.BooleanField(default=True)
    org_node = models.ForeignKey(OrgNode, null=True, on_delete=models.PROTECT)
    token_version = models.PositiveIntegerField(default=1)


class ProjectTeamPlan(Record):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="team_plans"
    )
    org = models.ForeignKey(OrgNode, on_delete=models.PROTECT)
    weight = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "org"], name="project_team_plan_unique"
            ),
            models.CheckConstraint(
                condition=Q(weight__gte=1, weight__lte=100),
                name="project_team_weight_valid",
            ),
        ]


class ProjectDeliverable(Record):
    plan = models.ForeignKey(
        ProjectTeamPlan, on_delete=models.PROTECT, related_name="deliverables"
    )
    title = models.CharField(max_length=240)
    kind = models.CharField(max_length=20, default="DELIVERABLE")
    weight = models.PositiveSmallIntegerField(default=1)
    progress = models.PositiveSmallIntegerField(default=0)
    evidence = models.TextField(blank=True)
    quality_rating = models.PositiveSmallIntegerField(null=True)
    due_at = models.DateTimeField(null=True)
    updated_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(weight__gte=1, weight__lte=100),
                name="project_delivery_weight_valid",
            ),
            models.CheckConstraint(
                condition=Q(progress__lte=100), name="project_delivery_progress_valid"
            ),
            models.CheckConstraint(
                condition=Q(quality_rating__isnull=True)
                | Q(quality_rating__gte=1, quality_rating__lte=5),
                name="project_delivery_quality_valid",
            ),
        ]


class ProjectProgressSnapshot(Record):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="progress_snapshots"
    )
    scores = models.JSONField(default=dict)
    teams = models.JSONField(default=list)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)


class ProjectClosureSurvey(Record):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="closure_surveys"
    )
    title = models.CharField(max_length=240)
    questions = models.JSONField(default=list)
    status = models.CharField(max_length=20, default="OPEN")
    invitees = models.ManyToManyField(User, related_name="project_closure_surveys")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    closes_at = models.DateTimeField()


class ProjectSurveyResponse(Record):
    survey = models.ForeignKey(
        ProjectClosureSurvey, on_delete=models.CASCADE, related_name="responses"
    )
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    answers = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["survey", "user"], name="project_survey_person_unique"
            )
        ]


class ProjectInsightReport(Record):
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="insight_reports"
    )
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=20)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, default="GENERATING")
    generated_mode = models.CharField(max_length=20, default="RULE_BASED")
    original_markdown = models.TextField(blank=True)
    markdown = models.TextField(blank=True)
    computed_values = models.JSONField(default=dict)
    reviewed_scores = models.JSONField(default=dict)
    sources = models.JSONField(default=list)
    source_hash = models.CharField(max_length=64)
    edit_reason = models.TextField(blank=True)
    job = models.OneToOneField(BackgroundJob, null=True, on_delete=models.PROTECT)
    published_by = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="+"
    )
    published_at = models.DateTimeField(null=True)


class ProjectInsightEdit(Record):
    report = models.ForeignKey(
        ProjectInsightReport, on_delete=models.CASCADE, related_name="edits"
    )
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    markdown = models.TextField()
    reviewed_scores = models.JSONField(default=dict)
    reason = models.TextField()


class Attachment(Record):
    """Private uploads are staged before the owning domain transaction claims them."""

    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="uploads")
    resource_type = models.CharField(max_length=32, blank=True)
    resource_id = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=180)
    storage_key = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    content_type = models.CharField(max_length=100)
    sha256 = models.CharField(max_length=64)
    status = models.CharField(max_length=24, default="PENDING_SCAN")
    scan_status = models.CharField(max_length=24, default="pending")
    upload_key = models.UUIDField(null=True, blank=True)
    bound_at = models.DateTimeField(null=True, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["resource_type", "resource_id"], name="attachment_resource_idx")]
        constraints = [
            models.CheckConstraint(
                condition=(Q(resource_type="", resource_id__isnull=True) | (~Q(resource_type="") & Q(resource_id__isnull=False))),
                name="attachment_context_pair",
            ),
            models.UniqueConstraint(fields=["uploaded_by", "upload_key"], condition=Q(upload_key__isnull=False), name="attachment_upload_request_unique"),
        ]


class RecordEmailPreference(models.Model):
    resource_type = models.CharField(max_length=32)
    resource_id = models.UUIDField()
    send_email = models.BooleanField(default=False)
    recipient_ids = models.JSONField(default=list)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["resource_type", "resource_id"], name="record_email_preference_unique")]
