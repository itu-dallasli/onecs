from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
import hashlib
import json
import uuid
from datetime import timedelta
from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.db.models import Q
from django.core.serializers.json import DjangoJSONEncoder
from django.core.exceptions import ValidationError as DjangoValidationError
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from django.views.decorators.csrf import csrf_protect
from rest_framework import viewsets
from rest_framework.decorators import (
    action,
    api_view,
    permission_classes,
    authentication_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
from .exceptions import Conflict
from .models import (
    Announcement,
    ApiClient,
    AuditEvent,
    BackgroundJob,
    Case,
    CaseNotice,
    CommunityCard,
    Credential,
    Event,
    EventAttendance,
    EventRSVP,
    IdempotencyRecord,
    Notification,
    OrgNode,
    PMAppointment,
    ParticipationRequest,
    Poll,
    PollResponse,
    ProgressEntry,
    Project,
    ProjectAuthorityGrant,
    ProjectMembership,
    ProjectRevision,
    Report,
    ReportSelection,
    RoleGrant,
    SLAEvent,
    SLAInstance,
    SLAPolicy,
    User,
    WorkItem,
)
from .policy import (
    active_grants,
    api_narrow,
    api_scope_ids,
    audience_visible,
    can_approve_project,
    can_manage_case,
    can_manage_org,
    can_manage_project,
    can_manage_work,
    can_open_case,
    can_read_progress,
    can_read_project_detail,
    can_read_work,
    can_reroute_project,
    can_update_work,
    can_verify_case,
    descendants_ids,
    has_role,
    is_director,
    is_system_admin,
    manager_scope_ids,
    report_source,
    require_admin,
    visible_announcements,
    visible_cards,
    visible_cases,
    visible_credentials,
    visible_org_ids,
    visible_participations,
    visible_projects,
    visible_work,
    can_read_project,
    can_read_case,
)
from .serializers import (
    AnnouncementSerializer,
    ApiClientSerializer,
    AuditSerializer,
    CardSerializer,
    CaseSerializer,
    CredentialSerializer,
    EventSerializer,
    NoticeSerializer,
    NotificationSerializer,
    OrgSerializer,
    PMSerializer,
    ParticipationSerializer,
    PersonSerializer,
    PollSerializer,
    ProgressSerializer,
    ProjectSerializer,
    ReportSelectionSerializer,
    ReportSerializer,
    SLAPolicySerializer,
    WorkSerializer,
    PersonWorkSerializer,
    PersonProgressSerializer,
    PersonCaseSerializer,
)
from .services import (
    TERMINAL,
    access_fingerprint,
    assign_work,
    audit,
    bump,
    check_version,
    contribute,
    create_sla,
    enqueue_notification,
    ensure,
    mark_breach,
    priority,
    report_hash,
    snapshot_source,
    source_visibility_valid,
    stop_sla,
)


def text(data, key, required=False, limit=10000):
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValidationError({key: "Metin girin."})
    value = value.strip()
    if required and not value:
        raise ValidationError({key: "Bu alan zorunludur."})
    if len(value) > limit:
        raise ValidationError({key: f"En fazla {limit} karakter."})
    return value


def timestamp(value, required=False):
    if not value:
        if required:
            raise ValidationError("Tarih zorunludur.")
        return None
    try:
        dt = parse_datetime(str(value))
        if not dt:
            d = parse_date(str(value))
            if d:
                dt = timezone.make_aware(
                    __import__("datetime").datetime.combine(
                        d, __import__("datetime").time(23, 59, 59)
                    )
                )
    except (TypeError, ValueError):
        raise ValidationError("Geçerli ISO8601 tarih girin.")
    if not dt:
        raise ValidationError("Geçerli ISO8601 tarih girin.")
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


def date_value(value):
    try:
        return parse_date(str(value)[:10]) if value else None
    except (TypeError, ValueError):
        raise ValidationError("Geçerli takvim tarihi girin.")


def fetch(model, pk, **filters):
    try:
        return model.objects.get(pk=pk, **filters)
    except (model.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise NotFound("Kayıt bulunamadı.")


def unknown(data, allowed):
    extra = set(data) - set(allowed)
    if extra:
        raise ValidationError({k: "Bu alan bu işlemle değiştirilemez." for k in extra})


def require_org(user):
    if not user.primary_org_id:
        raise ValidationError("Kullanıcı için organizasyon üyeliği gerekir.")
    return user.primary_org


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def csrf_view(request):
    return Response(
        {"csrf_token": get_token(request), "test_mode": test_mode_data(request)}
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_protect
def login_view(request):
    if not isinstance(request.data, dict):
        raise ValidationError("JSON nesnesi gönderilmelidir.")
    username = text(request.data, "username", True, 150)
    password = request.data.get("password", "")
    method = request.data.get("method", "local")
    if not isinstance(password, str):
        raise ValidationError("Geçerli parola girin.")
    if method == "ldap":
        try:
            from administration.services import authenticate_ldap

            user = authenticate_ldap(username, password)
        except ImportError:
            raise ValidationError("LDAP bağlantısı henüz yapılandırılmadı.")
    elif method == "local":
        user = authenticate(request, username=username, password=password)
        if user and user.identity_source != "local":
            user = None
    else:
        raise ValidationError("Geçersiz giriş yöntemi.")
    if not user or not user.is_active:
        return Response(
            {
                "detail": "Kullanıcı adı veya parola hatalı.",
                "code": "invalid_credentials",
            },
            status=401,
        )
    login(request, user)
    audit(user, "auth.login", user, {"method": method})
    return Response(me_data(user, request))


def me_data(user, request):
    roles = [
        {
            "role": g.role,
            "org_id": str(g.org_node_id) if g.org_node_id else None,
            "permissions": g.permissions,
        }
        for g in active_grants(user)
    ]
    return {
        **PersonSerializer(user).data,
        "primary_org": OrgSerializer(user.primary_org).data
        if user.primary_org_id
        else None,
        "roles": roles,
        "permissions": {
            "manage_unit": bool(manager_scope_ids(user)),
            "manage_projects": user.pm_appointments.filter(active=True).exists()
            or any(
                can_manage_project(user, p)
                for p in Project.objects.select_related("appointment__user")
            ),
            "create_case": can_open_case(user, user.primary_org_id),
            "system_admin": is_system_admin(user),
            "director": is_director(user),
        },
        "csrf_token": get_token(request),
        "test_mode": test_mode_data(request),
    }


@api_view(["GET"])
def me_view(request):
    return Response(me_data(request.user, request))


@api_view(["POST"])
def logout_view(request):
    audit(request.user, "auth.logout", request.user)
    logout(request)
    return Response({"detail": "Oturum kapatıldı."})


class DomainViewSet(viewsets.GenericViewSet):
    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        query = request.query_params.get("search", "").strip()
        if query:
            if "title" in [f.name for f in qs.model._meta.fields]:
                qs = qs.filter(title__icontains=query)
        total = qs.count()
        return Response(
            {"results": self.get_serializer(qs[:500], many=True).data, "count": total}
        )

    def retrieve(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)

    def dispatch(self, request, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        request = self.initialize_request(request, *args, **kwargs)
        self.request = request
        self.headers = self.default_response_headers
        with transaction.atomic():
            try:
                self.initial(request, *args, **kwargs)
                if request.method in ("POST", "PUT", "PATCH") and not isinstance(
                    request.data, dict
                ):
                    raise ValidationError("JSON nesnesi gönderilmelidir.")
                key = request.headers.get("X-Request-ID")
                record = None
                digest = None
                uid = None
                if request.method in ("POST", "PATCH", "PUT", "DELETE") and key:
                    try:
                        uid = uuid.UUID(key)
                    except ValueError:
                        raise ValidationError("X-Request-ID UUID olmalıdır.")
                    User.objects.select_for_update().get(pk=request.user.pk)
                    digest = hashlib.sha256(
                        request.method.encode()
                        + request.path.encode()
                        + json.dumps(
                            request.data,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        ).encode()
                    ).hexdigest()
                    fingerprint = access_fingerprint(request.user)
                    record = IdempotencyRecord.objects.filter(
                        actor=request.user, key=uid
                    ).first()
                    if record:
                        if record.payload_hash != digest:
                            raise Conflict(
                                "Aynı istek anahtarı farklı içerikle kullanılamaz."
                            )
                        if record.access_fingerprint != fingerprint:
                            raise PermissionDenied(
                                "İstekten sonra erişim kapsamı değişti. Yeni istek anahtarı kullanın."
                            )
                        if (
                            isinstance(record.response, dict)
                            and record.response.get("id")
                            and self.serializer_class
                        ):
                            if kwargs.get("pk") and str(record.response["id"]) != str(
                                kwargs["pk"]
                            ):
                                self.get_object()
                                response = Response(
                                    record.response, status=record.status_code
                                )
                            else:
                                obj = (
                                    self.get_queryset()
                                    .filter(pk=record.response["id"])
                                    .first()
                                )
                                if obj is None:
                                    raise NotFound("Kayıt bulunamadı.")
                                response = Response(
                                    self.get_serializer(obj).data,
                                    status=record.status_code,
                                )
                        else:
                            response = Response(
                                record.response, status=record.status_code
                            )
                    else:
                        response = None
                else:
                    response = None
                if response is None:
                    handler = getattr(
                        self, request.method.lower(), self.http_method_not_allowed
                    )
                    response = handler(request, *args, **kwargs)
                    if response.status_code < 400 and uid:
                        IdempotencyRecord.objects.create(
                            actor=request.user,
                            key=uid,
                            operation=request.path,
                            payload_hash=digest,
                            access_fingerprint=access_fingerprint(request.user),
                            response=json.loads(
                                json.dumps(response.data, cls=DjangoJSONEncoder)
                            ),
                            status_code=response.status_code,
                        )
            except Exception as exc:
                response = self.handle_exception(exc)
            if response.status_code >= 400:
                transaction.set_rollback(True)
            self.response = self.finalize_response(request, response, *args, **kwargs)
            return self.response

    def locked(self):
        obj = self.get_object()
        obj = type(obj).objects.select_for_update().get(pk=obj.pk)
        check_version(obj, self.request.data)
        return obj


class OrgViewSet(DomainViewSet):
    serializer_class = OrgSerializer

    def get_queryset(self):
        qs = OrgNode.objects.filter(active=True)
        client = getattr(self.request.user, "_api_client", None)
        return (
            qs.filter(pk__in=descendants_ids(client.org_node_id))
            if client and client.org_node_id
            else qs
        )

    def partial_update(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_org(request.user, obj.pk) or is_system_admin(request.user))
        unknown(request.data, {"version", "description", "expertise", "contact"})
        for key in ["description", "contact"]:
            if key in request.data:
                setattr(obj, key, text(request.data, key, limit=3000))
        if "expertise" in request.data:
            if (
                not isinstance(request.data["expertise"], list)
                or len(request.data["expertise"]) > 30
            ):
                raise ValidationError("En fazla 30 uzmanlık etiketi girin.")
            obj.expertise = [str(x)[:80] for x in request.data["expertise"]]
        bump(obj)
        audit(request.user, "organization.profile.updated", obj)
        return Response(self.get_serializer(obj).data)


class PeopleViewSet(DomainViewSet):
    serializer_class = PersonSerializer

    def get_queryset(self):
        qs = api_narrow(
            self.request.user,
            User.objects.filter(is_active=True).select_related("primary_org"),
            "primary_org_id",
        )
        if self.request.query_params.get("assignable") == "true":
            qs = qs.filter(primary_org_id__in=manager_scope_ids(self.request.user))
        org_id = self.request.query_params.get("org_id")
        if org_id:
            org = fetch(OrgNode, org_id, active=True)
            scope = (
                descendants_ids(org.pk)
                if self.request.query_params.get("include_descendants", "true")
                != "false"
                else {org.pk}
            )
            qs = qs.filter(
                Q(primary_org_id__in=scope)
                | Q(
                    role_grants__org_node_id__in=scope,
                    role_grants__active=True,
                    role_grants__role__in=["DIRECTOR", "UNIT_HEAD", "TEAM_MANAGER"],
                )
            ).distinct()
        role = self.request.query_params.get("role")
        if role:
            qs = (
                qs.filter(role_grants__role=role, role_grants__active=True)
                .filter(
                    Q(role_grants__expires_at__isnull=True)
                    | Q(role_grants__expires_at__gt=timezone.now())
                )
                .distinct()
            )
        query = self.request.query_params.get("search", "").strip()[:120]
        return (
            _search_matches(
                qs,
                ["display_name", "username", "primary_org__name", "expertise"],
                query,
            )
            if query
            else qs.order_by("display_name")
        )

    def list(self, request):
        qs = self.get_queryset()
        try:
            limit = int(request.query_params.get("limit", 500))
            offset = int(request.query_params.get("offset", 0))
        except (ValueError, TypeError):
            raise ValidationError("limit ve offset tam sayı olmalıdır.")
        if not 1 <= limit <= 500 or not 0 <= offset <= 100000:
            raise ValidationError("Geçerli sayfa boyutu/aralığı seçin.")
        count = qs.count()
        return Response(
            {
                "results": self.get_serializer(
                    qs[offset : offset + limit], many=True
                ).data,
                "count": count,
                "limit": limit,
                "offset": offset,
                "next_offset": offset + limit if offset + limit < count else None,
            }
        )

    @action(detail=True, methods=["get"])
    def contributions(self, request, pk=None):
        person = self.get_object()
        ensure(
            person.pk == request.user.pk
            or can_manage_org(request.user, person.primary_org_id)
        )
        entries = []
        for entry in (
            ProgressEntry.objects.filter(author=person)
            .select_related(
                "project__appointment__user",
                "case",
                "work__project__appointment__user",
                "work__case",
                "author",
                "author_org",
            )
            .order_by("-created_at")
        ):
            if can_read_progress(request.user, entry):
                entries.append(entry)
        return Response(
            {
                "results": ProgressSerializer(entries[:100], many=True).data,
                "count": len(entries),
            }
        )

    def _assignment_permissions(self, person):
        actor = self.request.user
        manager = bool(actor.is_active and person.is_active and person.primary_org_id and can_manage_org(actor, person.primary_org_id))
        assignable = manager and self.request.auth is None
        target = {"person_id": str(person.pk), "org_id": str(person.primary_org_id), "org_name": person.primary_org.name} if assignable else None
        return {
            "permissions": {
                "can_view_workload": bool(actor.is_active and person.is_active and (person.pk == actor.pk or manager)),
                "can_assign_work": assignable,
                "can_create_personal_work": bool(actor.is_active and person.pk == actor.pk and self.request.auth is None),
            },
            "assignment": {
                "context": "UNIT_WORK",
                "allowed_target": target,
                "suggested_payload": {"assignee_id": str(person.pk), "personal": False, "kind": "TASK", "priority": "NORMAL"} if assignable else None,
            },
        }

    @extend_schema(operation_id="people_assignable_scope", responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"], url_path="assignable-scope")
    def assignable_scope(self, request, pk=None):
        person = self.get_object()
        return Response({"person": self.get_serializer(person).data, **self._assignment_permissions(person)})

    @extend_schema(operation_id="people_workload", responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def workload(self, request, pk=None):
        person = self.get_object()
        access = self._assignment_permissions(person)
        ensure(access["permissions"]["can_view_workload"], "Kişinin iş ayrıntısını yalnız kendisi veya güncel organizasyon yöneticisi görebilir.")
        context = {"request": request}
        now = timezone.now()
        work_candidates = api_narrow(request.user, WorkItem.objects.filter(assigned_to=person).select_related("parent", "owner_org", "sla", "assigned_to__primary_org", "project__appointment__user", "project__appointment__governing_org", "case")).prefetch_related("contributions__author", "contributions__author_org")
        work_query = work_candidates.filter(pk__in=[item.pk for item in work_candidates if can_read_work(request.user, item)])
        work_total = work_query.count()
        open_work = work_query.exclude(status__in=TERMINAL)
        project_candidates = api_narrow(request.user, Project.objects.filter(Q(memberships__user=person, memberships__active=True) | Q(appointment__user=person, appointment__active=True)).distinct().select_related("appointment__user", "appointment__governing_org", "owner_org")).prefetch_related("memberships", "revisions", "contributions__author", "contributions__author_org", "audience")
        project_query = project_candidates.filter(pk__in=[item.pk for item in project_candidates if can_read_project(request.user, item)])
        case_candidates = api_narrow(request.user, Case.objects.filter(Q(coordinator=person) | Q(members=person) | Q(contributions__author=person) | Q(actions__assigned_to=person) | Q(actions__contributions__author=person)).distinct().select_related("sla", "owner_org", "coordinator__primary_org")).prefetch_related("members", "contributions__author", "contributions__author_org")
        case_query = case_candidates.filter(pk__in=[item.pk for item in case_candidates if can_read_case(request.user, item)])
        contribution_query = ProgressEntry.objects.filter(author=person).select_related("author", "author_org", "project__appointment__user", "project__appointment__governing_org", "case", "work__project__appointment__user", "work__project__appointment__governing_org", "work__assigned_to", "work__case")
        entries = [entry for entry in contribution_query.order_by("-created_at") if can_read_progress(request.user, entry)]
        projects = []
        for project in project_query.order_by("-updated_at")[:100]:
            data = ProjectSerializer(project, context=context).data
            membership = next((item for item in project.memberships.all() if item.user_id == person.pk and item.active), None)
            data["membership_role"] = "PROJECT_MANAGER" if project.appointment.user_id == person.pk else (membership.role if membership else "MEMBER")
            if data.get("visibility") == "SUMMARY":
                data["contributions"] = []
            projects.append(data)
        return Response({
            "person": self.get_serializer(person).data,
            "summary": {
                "work_total": work_total,
                "open_work": open_work.count(),
                "overdue_work": open_work.filter(due_at__lt=now).count(),
                "critical_work": open_work.filter(priority="CRITICAL").count(),
                "projects": project_query.count(),
                "cases": case_query.count(),
                "contributions": len(entries),
                "by_context": {kind: work_query.filter(context=kind).count() for kind in ("UNIT_WORK", "PROJECT_TASK", "CASE_ACTION")},
            },
            "works": PersonWorkSerializer(work_query.order_by("due_at", "-updated_at")[:200], many=True, context=context).data,
            "projects": projects,
            "cases": PersonCaseSerializer(case_query.order_by("-updated_at")[:100], many=True, context=context).data,
            "contributions": PersonProgressSerializer(entries[:100], many=True, context=context).data,
            "limits": {"works": 200, "projects": 100, "cases": 100, "contributions": 100},
            **access,
        })

    def partial_update(self, request, pk=None):
        person = self.get_object()
        ensure(
            person.pk == request.user.pk,
            "Uzmanlık beyanını yalnız kişi kendisi düzenleyebilir.",
        )
        unknown(request.data, {"expertise"})
        expertise = request.data.get("expertise", [])
        if (
            not isinstance(expertise, list)
            or len(expertise) > 30
            or any(
                not isinstance(item, str) or not item.strip() or len(item) > 80
                for item in expertise
            )
        ):
            raise ValidationError("En fazla 30 kısa uzmanlık etiketi girin.")
        person.expertise = list(dict.fromkeys(item.strip() for item in expertise))
        person.save(update_fields=["expertise"])
        audit(request.user, "person.expertise.updated", person)
        return Response(self.get_serializer(person).data)


class PMViewSet(DomainViewSet):
    serializer_class = PMSerializer

    def get_queryset(self):
        return api_narrow(
            self.request.user,
            PMAppointment.objects.filter(
                active=True, user__is_active=True
            ).select_related("user__primary_org", "governing_org"),
            "governing_org_id",
        )

    def create(self, request):
        person = fetch(User, request.data.get("user_id"), is_active=True)
        org = fetch(
            OrgNode, request.data.get("governing_org_id"), kind="UNIT", active=True
        )
        ensure(
            is_director(request.user)
            or active_grants(request.user)
            .filter(role="UNIT_HEAD", org_node=org)
            .exists()
        )
        ensure(
            person.primary_org_id in descendants_ids(org.pk),
            "PM görevi kişinin bağlı unitinde açılmalıdır.",
        )
        if PMAppointment.objects.filter(
            user=person, governing_org=org, active=True
        ).exists():
            raise ValidationError("Etkin PM görevi zaten var.")
        obj = PMAppointment.objects.create(
            user=person,
            governing_org=org,
            name=text(request.data, "name", False, 160) or "CS Proje Portföyü",
        )
        audit(
            request.user,
            "project.manager.appointed",
            obj,
            {"reason": text(request.data, "reason", True)},
        )
        return Response(self.get_serializer(obj).data, status=201)


class ProjectViewSet(DomainViewSet):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return visible_projects(self.request.user)

    def create(self, request):
        data = request.data
        unknown(
            data,
            {
                "title",
                "description",
                "expected_outcome",
                "appointment_id",
                "pm_id",
                "requesting_org_id",
                "priority",
                "due_at",
                "audience_ids",
            },
        )
        org = require_org(request.user)
        if data.get("requesting_org_id") and str(org.pk) != str(
            data["requesting_org_id"]
        ):
            raise PermissionDenied("Başvuru kaynak biriminizle oluşturulur.")
        appointment = PMAppointment.objects.filter(active=True, user__is_active=True)
        if data.get("appointment_id"):
            appointment = appointment.filter(pk=data["appointment_id"])
        elif data.get("pm_id"):
            appointment = appointment.filter(user_id=data["pm_id"])
        elif appointment.count() != 1:
            raise ValidationError({"pm_id": "İlgili proje yöneticisini seçin."})
        appointment = appointment.first()
        if not appointment:
            raise ValidationError({"pm_id": "Etkin proje yöneticisi bulunamadı."})
        obj = Project.objects.create(
            title=text(data, "title", True, 240),
            description=text(data, "description"),
            expected_outcome=text(data, "expected_outcome"),
            created_by=request.user,
            owner_org=org,
            appointment=appointment,
            priority=priority(data.get("priority", "NORMAL")),
            due_at=timestamp(data.get("due_at")),
        )
        obj.audience.add(org)
        audit(request.user, "project.draft.created", obj)
        return Response(self.get_serializer(obj).data, status=201)

    def partial_update(self, request, pk=None):
        obj = self.locked()
        data = request.data
        unknown(
            data,
            {
                "version",
                "title",
                "description",
                "expected_outcome",
                "due_at",
                "priority",
                "progress_note",
            },
        )
        ensure(
            obj.created_by_id == request.user.id
            and obj.status in ("DRAFT", "REVISION")
            or can_manage_project(request.user, obj)
        )
        if obj.published_revision and any(
            k in data for k in ("title", "description", "expected_outcome")
        ):
            raise ValidationError(
                "Yayınlı projenin ana kapsam değişikliği için yeni başvuru sürümü gerekir."
            )
        for key in ("title", "description", "expected_outcome", "progress_note"):
            if key in data:
                setattr(
                    obj,
                    key,
                    text(data, key, key == "title", 240 if key == "title" else 10000),
                )
        if "priority" in data:
            obj.priority = priority(data["priority"])
        if "due_at" in data:
            obj.due_at = timestamp(data["due_at"])
        bump(obj)
        audit(request.user, "project.updated", obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        obj = self.locked()
        ensure(obj.created_by_id == request.user.id)
        if obj.status not in ("DRAFT", "REVISION"):
            raise ValidationError("Yalnız taslak/düzeltme başvurusu gönderilebilir.")
        if not obj.appointment.active or not obj.appointment.user.is_active:
            raise ValidationError("Başvuru yönlendirmesi için etkin PM gerekir.")
        if not obj.description:
            raise ValidationError("Proje açıklamasını tamamlayın.")
        number = (
            (obj.revisions.order_by("-number").first().number + 1)
            if obj.revisions.exists()
            else 1
        )
        ProjectRevision.objects.create(
            project=obj,
            number=number,
            author=request.user,
            content={
                "title": obj.title,
                "description": obj.description,
                "expected_outcome": obj.expected_outcome,
                "due_at": obj.due_at.isoformat() if obj.due_at else None,
                "audience_ids": [
                    str(x) for x in obj.audience.values_list("id", flat=True)
                ],
            },
        )
        obj.submitted_revision = number
        obj.status = "SUBMITTED"
        bump(obj)
        recipients = [obj.appointment.user]
        if obj.appointment.user_id == request.user.pk:
            recipients = list(
                User.objects.filter(
                    role_grants__role="UNIT_HEAD",
                    role_grants__org_node=obj.appointment.governing_org,
                    role_grants__active=True,
                    is_active=True,
                )
                .exclude(pk=request.user.pk)
                .distinct()
            )
        for recipient in recipients:
            enqueue_notification(
                recipient,
                "Proje onayınızı bekliyor",
                "project",
                obj.pk,
                f"project-submit:{obj.pk}:{number}:{recipient.pk}",
            )
        audit(request.user, "project.submitted", obj, {"revision": number})
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        obj = self.locked()
        ensure(
            can_approve_project(request.user, obj),
            "Kendi başvurunuzu onaylayamazsınız; atanmış bağımsız proje yetkilisi gerekir.",
        )
        pending_change = bool(
            obj.published_revision
            and obj.submitted_revision
            and obj.submitted_revision > obj.published_revision
        )
        if obj.status != "SUBMITTED" and not pending_change:
            raise ValidationError("Başvuru karar beklemiyor.")
        decision = request.data.get("decision")
        note = text(request.data, "note")
        if decision not in ("APPROVE", "REVISION", "REJECT"):
            raise ValidationError("Geçersiz karar.")
        if decision != "APPROVE" and not note:
            raise ValidationError("Karar gerekçesi zorunludur.")
        revision = obj.revisions.select_for_update().get(number=obj.submitted_revision)
        if revision.decision != "PENDING":
            raise Conflict()
        ensure(
            revision.author_id != request.user.pk,
            "Kendi değişiklik başvurunuzu onaylayamazsınız.",
        )
        revision.decision = decision
        revision.decided_by = request.user
        revision.decision_note = note
        revision.save()
        obj.approval_note = note
        if not pending_change:
            obj.status = {
                "APPROVE": "PLANNED",
                "REVISION": "REVISION",
                "REJECT": "REJECTED",
            }[decision]
        if decision == "APPROVE":
            obj.published_revision = revision.number
            obj.approved_by = request.user
            if pending_change:
                content = revision.content
                obj.title = content["title"]
                obj.description = content.get("description", "")
                obj.expected_outcome = content.get("expected_outcome", "")
                obj.due_at = timestamp(content.get("due_at"))
                if "audience_ids" in content:
                    obj.audience.set(
                        OrgNode.objects.filter(
                            pk__in=content["audience_ids"], active=True
                        )
                    )
        bump(obj)
        audit(
            request.user,
            "project.reviewed",
            obj,
            {"decision": decision, "revision": revision.number},
        )
        enqueue_notification(
            obj.created_by,
            "Proje başvurunuz değerlendirildi",
            "project",
            obj.pk,
            f"project-decision:{obj.pk}:{revision.number}",
        )
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def progress(self, request, pk=None):
        obj = self.locked()
        ensure(
            can_manage_project(request.user, obj)
            or obj.memberships.filter(user=request.user, active=True).exists()
        )
        if obj.status not in ("PLANNED", "IN_PROGRESS", "WAITING"):
            raise ValidationError("Yayınlı etkin projede ilerleme girilebilir.")
        entry = contribute(request.user, obj, request.data)
        if "progress" in request.data:
            ensure(can_manage_project(request.user, obj))
            value = request.data["progress"]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= 100
            ):
                raise ValidationError("İlerleme 0–100 arasında olmalıdır.")
            obj.progress = value
            obj.progress_note = entry.done
        obj.status = "IN_PROGRESS"
        bump(obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["get", "post"])
    def members(self, request, pk=None):
        obj = self.get_object()
        if request.method == "GET":
            return Response({"results": self.get_serializer(obj).data["members"]})
        obj = self.locked()
        ensure(can_manage_project(request.user, obj))
        person = fetch(User, request.data.get("user_id"), is_active=True)
        if obj.status not in ("PLANNED", "IN_PROGRESS", "WAITING"):
            raise ValidationError("Kaynak talebi için onaylı proje gerekir.")
        if person.primary_org_id is None:
            raise ValidationError("Kişinin birimi tanımlı değil.")
        resource = ParticipationRequest.objects.create(
            project=obj,
            requested_by=request.user,
            user=person,
            target_org=person.primary_org,
            summary=text(request.data, "summary", True),
        )
        audit(
            request.user,
            "project.resource.requested",
            obj,
            {"request_id": str(resource.pk)},
        )
        for manager in User.objects.filter(
            is_active=True,
            role_grants__role__in=["UNIT_HEAD", "TEAM_MANAGER", "DIRECTOR"],
        ).distinct():
            if can_manage_org(manager, person.primary_org_id):
                enqueue_notification(
                    manager,
                    "Proje kaynak talebi",
                    "participation",
                    resource.pk,
                    f"resource:{resource.pk}:{manager.pk}",
                )
        bump(obj)
        return Response(ParticipationSerializer(resource).data, status=201)

    @action(detail=True, methods=["get", "post"])
    def tasks(self, request, pk=None):
        obj = self.get_object()
        if request.method == "GET":
            return Response(
                {
                    "results": WorkSerializer(
                        visible_work(request.user).filter(project=obj),
                        many=True,
                        context={"request": request},
                    ).data
                }
            )
        obj = self.locked()
        ensure(can_manage_project(request.user, obj))
        if obj.status not in ("PLANNED", "IN_PROGRESS", "WAITING"):
            raise ValidationError("Önce proje yayını onaylanmalıdır.")
        person = fetch(User, request.data.get("assignee_id"), is_active=True)
        ensure(
            obj.memberships.filter(user=person, active=True).exists()
            or obj.appointment.user_id == person.pk,
            "Atama için kabul edilmiş proje üyeliği gerekir.",
        )
        task = WorkItem.objects.create(
            title=text(request.data, "title", True, 240),
            description=text(request.data, "description"),
            expected_outcome=text(request.data, "expected_outcome"),
            context="PROJECT_TASK",
            project=obj,
            created_by=request.user,
            assigned_to=person,
            owner_org=person.primary_org,
            priority=priority(request.data.get("priority", "NORMAL")),
            due_at=timestamp(request.data.get("due_at")),
        )
        enqueue_notification(
            person, "Yeni proje görevi", "work", task.pk, f"assign:{task.pk}:1"
        )
        audit(request.user, "project.task.created", task)
        bump(obj)
        return Response(
            WorkSerializer(task, context={"request": request}).data, status=201
        )

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_project(request.user, obj))
        if obj.status not in ("PLANNED", "IN_PROGRESS", "WAITING"):
            raise ValidationError("Proje etkin değil.")
        if (
            obj.tasks.filter(mandatory=True)
            .exclude(status__in=["COMPLETED", "CANCELLED"])
            .exists()
        ):
            raise ValidationError("Zorunlu açık proje görevleri var.")
        obj.progress_note = text(request.data, "summary", True)
        obj.progress = 100
        obj.status = "COMPLETED"
        bump(obj)
        audit(request.user, "project.closed", obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["get", "post"])
    def authorities(self, request, pk=None):
        obj = self.get_object()
        ensure(can_manage_project(request.user, obj))
        if request.method == "GET":
            rows = [
                {
                    "id": str(g.pk),
                    "user": PersonSerializer(g.user).data,
                    "permissions": g.permissions,
                    "expires_at": g.expires_at,
                    "active": g.active,
                    "reason": g.reason,
                    "version": g.version,
                }
                for g in obj.authorities.select_related("user")
            ]
            return Response({"results": rows, "count": len(rows)})
        obj = self.locked()
        ensure(
            obj.appointment.user_id == request.user.pk
            or active_grants(request.user)
            .filter(role="UNIT_HEAD", org_node=obj.appointment.governing_org)
            .exists(),
            "Yetki devrini PM veya bağlı Unit Head yapabilir.",
        )
        person = fetch(User, request.data.get("user_id"), is_active=True)
        ensure(person.pk != request.user.pk, "Kendinize ek yetki veremezsiniz.")
        permissions = request.data.get("permissions", [])
        allowed = {"read", "approve", "manage", "tasks", "close"}
        if (
            not isinstance(permissions, list)
            or not permissions
            or not set(permissions) <= allowed
        ):
            raise ValidationError("Geçerli proje yetkileri seçin.")
        expires = timestamp(request.data.get("expires_at"), True)
        if not timezone.now() < expires <= timezone.now() + timedelta(days=365):
            raise ValidationError(
                "Yetki süresi gelecekte ve en fazla bir yıl olmalıdır."
            )
        grant = ProjectAuthorityGrant.objects.create(
            project=obj,
            user=person,
            granted_by=request.user,
            permissions=permissions,
            expires_at=expires,
            reason=text(request.data, "reason", True),
        )
        bump(obj)
        audit(
            request.user,
            "project.authority.granted",
            obj,
            {
                "grant_id": str(grant.pk),
                "user_id": str(person.pk),
                "permissions": permissions,
            },
        )
        return Response(
            {
                "id": str(grant.pk),
                "project_version": obj.version,
                "permissions": permissions,
                "expires_at": expires,
            },
            status=201,
        )

    @action(detail=True, methods=["post"], url_path="authority-revoke")
    def authority_revoke(self, request, pk=None):
        obj = self.locked()
        ensure(
            obj.appointment.user_id == request.user.pk
            or active_grants(request.user)
            .filter(role="UNIT_HEAD", org_node=obj.appointment.governing_org)
            .exists()
        )
        grant = fetch(ProjectAuthorityGrant, request.data.get("grant_id"), project=obj)
        grant.active = False
        grant.version += 1
        grant.save()
        bump(obj)
        audit(
            request.user,
            "project.authority.revoked",
            obj,
            {"grant_id": str(grant.pk), "reason": text(request.data, "reason", True)},
        )
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"], url_path="propose-change")
    def propose_change(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_project(request.user, obj))
        if not obj.published_revision or obj.status in ("COMPLETED", "CANCELLED"):
            raise ValidationError("Değişiklik için etkin yayınlı proje gerekir.")
        if obj.revisions.filter(decision="PENDING").exists():
            raise Conflict("Karar bekleyen bir değişiklik zaten var.")
        reason = text(request.data, "reason", True)
        content = {
            "title": text(request.data, "title", limit=240)
            if "title" in request.data
            else obj.title,
            "description": text(request.data, "description")
            if "description" in request.data
            else obj.description,
            "expected_outcome": text(request.data, "expected_outcome")
            if "expected_outcome" in request.data
            else obj.expected_outcome,
            "due_at": timestamp(request.data["due_at"]).isoformat()
            if request.data.get("due_at")
            else obj.due_at.isoformat()
            if obj.due_at
            else None,
            "audience_ids": [str(x) for x in obj.audience.values_list("id", flat=True)],
            "change_reason": reason,
        }
        if not content["title"]:
            raise ValidationError("Proje başlığı boş olamaz.")
        if "audience_org_ids" in request.data:
            requested = request.data["audience_org_ids"]
            if not isinstance(requested, list) or len(requested) > 100:
                raise ValidationError("Hedef kitle listesi geçersiz.")
            audience = OrgNode.objects.filter(pk__in=requested, active=True)
            if audience.count() != len(set(requested)):
                raise ValidationError("Hedef ekiplerden biri etkin değil.")
            content["audience_ids"] = [
                str(x) for x in audience.values_list("id", flat=True)
            ]
        number = obj.revisions.order_by("-number").first().number + 1
        ProjectRevision.objects.create(
            project=obj, number=number, author=request.user, content=content
        )
        obj.submitted_revision = number
        bump(obj)
        audit(
            request.user,
            "project.change.submitted",
            obj,
            {"revision": number, "reason": reason},
        )
        return Response(self.get_serializer(obj).data, status=201)

    @action(detail=True, methods=["post"])
    def transfer(self, request, pk=None):
        obj = self.locked()
        ensure(
            can_reroute_project(request.user, obj),
            "PM devrini direktör veya mevcut PM bağlı Unit Head yapabilir.",
        )
        appointment = fetch(
            PMAppointment, request.data.get("appointment_id"), active=True
        )
        if not appointment.user.is_active:
            raise ValidationError("Yeni PM etkin değil.")
        old = str(obj.appointment_id)
        reason = text(request.data, "reason", True)
        obj.appointment = appointment
        obj.authorities.filter(active=True).update(active=False)
        bump(obj)
        audit(
            request.user,
            "project.manager.transferred",
            obj,
            {
                "old_appointment_id": old,
                "new_appointment_id": str(appointment.pk),
                "reason": reason,
            },
        )
        enqueue_notification(
            appointment.user,
            "Proje yönetimi size devredildi",
            "project",
            obj.pk,
            f"project-transfer:{obj.pk}:{obj.version}",
        )
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["get"])
    def revisions(self, request, pk=None):
        obj = self.get_object()
        ensure(
            can_manage_project(request.user, obj)
            or obj.created_by_id == request.user.pk
        )
        return Response(
            {
                "results": [
                    {
                        "id": str(r.pk),
                        "number": r.number,
                        "content": r.content,
                        "author_id": str(r.author_id),
                        "decision": r.decision,
                        "decided_by_id": str(r.decided_by_id)
                        if r.decided_by_id
                        else None,
                        "decision_note": r.decision_note,
                        "created_at": r.created_at,
                    }
                    for r in obj.revisions.order_by("-number")
                ]
            }
        )


class ParticipationViewSet(DomainViewSet):
    serializer_class = ParticipationSerializer

    def get_queryset(self):
        return visible_participations(self.request.user)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_org(request.user, obj.target_org_id))
        if obj.status != "PENDING":
            raise ValidationError("Talep zaten kararlaştırıldı.")
        if request.data.get("decision") not in ("ACCEPT", "REJECT"):
            raise ValidationError("ACCEPT veya REJECT seçin.")
        obj.status = "ACCEPTED" if request.data["decision"] == "ACCEPT" else "REJECTED"
        obj.decided_by = request.user
        obj.decision_note = text(request.data, "note")
        if obj.status == "ACCEPTED":
            if not obj.user.is_active or obj.user.primary_org_id not in descendants_ids(
                obj.target_org_id
            ):
                raise ValidationError(
                    "Kişinin birim/etkinlik bilgisi değişti; yeni talep açın."
                )
            if obj.project:
                ProjectMembership.objects.update_or_create(
                    project=obj.project,
                    user=obj.user,
                    defaults={"active": True, "accepted_by": request.user},
                )
            else:
                obj.case.members.add(obj.user)
        bump(obj)
        audit(request.user, "participation.decided", obj, {"decision": obj.status})
        enqueue_notification(
            obj.requested_by,
            "Kaynak talebi değerlendirildi",
            "project" if obj.project else "case",
            obj.project_id or obj.case_id,
            f"resource-decision:{obj.pk}",
        )
        return Response(self.get_serializer(obj).data)


class WorkViewSet(DomainViewSet):
    serializer_class = WorkSerializer

    def get_queryset(self):
        qs = visible_work(self.request.user)
        if self.request.query_params.get("mine") == "true":
            qs = qs.filter(assigned_to=self.request.user)
        elif not self.request.query_params.get("all_contexts"):
            qs = qs.filter(context="UNIT_WORK")
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    def create(self, request):
        data = request.data
        unknown(
            data,
            {
                "title",
                "description",
                "expected_outcome",
                "assignee_id",
                "priority",
                "personal",
                "due_at",
                "parent_id",
                "mandatory",
                "shared_parent_summary",
                "kind",
            },
        )
        person = fetch(User, data.get("assignee_id") or request.user.pk, is_active=True)
        require_org(person)
        ensure(
            person.pk == request.user.pk
            or can_manage_org(request.user, person.primary_org_id)
        )
        personal = data.get(
            "personal", not can_manage_org(request.user, person.primary_org_id)
        )
        if not isinstance(personal, bool):
            raise ValidationError("personal bir boolean olmalıdır.")
        if personal and person.pk != request.user.pk:
            raise ValidationError("Kişisel iş yalnız kendinize açılabilir.")
        formal = not personal
        if formal:
            ensure(can_manage_org(request.user, person.primary_org_id))
        parent = None
        if data.get("parent_id"):
            parent = fetch(WorkItem, data["parent_id"])
            ensure(
                can_read_work(request.user, parent)
                and can_update_work(request.user, parent)
            )
            if parent.context != "UNIT_WORK":
                raise ValidationError(
                    "Proje/vaka alt görevini kendi bağlamında oluşturun."
                )
            if parent.status in TERMINAL:
                raise ValidationError("Kapalı işe alt iş eklenemez.")
        obj = WorkItem.objects.create(
            title=text(data, "title", True, 240),
            description=text(data, "description"),
            expected_outcome=text(data, "expected_outcome"),
            assigned_to=person,
            created_by=request.user,
            owner_org=person.primary_org,
            formal=formal,
            priority=priority(data.get("priority", "NORMAL")),
            due_at=timestamp(data.get("due_at")),
            parent=parent,
            mandatory=bool(data.get("mandatory", True)),
            shared_parent_summary=text(data, "shared_parent_summary"),
            kind=data.get("kind", "TASK"),
        )
        if obj.kind not in ("TASK", "COMMITMENT"):
            raise ValidationError("TASK veya COMMITMENT seçin.")
        if obj.kind == "COMMITMENT" and not obj.expected_outcome:
            raise ValidationError("Taahhütte beklenen çıktı zorunludur.")
        if formal:
            create_sla(work=obj)
        enqueue_notification(
            person, "Size bir iş atandı", "work", obj.pk, f"assign:{obj.pk}:1"
        )
        audit(request.user, "work.created", obj)
        return Response(self.get_serializer(obj).data, status=201)

    def partial_update(self, request, pk=None):
        obj = self.locked()
        ensure(can_update_work(request.user, obj))
        unknown(request.data, {"version", "title", "description", "expected_outcome"})
        for key in ("title", "description", "expected_outcome"):
            if key in request.data:
                setattr(
                    obj,
                    key,
                    text(
                        request.data,
                        key,
                        key == "title",
                        240 if key == "title" else 10000,
                    ),
                )
        bump(obj)
        audit(request.user, "work.updated", obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        obj = self.locked()
        assign_work(
            request.user,
            obj,
            fetch(User, request.data.get("assignee_id"), is_active=True),
        )
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def adopt(self, request, pk=None):
        obj = self.locked()
        ensure(obj.context == "UNIT_WORK" and can_manage_work(request.user, obj))
        if obj.formal or obj.status in TERMINAL:
            raise ValidationError("Yalnız etkin kişisel iş resmî takibe alınabilir.")
        obj.formal = True
        obj.priority = priority(request.data.get("priority", obj.priority))
        bump(obj)
        create_sla(work=obj)
        audit(request.user, "work.adopted", obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        obj = self.locked()
        ensure(can_update_work(request.user, obj))
        target = request.data.get("status")
        if target not in (
            "OPEN",
            "IN_PROGRESS",
            "WAITING",
            "VERIFYING",
            "COMPLETED",
            "CANCELLED",
        ):
            raise ValidationError("Geçersiz durum.")
        if target == "CANCELLED":
            ensure(
                can_manage_work(request.user, obj)
                or (not obj.formal and obj.assigned_to_id == request.user.pk)
            )
            text(request.data, "reason", True)
        if obj.status in TERMINAL and target not in ("OPEN", "IN_PROGRESS"):
            raise ValidationError("Kapalı iş önce gerekçeli yeniden açılmalıdır.")
        if obj.status in TERMINAL:
            ensure(can_manage_work(request.user, obj) or not obj.formal)
            text(request.data, "reason", True)
            if hasattr(obj, "sla"):
                obj.sla.stopped_at = None
                obj.sla.save()
                mark_breach(obj.sla)
            obj.completed_at = None
        if target == "WAITING":
            obj.blocker = text(request.data, "blocker", True)
        if target in ("VERIFYING", "COMPLETED"):
            if (
                obj.children.filter(mandatory=True)
                .exclude(status__in=TERMINAL)
                .exists()
            ):
                raise ValidationError("Zorunlu açık alt işler tamamlanmalıdır.")
            obj.result = text(request.data, "result", True)
            if obj.formal:
                target = "VERIFYING"
        obj.status = target
        if target in TERMINAL:
            obj.completed_at = timezone.now()
            stop_sla(obj)
        bump(obj)
        audit(request.user, "work.status.changed", obj, {"status": target})
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        obj = self.locked()
        ensure(
            can_manage_work(request.user, obj)
            and obj.assigned_to_id != request.user.pk,
            "Kendi tamamlanma bildiriminizi kabul edemezsiniz.",
        )
        if obj.status != "VERIFYING":
            raise ValidationError("İş doğrulama beklemiyor.")
        if obj.children.filter(mandatory=True).exclude(status__in=TERMINAL).exists():
            raise ValidationError("Zorunlu açık alt iş var.")
        obj.status = "COMPLETED"
        obj.accepted_by = request.user
        obj.completed_at = timezone.now()
        stop_sla(obj)
        bump(obj)
        audit(request.user, "work.accepted", obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["get"])
    def children(self, request, pk=None):
        obj = self.get_object()
        return Response(
            {
                "results": self.get_serializer(
                    visible_work(request.user).filter(parent=obj), many=True
                ).data
            }
        )

    @action(detail=True, methods=["post"])
    def progress(self, request, pk=None):
        obj = self.locked()
        ensure(can_update_work(request.user, obj))
        contribute(request.user, obj, request.data)
        bump(obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"], url_path="sla-adjust")
    def sla_adjust(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_work(request.user, obj))
        ensure(
            request.user.pk == obj.created_by_id
            or is_director(request.user)
            or can_manage_org(request.user, obj.created_by.primary_org_id),
            "Süre değişimini atayan yönetici veya yetkili üst yönetici yapabilir.",
        )
        ensure(
            obj.assigned_to_id != request.user.pk,
            "Kendi hedef uzatmanızı onaylayamazsınız.",
        )
        if not obj.formal or not hasattr(obj, "sla"):
            raise ValidationError("Bu işte resmî süre hedefi yok.")
        sla = SLAInstance.objects.select_for_update().get(work=obj)
        mark_breach(sla)
        due = timestamp(request.data.get("due_at"), True)
        reason = text(request.data, "reason", True)
        if due <= sla.started_at:
            raise ValidationError("Hedef başlangıçtan sonra olmalıdır.")
        old = sla.current_due_at
        sla.current_due_at = due
        sla.revision += 1
        sla.save()
        obj.due_at = due
        bump(obj)
        SLAEvent.objects.create(
            sla=sla,
            key=f"{sla.pk}:{sla.revision}:ADJUSTMENT",
            kind="ADJUSTMENT",
            threshold_at=timezone.now(),
            data={
                "old_due_at": old.isoformat(),
                "new_due_at": due.isoformat(),
                "reason": reason,
                "actor_id": str(request.user.pk),
            },
        )
        audit(
            request.user,
            "sla.adjusted",
            obj,
            {
                "reason": reason,
                "old_due_at": old.isoformat(),
                "new_due_at": due.isoformat(),
            },
        )
        obj.sla = sla
        return Response(self.get_serializer(obj).data)


class CaseViewSet(DomainViewSet):
    serializer_class = CaseSerializer

    def get_queryset(self):
        return visible_cases(self.request.user)

    def create(self, request):
        data = request.data
        unknown(
            data,
            {
                "title",
                "description",
                "kind",
                "priority",
                "coordinator_id",
                "verifier_id",
                "owner_org_id",
            },
        )
        org = fetch(OrgNode, data.get("owner_org_id") or require_org(request.user).pk)
        ensure(can_open_case(request.user, org))
        person = fetch(
            User, data.get("coordinator_id") or request.user.pk, is_active=True
        )
        ensure(can_manage_org(request.user, person.primary_org_id))
        kind = data.get("kind", "SECURITY_INCIDENT")
        if kind not in ("SECURITY_INCIDENT", "VULNERABILITY", "OPERATIONAL"):
            raise ValidationError("Geçersiz vaka türü.")
        obj = Case.objects.create(
            title=text(data, "title", True, 240),
            description=text(data, "description"),
            kind=kind,
            priority=priority(data.get("priority", "HIGH")),
            owner_org=org,
            created_by=request.user,
            coordinator=person,
        )
        obj.members.add(person)
        create_sla(case=obj)
        audit(request.user, "case.opened", obj)
        enqueue_notification(
            person, "Yeni vaka koordinasyonu", "case", obj.pk, f"case-open:{obj.pk}"
        )
        return Response(self.get_serializer(obj).data, status=201)

    @action(detail=True, methods=["get", "post"])
    def actions(self, request, pk=None):
        obj = self.get_object()
        if request.method == "GET":
            return Response(
                {
                    "results": WorkSerializer(
                        visible_work(request.user).filter(case=obj),
                        many=True,
                        context={"request": request},
                    ).data
                }
            )
        obj = self.locked()
        ensure(can_manage_case(request.user, obj))
        person = fetch(User, request.data.get("assignee_id"), is_active=True)
        ensure(
            obj.members.filter(pk=person.pk).exists()
            or person.pk == obj.coordinator_id,
            "Önce vaka katılımının kabulü gerekir.",
        )
        work = WorkItem.objects.create(
            title=text(request.data, "title", True, 240),
            description=text(request.data, "description"),
            expected_outcome=text(request.data, "expected_outcome"),
            context="CASE_ACTION",
            case=obj,
            created_by=request.user,
            assigned_to=person,
            owner_org=person.primary_org,
            priority=priority(request.data.get("priority", obj.priority)),
            due_at=timestamp(request.data.get("due_at")),
            mandatory=bool(request.data.get("mandatory", True)),
        )
        enqueue_notification(
            person, "Yeni vaka aksiyonu", "work", work.pk, f"assign:{work.pk}:1"
        )
        audit(request.user, "case.action.created", work)
        bump(obj)
        return Response(
            WorkSerializer(work, context={"request": request}).data, status=201
        )

    @action(detail=True, methods=["post"])
    def members(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_case(request.user, obj))
        person = fetch(User, request.data.get("user_id"), is_active=True)
        resource = ParticipationRequest.objects.create(
            case=obj,
            requested_by=request.user,
            user=person,
            target_org=person.primary_org,
            summary=text(request.data, "summary", True),
        )
        audit(
            request.user,
            "case.resource.requested",
            obj,
            {"request_id": str(resource.pk)},
        )
        bump(obj)
        return Response(ParticipationSerializer(resource).data, status=201)

    @action(detail=True, methods=["post"])
    def progress(self, request, pk=None):
        obj = self.locked()
        ensure(
            can_manage_case(request.user, obj)
            or obj.members.filter(pk=request.user.pk).exists()
        )
        contribute(request.user, obj, request.data)
        if obj.status in ("NEW", "ASSESSING"):
            obj.status = "IN_PROGRESS"
        bump(obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"], url_path="request-close")
    def request_close(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_case(request.user, obj))
        if obj.status in ("CLOSED", "CANCELLED", "VERIFYING"):
            raise ValidationError("Vaka kapanış isteği için uygun değil.")
        if obj.actions.filter(mandatory=True).exclude(status__in=TERMINAL).exists():
            raise ValidationError("Zorunlu açık vaka aksiyonları var.")
        obj.closure_summary = text(request.data, "summary", True)
        obj.verification_evidence = text(request.data, "evidence", True)
        obj.status = "VERIFYING"
        obj.closure_requested_by = request.user
        bump(obj)
        audit(request.user, "case.closure.requested", obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"], url_path="verify-close")
    def verify_close(self, request, pk=None):
        obj = self.locked()
        ensure(can_verify_case(request.user, obj))
        ensure(
            obj.closure_requested_by_id != request.user.pk,
            "Kendi kapanış isteğinizi doğrulayamazsınız.",
        )
        if obj.status != "VERIFYING":
            raise ValidationError("Vaka doğrulama beklemiyor.")
        if obj.actions.filter(mandatory=True).exclude(status__in=TERMINAL).exists():
            raise ValidationError("Zorunlu açık vaka aksiyonu var.")
        obj.verification_evidence = text(request.data, "evidence", True)
        obj.verifier = request.user
        obj.status = "CLOSED"
        obj.closed_at = timezone.now()
        stop_sla(obj)
        bump(obj)
        audit(request.user, "case.closed.verified", obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_case(request.user, obj))
        target = request.data.get("status")
        if target not in ("ASSESSING", "IN_PROGRESS", "CANCELLED"):
            raise ValidationError(
                "ASSESSING, IN_PROGRESS veya CANCELLED seçin; kapanış için doğrulama akışını kullanın."
            )
        if target == "CANCELLED":
            ensure(can_open_case(request.user, obj.owner_org_id))
            reason = text(request.data, "reason", True)
            stop_sla(obj)
            obj.closed_at = timezone.now()
            audit(request.user, "case.cancelled", obj, {"reason": reason})
        elif obj.status in ("CLOSED", "CANCELLED"):
            ensure(can_open_case(request.user, obj.owner_org_id))
            reason = text(request.data, "reason", True)
            obj.closed_at = None
            obj.closure_requested_by = None
            obj.verifier = None
            sla = SLAInstance.objects.select_for_update().get(case=obj)
            sla.stopped_at = None
            sla.save(update_fields=["stopped_at"])
            mark_breach(sla)
            audit(request.user, "case.reopened", obj, {"reason": reason})
        elif obj.status == "VERIFYING":
            raise ValidationError(
                "Doğrulama bekleyen vaka için kapanış kararını tamamlayın."
            )
        obj.status = target
        bump(obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"], url_path="sla-adjust")
    def sla_adjust(self, request, pk=None):
        obj = self.locked()
        ensure(can_open_case(request.user, obj.owner_org_id))
        ensure(
            request.user.pk == obj.created_by_id
            or is_director(request.user)
            or can_manage_org(request.user, obj.created_by.primary_org_id)
        )
        ensure(
            obj.coordinator_id != request.user.pk,
            "Kendi hedef uzatmanızı onaylayamazsınız.",
        )
        sla = SLAInstance.objects.select_for_update().get(case=obj)
        mark_breach(sla)
        due = timestamp(request.data.get("due_at"), True)
        reason = text(request.data, "reason", True)
        if due <= sla.started_at:
            raise ValidationError("Hedef başlangıçtan sonra olmalıdır.")
        old = sla.current_due_at
        sla.current_due_at = due
        sla.revision += 1
        sla.save()
        bump(obj)
        SLAEvent.objects.create(
            sla=sla,
            key=f"{sla.pk}:{sla.revision}:ADJUSTMENT",
            kind="ADJUSTMENT",
            threshold_at=timezone.now(),
            data={
                "old_due_at": old.isoformat(),
                "new_due_at": due.isoformat(),
                "reason": reason,
                "actor_id": str(request.user.pk),
            },
        )
        audit(
            request.user,
            "sla.adjusted",
            obj,
            {
                "reason": reason,
                "old_due_at": old.isoformat(),
                "new_due_at": due.isoformat(),
            },
        )
        obj.sla = sla
        return Response(self.get_serializer(obj).data)


class CaseNoticeViewSet(DomainViewSet):
    serializer_class = NoticeSerializer

    def get_queryset(self):
        return api_narrow(
            self.request.user,
            CaseNotice.objects.filter(
                Q(created_by=self.request.user)
                | Q(owner_org_id__in=manager_scope_ids(self.request.user))
            ),
        )

    def create(self, request):
        org = require_org(request.user)
        obj = CaseNotice.objects.create(
            title=text(request.data, "title", True, 240),
            description=text(request.data, "description", True),
            created_by=request.user,
            owner_org=org,
        )
        audit(request.user, "case.notice.created", obj)
        return Response(self.get_serializer(obj).data, status=201)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        notice = self.locked()
        ensure(can_open_case(request.user, notice.owner_org_id))
        if notice.status != "PENDING":
            raise ValidationError("İhbar zaten kararlaştırıldı.")
        coordinator = fetch(
            User, request.data.get("coordinator_id") or request.user.pk, is_active=True
        )
        ensure(can_manage_org(request.user, coordinator.primary_org_id))
        obj = Case.objects.create(
            title=notice.title,
            description=notice.description,
            kind=request.data.get("kind", "SECURITY_INCIDENT"),
            priority=priority(request.data.get("priority", "HIGH")),
            owner_org=notice.owner_org,
            created_by=request.user,
            coordinator=coordinator,
        )
        if obj.kind not in ("SECURITY_INCIDENT", "VULNERABILITY", "OPERATIONAL"):
            raise ValidationError("Geçersiz vaka türü.")
        obj.members.add(coordinator)
        create_sla(case=obj)
        notice.case = obj
        notice.status = "CONVERTED"
        bump(notice)
        audit(request.user, "case.notice.converted", notice, {"case_id": str(obj.pk)})
        audit(request.user, "case.opened", obj, {"notice_id": str(notice.pk)})
        enqueue_notification(
            coordinator,
            "Yeni vaka koordinasyonu",
            "case",
            obj.pk,
            f"case-open:{obj.pk}",
        )
        return Response(
            CaseSerializer(obj, context={"request": request}).data, status=201
        )

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        notice = self.locked()
        ensure(can_open_case(request.user, notice.owner_org_id))
        if notice.status != "PENDING":
            raise ValidationError("İhbar zaten kararlaştırıldı.")
        notice.status = "DISMISSED"
        bump(notice)
        audit(
            request.user,
            "case.notice.dismissed",
            notice,
            {"reason": text(request.data, "reason", True)},
        )
        return Response(self.get_serializer(notice).data)


class AnnouncementViewSet(DomainViewSet):
    serializer_class = AnnouncementSerializer

    def get_queryset(self):
        return visible_announcements(self.request.user)

    def create(self, request):
        org = require_org(request.user)
        obj = Announcement.objects.create(
            title=text(request.data, "title", True, 240),
            body=text(request.data, "body", True),
            owner_org=org,
            created_by=request.user,
            all_cs=bool(request.data.get("all_cs", False)),
            starts_at=timestamp(request.data.get("starts_at")) or timezone.now(),
            ends_at=timestamp(request.data.get("ends_at")),
            pinned=bool(request.data.get("pinned", False)),
        )
        if obj.ends_at and obj.ends_at <= obj.starts_at:
            raise ValidationError("Bitiş başlangıçtan sonra olmalıdır.")
        audience = request.data.get("audience_org_ids") or [str(org.pk)]
        obj.audience.set(OrgNode.objects.filter(pk__in=audience, active=True))
        audit(request.user, "announcement.proposed", obj)
        return Response(self.get_serializer(obj).data, status=201)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        obj = self.locked()
        ensure(
            obj.owner_org_id
            in manager_scope_ids(request.user, ("DIRECTOR", "UNIT_HEAD"))
        )
        if obj.status == "PUBLISHED":
            raise ValidationError("Anons zaten yayında.")
        obj.status = "PUBLISHED"
        bump(obj)
        audit(
            request.user,
            "announcement.published",
            obj,
            {
                "all_cs": obj.all_cs,
                "audience_ids": [
                    str(x) for x in obj.audience.values_list("id", flat=True)
                ],
            },
        )
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_org(request.user, obj.owner_org_id))
        obj.status = "WITHDRAWN"
        bump(obj)
        audit(request.user, "announcement.withdrawn", obj)
        return Response(self.get_serializer(obj).data)


class CommunityViewSet(DomainViewSet):
    serializer_class = CardSerializer

    def get_queryset(self):
        return api_narrow(self.request.user, visible_cards(self.request.user))

    def create(self, request):
        org = require_org(request.user)
        source = None
        stype = request.data.get("source_type", "")
        sid = request.data.get("source_id", "")
        if sid:
            source = report_source(request.user, stype, sid)
            if not source:
                raise NotFound("Paylaşım kaynağı bulunamadı.")
        kind = request.data.get("kind", "SUCCESS")
        if kind not in ("SUCCESS", "HELP", "OFFER", "LESSON", "KNOWLEDGE"):
            raise ValidationError("Geçersiz paylaşım türü.")
        obj = CommunityCard.objects.create(
            title=text(request.data, "title", True, 240),
            body=text(request.data, "body", True),
            kind=kind,
            created_by=request.user,
            owner_org=org,
            source_type=stype if source else "",
            source_id=str(source.pk) if source else "",
            source_version=source.version if source else None,
            all_cs=bool(request.data.get("all_cs", False)),
        )
        audience = request.data.get("audience_org_ids") or [str(org.pk)]
        obj.audience.set(OrgNode.objects.filter(pk__in=audience, active=True))
        audit(request.user, "community.card.created", obj)
        return Response(self.get_serializer(obj).data, status=201)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        obj = self.locked()
        ensure(obj.created_by_id == request.user.pk)
        if obj.status != "DRAFT":
            raise ValidationError("Yalnız taslak gönderilebilir.")
        obj.status = "SUBMITTED"
        bump(obj)
        audit(request.user, "community.card.submitted", obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_org(request.user, obj.owner_org_id))
        if obj.status not in ("DRAFT", "SUBMITTED", "CONTENT_APPROVED"):
            raise ValidationError("Kart yayın kararı beklemiyor.")
        if obj.source_id:
            if obj.source_type == "project" and obj.content_approved_by_id:
                source = Project.objects.filter(pk=obj.source_id).first()
            else:
                source = report_source(request.user, obj.source_type, obj.source_id)
            if not source or source.version != obj.source_version:
                raise Conflict(
                    "Kaynak değişti veya erişim kaldırıldı. Kart yeniden hazırlanmalı."
                )
            if obj.source_type == "project":
                if not obj.content_approved_by_id:
                    ensure(
                        can_manage_project(request.user, source, "approve"),
                        "Önce PM kapsamında paylaşım metni onaylanmalıdır.",
                    )
                    obj.content_approved_by = request.user
            if obj.source_type == "case":
                ensure(
                    can_open_case(request.user, source.owner_org_id),
                    "Vaka dersini Unit Head onaylamalıdır.",
                )
        if obj.all_cs or any(
            o not in manager_scope_ids(request.user)
            for o in obj.audience.values_list("id", flat=True)
        ):
            ensure(
                has_role(request.user, "UNIT_HEAD") or is_director(request.user),
                "Geniş hedef kitle için Unit Head yayın kararı gerekir.",
            )
        obj.status = "PUBLISHED"
        obj.published_by = request.user
        bump(obj)
        audit(request.user, "community.card.published", obj, {"all_cs": obj.all_cs})
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"], url_path="approve-content")
    def approve_content(self, request, pk=None):
        obj = self.locked()
        if obj.status not in ("SUBMITTED", "DRAFT"):
            raise ValidationError("Kart metin onayı beklemiyor.")
        if obj.source_type == "project":
            source = report_source(request.user, "project", obj.source_id)
            ensure(
                source is not None
                and can_manage_project(request.user, source, "approve")
            )
        elif obj.source_type == "case":
            source = report_source(request.user, "case", obj.source_id)
            ensure(
                source is not None and can_open_case(request.user, source.owner_org_id)
            )
        else:
            ensure(can_manage_org(request.user, obj.owner_org_id))
            source = None
        if source and source.version != obj.source_version:
            raise Conflict("Kaynak sürümü değişti; paylaşım yeniden hazırlanmalıdır.")
        obj.content_approved_by = request.user
        obj.status = "CONTENT_APPROVED"
        bump(obj)
        audit(request.user, "community.card.content.approved", obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_org(request.user, obj.owner_org_id))
        obj.status = "WITHDRAWN"
        bump(obj)
        audit(request.user, "community.card.withdrawn", obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def interest(self, request, pk=None):
        obj = self.get_object()
        if obj.status != "PUBLISHED":
            raise ValidationError("Yalnız yayınlı karta ilgi gösterilebilir.")
        if request.data.get("interested", True):
            obj.interests.add(request.user)
            enqueue_notification(
                obj.created_by,
                "Paylaşımınıza ilgi var",
                "community",
                obj.pk,
                f"card-interest:{obj.pk}:{request.user.pk}",
            )
        else:
            obj.interests.remove(request.user)
        audit(request.user, "community.card.interest", obj)
        return Response(self.get_serializer(obj).data)


class EventViewSet(DomainViewSet):
    serializer_class = EventSerializer

    @action(detail=True, methods=["get"])
    def participants(self, request, pk=None):
        event = self.get_object()
        ensure(can_manage_org(request.user, event.owner_org_id))
        responses = dict(event.responses.values_list("user_id", "answer"))
        attendance = dict(event.attendance.values_list("user_id", "present"))
        rows = [
            {
                "id": str(person.pk),
                "display_name": person.display_name or person.username,
                "rsvp": responses.get(person.pk),
                "present": attendance.get(person.pk),
            }
            for person in event.invitees.filter(is_active=True).order_by("display_name")
        ]
        return Response({"results": rows, "count": len(rows), "version": event.version})

    def get_queryset(self):
        return api_narrow(
            self.request.user,
            Event.objects.filter(
                Q(invitees=self.request.user)
                | Q(owner_org_id__in=manager_scope_ids(self.request.user))
            )
            .distinct()
            .select_related("owner_org"),
        )

    def create(self, request):
        org = fetch(
            OrgNode, request.data.get("owner_org_id") or require_org(request.user).pk
        )
        ensure(can_manage_org(request.user, org.pk))
        obj = Event.objects.create(
            title=text(request.data, "title", True, 240),
            description=text(request.data, "description"),
            location=text(request.data, "location", limit=200),
            starts_at=timestamp(request.data.get("starts_at")),
            ends_at=timestamp(request.data.get("ends_at")),
            owner_org=org,
            created_by=request.user,
        )
        if obj.ends_at and obj.starts_at and obj.ends_at <= obj.starts_at:
            raise ValidationError("Etkinlik bitişi başlangıçtan sonra olmalıdır.")
        people = User.objects.filter(
            is_active=True, primary_org_id__in=descendants_ids(org.pk)
        )
        if request.data.get("invitee_ids"):
            people = people.filter(pk__in=request.data["invitee_ids"])
            if people.count() != len(set(request.data["invitee_ids"])):
                raise PermissionDenied(
                    "Davetli listesi yönetim kapsamınızda olmalıdır."
                )
        obj.invitees.set(people)
        audit(request.user, "event.created", obj)
        return Response(self.get_serializer(obj).data, status=201)

    @action(detail=True, methods=["post"])
    def rsvp(self, request, pk=None):
        obj = self.get_object()
        ensure(
            obj.invitees.filter(pk=request.user.pk).exists(),
            "Etkinliğe davetli değilsiniz.",
        )
        answer = request.data.get("answer") or request.data.get("response")
        if answer not in ("YES", "NO", "MAYBE"):
            raise ValidationError("YES, NO veya MAYBE seçin.")
        EventRSVP.objects.update_or_create(
            event=obj, user=request.user, defaults={"answer": answer}
        )
        audit(request.user, "event.rsvp", obj, {"answer": answer})
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def attendance(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_org(request.user, obj.owner_org_id))
        person = fetch(User, request.data.get("user_id"))
        ensure(
            obj.invitees.filter(pk=person.pk).exists(),
            "Kişi etkinliğin davetlisi değil.",
        )
        if not isinstance(request.data.get("present"), bool):
            raise ValidationError("present boolean olmalıdır.")
        EventAttendance.objects.update_or_create(
            event=obj,
            user=person,
            defaults={"present": request.data["present"], "recorded_by": request.user},
        )
        audit(request.user, "event.attendance", obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def poll(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_org(request.user, obj.owner_org_id))
        options = request.data.get("options", [])
        if not isinstance(options, list) or not 2 <= len(options) <= 20:
            raise ValidationError("2–20 seçenek girin.")
        normalized = [
            {
                "id": str(uuid.uuid4()),
                "label": str(o.get("label", "") if isinstance(o, dict) else o)[:180],
            }
            for o in options
        ]
        if len(set(o["label"] for o in normalized)) != len(normalized) or any(
            not o["label"].strip() for o in normalized
        ):
            raise ValidationError("Seçenekler benzersiz ve dolu olmalıdır.")
        try:
            maximum = int(request.data.get("max_choices", 1))
        except (ValueError, TypeError):
            raise ValidationError("Seçim sınırı bir sayı olmalıdır.")
        if not 1 <= maximum <= len(options):
            raise ValidationError("Seçim sınırı geçersiz.")
        closes = timestamp(request.data.get("closes_at"), True)
        if closes <= timezone.now():
            raise ValidationError("Anket kapanışı gelecekte olmalıdır.")
        poll = Poll.objects.create(
            event=obj,
            question=text(request.data, "question", True, 300),
            options=normalized,
            max_choices=maximum,
            closes_at=closes,
            elector_ids=[str(x) for x in obj.invitees.values_list("id", flat=True)],
            elector_version=obj.invitee_version,
        )
        bump(obj)
        audit(request.user, "event.poll.created", poll)
        return Response(
            PollSerializer(poll, context={"request": request}).data, status=201
        )

    @action(detail=True, methods=["post"], url_path="poll-response")
    def poll_response(self, request, pk=None):
        event = self.get_object()
        poll = fetch(Poll, request.data.get("poll_id"), event=event)
        poll = Poll.objects.select_for_update().get(pk=poll.pk)
        ensure(
            str(request.user.pk) in poll.elector_ids,
            "Anketin seçmen listesinde değilsiniz.",
        )
        if timezone.now() >= poll.closes_at:
            raise ValidationError("Anket kapandı.")
        choices = request.data.get("choices", [])
        allowed = {str(o["id"]) for o in poll.options}
        if (
            not isinstance(choices, list)
            or len(set(map(str, choices))) != len(choices)
            or not 1 <= len(choices) <= poll.max_choices
            or not set(map(str, choices)) <= allowed
        ):
            raise ValidationError("Geçerli ve benzersiz anket seçenekleri seçin.")
        PollResponse.objects.update_or_create(
            poll=poll,
            user=request.user,
            defaults={"choices": [str(c) for c in choices]},
        )
        audit(request.user, "event.poll.responded", poll)
        return Response(PollSerializer(poll, context={"request": request}).data)


class CredentialViewSet(DomainViewSet):
    serializer_class = CredentialSerializer

    def get_queryset(self):
        return visible_credentials(self.request.user)

    def create(self, request):
        person = fetch(User, request.data.get("user_id") or request.user.pk)
        ensure(
            person.pk == request.user.pk
            or can_manage_org(request.user, person.primary_org_id)
        )
        no_expiry = bool(request.data.get("no_expiry", False))
        expiry = request.data.get("expires_on") or request.data.get("expires_at")
        issued = request.data.get("issued_on") or request.data.get("issued_at")
        expires = date_value(expiry)
        issued_on = date_value(issued)
        if expiry and not expires or issued and not issued_on:
            raise ValidationError("Geçerli tarih girin.")
        if no_expiry and expires or not no_expiry and not expires:
            raise ValidationError(
                "Süreli sertifikada bitiş, süresizde no_expiry gereklidir."
            )
        if issued_on and expires and expires < issued_on:
            raise ValidationError("Bitiş edinme tarihinden önce olamaz.")
        important = bool(request.data.get("important", False))
        if important:
            ensure(
                can_manage_org(request.user, person.primary_org_id),
                "Önemli sertifika işaretini yönetici seçer.",
            )
        obj = Credential.objects.create(
            user=person,
            name=text(request.data, "name", True, 200),
            issuer=text(request.data, "issuer", True, 180),
            issued_on=issued_on,
            expires_on=expires,
            no_expiry=no_expiry,
            important=important,
            reference=text(request.data, "reference", limit=300),
        )
        audit(request.user, "credential.created", obj)
        return Response(self.get_serializer(obj).data, status=201)

    def partial_update(self, request, pk=None):
        obj = self.locked()
        ensure(can_manage_org(request.user, obj.user.primary_org_id))
        unknown(
            request.data, {"version", "important", "verification_status", "alert_days"}
        )
        if "important" in request.data:
            obj.important = bool(request.data["important"])
        if "verification_status" in request.data:
            if request.data["verification_status"] not in (
                "DECLARED",
                "VERIFIED",
                "REJECTED",
            ):
                raise ValidationError("Geçersiz doğrulama durumu.")
            obj.verification_status = request.data["verification_status"]
        if "alert_days" in request.data:
            try:
                days = int(request.data["alert_days"])
            except (ValueError, TypeError):
                raise ValidationError("Uyarı günü bir sayı olmalıdır.")
            if not 1 <= days <= 365:
                raise ValidationError("Uyarı 1–365 gün arasında olmalıdır.")
            obj.alert_days = days
        bump(obj)
        audit(request.user, "credential.updated", obj)
        return Response(self.get_serializer(obj).data)


class ReportSelectionViewSet(DomainViewSet):
    serializer_class = ReportSelectionSerializer

    def get_queryset(self):
        qs = ReportSelection.objects.filter(user=self.request.user)
        return qs.filter(
            pk__in=[
                selection.pk
                for selection in qs
                if report_source(
                    self.request.user, selection.source_type, selection.source_id
                )
            ]
        )

    def list(self, request):
        qs = self.get_queryset()
        return Response(
            {
                "results": [
                    {
                        "id": str(s.pk),
                        "source_type": s.source_type,
                        "source_id": str(s.source_id),
                        "week_start": s.week_start,
                    }
                    for s in qs
                ],
                "count": qs.count(),
            }
        )

    def create(self, request):
        kind = request.data.get("source_type")
        sid = request.data.get("source_id")
        obj = report_source(request.user, kind, sid)
        if obj is None:
            raise NotFound("Rapor kaynağı bulunamadı.")
        week = date_value(
            request.data.get("week_start", "")
        ) or timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        if request.data.get("selected", True):
            ReportSelection.objects.get_or_create(
                user=request.user, source_type=kind, source_id=obj.pk, week_start=week
            )
        else:
            ReportSelection.objects.filter(
                user=request.user, source_type=kind, source_id=obj.pk, week_start=week
            ).delete()
        audit(
            request.user,
            "report.selection.changed",
            obj,
            {"selected": bool(request.data.get("selected", True))},
        )
        return Response({"selected": bool(request.data.get("selected", True))})


class ReportViewSet(DomainViewSet):
    serializer_class = ReportSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Report.objects.filter(
            Q(created_by=user)
            | Q(
                status="APPROVED",
                created_by__primary_org_id__in=manager_scope_ids(user),
            )
        ).select_related("created_by", "job")
        return qs.filter(
            pk__in=[
                r.pk
                for r in qs
                if (api_scope_ids(user) is None or bool(r.sources))
                and all(
                    source_visibility_valid(self.request.user, source)
                    for source in r.sources
                )
            ]
        )

    def retrieve(self, request, pk=None):
        obj = self.get_object()
        for source in obj.sources:
            if not source_visibility_valid(request.user, source):
                raise PermissionDenied(
                    "Rapordaki kaynağa erişiminiz kaldırıldı. Yeni rapor hazırlayın."
                )
        return Response(self.get_serializer(obj).data)

    def create(self, request):
        ensure(
            bool(manager_scope_ids(request.user))
            or request.user.pm_appointments.filter(active=True).exists(),
            "Yönetim raporu için yönetici veya PM yetkisi gerekir.",
        )
        start = date_value(request.data.get("period_start", ""))
        end = date_value(request.data.get("period_end", ""))
        if not start or not end or end < start or (end - start).days > 366:
            raise ValidationError("Geçerli, en fazla bir yıllık dönem girin.")
        sources = {}
        for selection in ReportSelection.objects.filter(
            user__is_active=True,
            week_start__gte=start - timedelta(days=6),
            week_start__lte=end,
        ):
            obj = report_source(
                request.user, selection.source_type, selection.source_id
            )
            if obj:
                snapshot = snapshot_source(obj, selection.source_type, request.user)
                snapshot["selection_reason"] = (
                    "SELECTED"
                    if selection.user_id == request.user.pk
                    else "TEAM_SELECTED"
                )
                sources[(selection.source_type, str(obj.pk))] = snapshot
        for kind, qs in [
            ("work", visible_work(request.user)),
            ("project", visible_projects(request.user)),
            ("case", visible_cases(request.user)),
        ]:
            for obj in qs:
                if (
                    obj.priority == "CRITICAL"
                    and obj.status
                    not in ("COMPLETED", "CANCELLED", "CLOSED", "DRAFT", "REJECTED")
                    or hasattr(obj, "sla")
                    and obj.sla.stopped_at is None
                    and obj.sla.current_due_at < timezone.now()
                    or obj.status in ("SUBMITTED", "VERIFYING")
                ):
                    sources[(kind, str(obj.pk))] = snapshot_source(
                        obj, kind, request.user
                    )
        obj = Report.objects.create(
            title=text(request.data, "title", False, 240) or "Haftalık Yönetim Özeti",
            created_by=request.user,
            period_start=start,
            period_end=end,
            sources=list(sources.values()),
        )
        audit(request.user, "report.created", obj, {"source_count": len(sources)})
        return Response(self.get_serializer(obj).data, status=201)

    @action(detail=True, methods=["post"])
    def generate(self, request, pk=None):
        obj = self.locked()
        ensure(
            obj.created_by_id == request.user.pk,
            "Paylaşılan rapor salt okunurdur; kendi raporunuzu oluşturun.",
        )
        if obj.status in ("APPROVED", "GENERATING"):
            raise ValidationError("Rapor onaylı veya üretimi devam ediyor.")
        if len(obj.sources) > 100:
            raise ValidationError("Bir raporda en fazla 100 kaynak özetlenebilir.")
        for source in obj.sources:
            if report_source(request.user, source["type"], source["id"]) is None:
                raise PermissionDenied("Kaynak erişimi kaldırıldı.")
        from administration.profiles import selected_ai_snapshot

        ai_snapshot = selected_ai_snapshot()
        job = BackgroundJob.objects.create(
            kind="REPORT",
            actor=request.user,
            payload={
                "report_id": str(obj.pk),
                "access_fingerprint": access_fingerprint(request.user),
                "ai_profile_id": ai_snapshot["profile_id"],
                "ai_configuration_version": ai_snapshot["configuration_version"],
                "ai_settings_version": ai_snapshot["settings_version"],
            },
        )
        obj.job = job
        obj.status = "GENERATING"
        bump(obj)
        audit(request.user, "report.queued", obj)
        return Response(self.get_serializer(obj).data, status=202)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        obj = self.locked()
        ensure(
            obj.created_by_id == request.user.pk,
            "Yalnız rapor sahibi gördüğü sürümü onaylayabilir.",
        )
        if obj.status != "READY":
            raise ValidationError("Rapor onaya hazır değil.")
        if (
            request.data.get("content_hash") != obj.content_hash
            or report_hash(obj) != obj.content_hash
        ):
            raise Conflict("İncelenen rapor sürümü değişti.")
        for source in obj.sources:
            current = report_source(request.user, source["type"], source["id"])
            if current is None:
                raise PermissionDenied("Kaynağa erişim kaldırıldı.")
            if current.version != source["version"]:
                raise Conflict("Rapor kaynağı değişti. Yeni rapor oluşturun.")
        obj.status = "APPROVED"
        obj.approved_by = request.user
        bump(obj)
        audit(request.user, "report.approved", obj)
        return Response(self.get_serializer(obj).data)


class NotificationViewSet(DomainViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user).order_by(
            "-created_at"
        )
        ids = []
        for n in qs:
            if n.resource_type in ("work", "project", "case"):
                if report_source(self.request.user, n.resource_type, n.resource_id):
                    ids.append(n.pk)
            elif n.resource_type == "community":
                if visible_cards(self.request.user).filter(pk=n.resource_id).exists():
                    ids.append(n.pk)
            elif n.resource_type == "credential":
                if (
                    visible_credentials(self.request.user)
                    .filter(pk=n.resource_id)
                    .exists()
                ):
                    ids.append(n.pk)
            elif n.resource_type == "participation":
                if (
                    visible_participations(self.request.user)
                    .filter(
                        pk=n.resource_id,
                        target_org_id__in=manager_scope_ids(self.request.user),
                    )
                    .exists()
                ):
                    ids.append(n.pk)
            elif n.resource_type == "announcement":
                if (
                    visible_announcements(self.request.user)
                    .filter(pk=n.resource_id)
                    .exists()
                ):
                    ids.append(n.pk)
            elif n.resource_type == "event":
                if (
                    api_narrow(
                        self.request.user,
                        Event.objects.filter(
                            Q(invitees=self.request.user)
                            | Q(owner_org_id__in=manager_scope_ids(self.request.user))
                        ),
                    )
                    .filter(pk=n.resource_id)
                    .exists()
                ):
                    ids.append(n.pk)
            elif api_scope_ids(self.request.user) is None:
                ids.append(n.pk)
        qs = qs.filter(pk__in=ids)
        status = self.request.query_params.get("status", "all")
        if status == "unread":
            return qs.filter(read_at__isnull=True)
        if status == "read":
            return qs.filter(read_at__isnull=False)
        if status != "all":
            raise ValidationError("Bildirim durumu all, unread veya read olmalıdır.")
        return qs

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        obj = self.get_object()
        read_state = request.data.get("read", True)
        if not isinstance(read_state, bool):
            raise ValidationError("read alanı boolean olmalıdır.")
        obj.read_at = timezone.now() if read_state else None
        obj.save(update_fields=["read_at"])
        audit(
            request.user,
            "notification.read" if read_state else "notification.unread",
            obj,
        )
        return Response(self.get_serializer(obj).data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        visible = self.get_queryset().filter(read_at__isnull=True)
        updated = visible.update(read_at=timezone.now())
        audit(request.user, "notification.all_read", request.user, {"updated": updated})
        return Response({"updated": updated})


@api_view(["GET"])
def dashboard_view(request):
    user = request.user
    work = visible_work(user)
    projects = visible_projects(user)
    cases = visible_cases(user)
    now = timezone.now()
    active_work = work.exclude(status__in=TERMINAL)
    active_cases = cases.exclude(status__in=["CLOSED", "CANCELLED"])
    active_projects = projects.exclude(
        status__in=["DRAFT", "REJECTED", "COMPLETED", "CANCELLED"]
    )
    critical = (
        active_work.filter(priority="CRITICAL").count()
        + active_cases.filter(priority="CRITICAL").count()
        + active_projects.filter(priority="CRITICAL").count()
    )
    overdue = (
        active_work.filter(due_at__lt=now).count()
        + active_cases.filter(
            sla__current_due_at__lt=now, sla__stopped_at__isnull=True
        ).count()
    )
    decisions = (
        sum(
            1
            for p in projects.filter(status="SUBMITTED")
            if can_approve_project(user, p)
        )
        + work.filter(status="VERIFYING").exclude(assigned_to=user).count()
        + visible_participations(user)
        .filter(status="PENDING", target_org_id__in=manager_scope_ids(user))
        .count()
    )
    today = timezone.localdate()
    certs = [
        credential
        for credential in visible_credentials(user).filter(
            important=True, no_expiry=False, expires_on__isnull=False
        )
        if credential.expires_on <= today + timedelta(days=credential.alert_days)
    ]
    agenda = []
    for kind, qs in [
        ("work", active_work),
        ("case", active_cases),
        ("project", active_projects),
    ]:
        for obj in qs:
            due = getattr(obj, "due_at", None)
            if not due and hasattr(obj, "sla"):
                due = obj.sla.current_due_at
            reason = (
                "Karar bekliyor"
                if obj.status in ("SUBMITTED", "VERIFYING")
                else "Geciken hedef"
                if due and due < now
                else "Kritik gündem"
                if obj.priority == "CRITICAL"
                else "Yaklaşan hedef"
            )
            score = (
                0 if obj.priority == "CRITICAL" else 1,
                0 if due and due < now else 1,
                due or now + timedelta(days=1000),
            )
            owner = (
                obj.assigned_to
                if kind == "work"
                else obj.coordinator
                if kind == "case"
                else obj.appointment.user
            )
            agenda.append(
                {
                    "id": str(obj.pk),
                    "title": obj.title,
                    "resource_type": kind,
                    "status": obj.status,
                    "priority": obj.priority,
                    "due_at": due,
                    "owner_name": owner.display_name or owner.username,
                    "reason": reason,
                    "_score": score,
                }
            )
    agenda.sort(key=lambda a: a["_score"])
    for item in agenda:
        item.pop("_score")
    units = []
    for org in OrgNode.objects.filter(kind="UNIT", active=True):
        client = getattr(user, "_api_client", None)
        if (
            client
            and client.org_node_id
            and org.pk not in descendants_ids(client.org_node_id)
        ):
            continue
        ids = descendants_ids(org.pk)
        if (
            not is_director(user)
            and not (ids & manager_scope_ids(user))
            and user.primary_org_id not in ids
        ):
            continue
        units.append(
            {
                "id": str(org.pk),
                "name": org.name,
                "code": org.code,
                "open_work": active_work.filter(owner_org_id__in=ids).count(),
                "critical": active_work.filter(
                    owner_org_id__in=ids, priority="CRITICAL"
                ).count(),
                "overdue": active_work.filter(
                    owner_org_id__in=ids, due_at__lt=now
                ).count(),
                "projects": active_projects.filter(
                    appointment__governing_org_id__in=ids
                ).count(),
                "project_contributions": active_projects.filter(
                    memberships__user__primary_org_id__in=ids, memberships__active=True
                )
                .distinct()
                .count(),
                "open_cases": active_cases.filter(owner_org_id__in=ids).count(),
                "manager_name": next(
                    (
                        g.user.display_name or g.user.username
                        for g in RoleGrant.objects.filter(
                            org_node=org,
                            role="UNIT_HEAD",
                            active=True,
                            user__is_active=True,
                        ).select_related("user")
                        if not g.expires_at or g.expires_at > now
                    ),
                    "",
                ),
            }
        )
    announcements = [
        a
        for a in visible_announcements(user).filter(
            status="PUBLISHED", starts_at__lte=now
        )
        if (not a.ends_at or a.ends_at > now) and audience_visible(user, a)
    ]
    cards = visible_cards(user).filter(status="PUBLISHED").order_by("-created_at")[:5]
    return Response(
        {
            "kpis": {
                "critical": critical,
                "overdue": overdue,
                "decisions": decisions,
                "credentials": len(certs),
            },
            "agenda": agenda[:5],
            "unit_summaries": units,
            "announcements": AnnouncementSerializer(announcements, many=True).data,
            "community": CardSerializer(
                cards, many=True, context={"request": request}
            ).data,
            "recent_activity": activity_data(user)[:8],
            "updated_at": now,
        }
    )


def activity_data(user):
    result = []
    lookup = {"Project": "project", "WorkItem": "work", "Case": "case"}
    for event in AuditEvent.objects.select_related("actor").all()[:500]:
        if event.object_type in lookup:
            source = report_source(user, lookup[event.object_type], event.object_id)
            if source and (
                event.object_type != "Project" or can_read_project_detail(user, source)
            ):
                result.append(AuditSerializer(event).data)
        elif event.actor_id == user.pk and (
            api_scope_ids(user) is None or api_activity_visible(user, event)
        ):
            result.append(AuditSerializer(event).data)
    return result


def api_activity_visible(user, event):
    sources = {
        "CommunityCard": lambda: visible_cards(user),
        "Credential": lambda: visible_credentials(user),
        "ParticipationRequest": lambda: visible_participations(user),
        "Announcement": lambda: visible_announcements(user),
        "Event": lambda: api_narrow(
            user,
            Event.objects.filter(
                Q(invitees=user) | Q(owner_org_id__in=manager_scope_ids(user))
            ),
        ),
        "OrgNode": lambda: OrgNode.objects.filter(pk__in=api_scope_ids(user) or []),
        "User": lambda: api_narrow(
            user, User.objects.filter(is_active=True), "primary_org_id"
        ),
        "PMAppointment": lambda: api_narrow(
            user, PMAppointment.objects.filter(active=True), "governing_org_id"
        ),
    }
    source = sources.get(event.object_type)
    if source is None:
        return False
    try:
        return source().filter(pk=event.object_id).exists()
    except (DjangoValidationError, ValueError, TypeError):
        return False


@api_view(["GET"])
def activity_view(request):
    result = activity_data(request.user)
    return Response({"results": result[:100], "count": len(result)})


@api_view(["GET"])
def health_view(request):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return Response({"status": "ok", "application": "Atlas", "database": "connected"})


class ApiClientViewSet(DomainViewSet):
    serializer_class = ApiClientSerializer

    def get_queryset(self):
        require_admin(self.request.user)
        return ApiClient.objects.filter(user=self.request.user)

    def list(self, request):
        require_admin(request.user)
        return Response(
            {
                "results": [
                    {
                        "id": str(c.pk),
                        "name": c.name,
                        "scopes": c.scopes,
                        "org_node_id": str(c.org_node_id) if c.org_node_id else None,
                        "active": c.active,
                        "version": c.version,
                    }
                    for c in self.get_queryset()
                ]
            }
        )

    def create(self, request):
        require_admin(request.user)
        scopes = request.data.get("scopes", [])
        allowed = {
            "dashboard:read",
            "organization:read",
            "people:read",
            "projects:read",
            "work:read",
            "cases:read",
            "credentials:read",
            "community:read",
            "events:read",
        }
        if not isinstance(scopes, list) or not scopes or not set(scopes) <= allowed:
            raise ValidationError("Geçerli salt okunur kapsam seçin.")
        # A technical admin can create a client only for their own separately granted business visibility.
        client = ApiClient.objects.create(
            name=text(request.data, "name", True, 180),
            user=request.user,
            scopes=scopes,
            org_node=fetch(OrgNode, request.data["org_node_id"])
            if request.data.get("org_node_id")
            else None,
        )
        token = issue_token(client)
        audit(request.user, "api.client.created", client, {"scopes": scopes})
        return Response(
            {
                "id": str(client.pk),
                "name": client.name,
                "token": token,
                "expires_in": 900,
                "scopes": scopes,
            },
            status=201,
        )

    @action(detail=True, methods=["post"])
    def token(self, request, pk=None):
        require_admin(request.user)
        client = self.get_object()
        if not client.active:
            raise ValidationError("API istemcisi iptal edilmiş.")
        audit(request.user, "api.token.issued", client)
        return Response({"token": issue_token(client), "expires_in": 900})

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        require_admin(request.user)
        client = self.get_object()
        client.active = False
        client.token_version += 1
        bump(client)
        audit(request.user, "api.client.revoked", client)
        return Response({"active": False})


def issue_token(client):
    import jwt
    from django.conf import settings

    now = timezone.now()
    return jwt.encode(
        {
            "sub": str(client.pk),
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "jti": str(uuid.uuid4()),
            "ver": client.token_version,
            "scopes": client.scopes,
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )


class SLAPolicyViewSet(DomainViewSet):
    serializer_class = SLAPolicySerializer

    def get_queryset(self):
        require_admin(self.request.user)
        return SLAPolicy.objects.filter(active=True).order_by("priority", "context")

    def serialize(self, obj):
        return {
            "id": str(obj.pk),
            "priority": obj.priority,
            "context": obj.context,
            "amount": obj.amount,
            "unit": obj.unit,
            "warning_percent": obj.warning_percent,
            "version": obj.version,
            "active": obj.active,
            "created_at": obj.created_at,
        }

    def list(self, request):
        require_admin(request.user)
        rows = [self.serialize(p) for p in self.get_queryset()]
        return Response({"results": rows, "count": len(rows)})

    def partial_update(self, request, pk=None):
        require_admin(request.user)
        obj = self.locked()
        unknown(
            request.data, {"version", "amount", "unit", "warning_percent", "reason"}
        )
        amount = request.data.get("amount", obj.amount)
        warn = request.data.get("warning_percent", obj.warning_percent)
        unit = request.data.get("unit", obj.unit)
        if (
            isinstance(amount, bool)
            or not isinstance(amount, int)
            or not 1 <= amount <= 3650
        ):
            raise ValidationError("Süre 1–3650 arasında tam sayı olmalıdır.")
        if isinstance(warn, bool) or not isinstance(warn, int) or not 1 <= warn <= 99:
            raise ValidationError("Uyarı yüzdesi 1–99 arasında tam sayı olmalıdır.")
        if unit not in ("HOURS", "DAYS", "MONTHS"):
            raise ValidationError("HOURS, DAYS veya MONTHS seçin.")
        reason = text(request.data, "reason", True)
        obj.active = False
        obj.save(update_fields=["active"])
        new = SLAPolicy.objects.create(
            priority=obj.priority,
            context=obj.context,
            amount=amount,
            unit=unit,
            warning_percent=warn,
            version=obj.version + 1,
        )
        audit(
            request.user,
            "sla.policy.versioned",
            new,
            {"previous_id": str(obj.pk), "reason": reason},
        )
        return Response(self.serialize(new))


def _fold_search(value):
    import unicodedata

    value = value.casefold().replace("ı", "i")
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def _search_matches(queryset, fields, query):
    """PostgreSQL lexical prefix + accent folding + bounded spelling fallback."""
    import re
    from django.contrib.postgres.search import (
        SearchVector,
        SearchQuery,
        SearchRank,
        TrigramSimilarity,
    )
    from django.contrib.postgres.lookups import Unaccent
    from django.db.models import F, Value, TextField
    from django.db.models.functions import Cast, Concat, Coalesce, Lower

    normalized = _fold_search(query)
    terms = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)[:8]
    if not terms:
        return queryset.none()
    expressions = []
    for field in fields:
        expressions.extend(
            [
                Coalesce(
                    Cast(F(field), TextField()), Value(""), output_field=TextField()
                ),
                Value(" "),
            ]
        )
    document = Lower(Unaccent(Concat(*expressions, output_field=TextField())))
    primary = Lower(
        Unaccent(
            Coalesce(
                Cast(F(fields[0]), TextField()), Value(""), output_field=TextField()
            )
        )
    )
    search_query = SearchQuery(
        " & ".join(term + ":*" for term in terms), search_type="raw", config="simple"
    )
    vector = SearchVector(document, config="simple")
    annotated = queryset.annotate(
        search_document=vector,
        search_text=document,
        search_rank=SearchRank(vector, search_query),
        search_similarity=TrigramSimilarity(primary, Value(normalized)),
    )
    matching = Q(search_document=search_query) | Q(search_text__contains=normalized)
    if len(normalized) >= 4:
        matching |= Q(search_similarity__gte=0.35)
    return annotated.filter(matching).order_by(
        "-search_rank", "-search_similarity", "pk"
    )


@api_view(["GET"])
def search_view(request):
    query = request.query_params.get("q", "").strip()[:120]
    if not query:
        return Response({"results": [], "count": 0})
    results = []
    for kind, queryset in [
        ("work", visible_work(request.user)),
        ("project", visible_projects(request.user)),
        ("case", visible_cases(request.user)),
    ]:
        if kind == "project":
            full_ids = [
                project.pk
                for project in queryset
                if can_read_project_detail(request.user, project)
            ]
            full = list(
                _search_matches(
                    queryset.filter(pk__in=full_ids),
                    ["title", "description", "expected_outcome"],
                    query,
                )[:8]
            )
            summary = list(
                _search_matches(queryset.exclude(pk__in=full_ids), ["title"], query)[:8]
            )
            found = (full + summary)[:8]
        else:
            found = _search_matches(
                queryset,
                ["title", "description", "expected_outcome"]
                if kind == "work"
                else ["title", "description"],
                query,
            )[:8]
        for obj in found:
            title = obj.title
            if kind == "project" and not can_read_project_detail(request.user, obj):
                revision = obj.revisions.filter(number=obj.published_revision).first()
                title = (
                    revision.content.get("title", obj.title) if revision else obj.title
                )
            results.append(
                {
                    "id": str(obj.pk),
                    "title": title,
                    "resource_type": kind,
                    "type": kind,
                    "status": obj.status,
                    "priority": obj.priority,
                }
            )
    people = _search_matches(
        api_narrow(request.user, User.objects.filter(is_active=True), "primary_org_id"),
        ["display_name", "username", "primary_org__name", "expertise"],
        query,
    ).select_related("primary_org")[:5]
    for person in people:
        results.append(
            {
                "id": str(person.pk),
                "title": person.display_name or person.username,
                "resource_type": "person",
                "type": "person",
                "subtitle": person.primary_org.name if person.primary_org else "",
            }
        )
    directory = OrgNode.objects.filter(
        pk__in=visible_org_ids(request.user), active=True
    )
    for org in _search_matches(
        directory, ["name", "code", "description", "expertise"], query
    )[:4]:
        results.append(
            {
                "id": str(org.pk),
                "title": org.name,
                "resource_type": "organization",
                "type": "organization",
                "subtitle": org.code,
            }
        )
    event_query = api_narrow(
        request.user,
        Event.objects.filter(
            Q(invitees=request.user)
            | Q(owner_org_id__in=manager_scope_ids(request.user))
        ).distinct(),
    )
    for kind, queryset, fields, title_field in [
        ("community", visible_cards(request.user), ["title", "body"], "title"),
        (
            "announcement",
            visible_announcements(request.user),
            ["title", "body"],
            "title",
        ),
        ("event", event_query, ["title", "description", "location"], "title"),
        ("credential", visible_credentials(request.user), ["name", "issuer"], "name"),
    ]:
        for obj in _search_matches(queryset, fields, query)[:3]:
            results.append(
                {
                    "id": str(obj.pk),
                    "title": getattr(obj, title_field),
                    "resource_type": kind,
                    "type": kind,
                }
            )
    return Response({"results": results[:25], "count": len(results[:25])})


@api_view(["GET", "POST"])
def test_mode_view(request):
    from django.conf import settings

    real = getattr(request, "real_user", request.user)
    require_admin(real)
    allowed = settings.ATLAS_ENV in ("test", "demo") and settings.ATLAS_TEST_GOD_MODE
    if request.method == "POST":
        ensure(
            allowed,
            "Kullanıcı denemesi ve God Mode yalnız sentetik test ortamında etkinleştirilebilir.",
        )
        mode = request.data.get("mode")
        if mode == "simulate":
            person = fetch(User, request.data.get("user_id"), is_active=True)
            request.session["atlas_effective_user"] = str(person.pk)
            request.session["atlas_god_mode"] = False
            audit(
                real,
                "test.simulation.started",
                person,
                {"effective_actor": str(person.pk)},
            )
        elif mode == "god":
            request.session.pop("atlas_effective_user", None)
            request.session["atlas_god_mode"] = True
            audit(real, "test.god.started", real)
        elif mode in ("stop", "normal"):
            request.session.pop("atlas_effective_user", None)
            request.session.pop("atlas_god_mode", None)
            audit(real, "test.identity.stopped", real)
        else:
            raise ValidationError("simulate, god veya stop seçin.")
    return Response(
        {
            "available": allowed,
            "environment": settings.ATLAS_ENV,
            "god_mode": bool(request.session.get("atlas_god_mode"))
            and not request.session.get("atlas_effective_user"),
            "effective_user_id": request.session.get("atlas_effective_user"),
            "real_actor_id": str(real.pk),
        }
    )


def test_mode_data(request):
    from django.conf import settings

    real = getattr(request, "real_user", request.user)
    available = settings.ATLAS_ENV in ("test", "demo") and settings.ATLAS_TEST_GOD_MODE
    return {
        "available": available,
        "environment": settings.ATLAS_ENV,
        "god_mode": bool(request.session.get("atlas_god_mode"))
        and not request.session.get("atlas_effective_user"),
        "effective_user_id": request.session.get("atlas_effective_user"),
        "real_actor_id": str(real.pk) if real.is_authenticated else None,
        "real_admin": real.is_authenticated and is_system_admin(real),
    }


class ContributionViewSet(DomainViewSet):
    serializer_class = ProgressSerializer

    def get_queryset(self):
        qs = ProgressEntry.objects.select_related(
            "author",
            "author_org",
            "project__appointment__user",
            "work__project__appointment__user",
            "work__case",
            "case",
        ).order_by("-created_at")
        return qs.filter(
            pk__in=[p.pk for p in qs if can_read_progress(self.request.user, p)]
        )

    def partial_update(self, request, pk=None):
        obj = self.locked()
        ensure(
            obj.author_id == request.user.pk,
            "Yalnız kendi katkınızı yeni sürümle düzeltebilirsiniz.",
        )
        unknown(request.data, {"version", "done", "next_step", "blocker"})
        if ProgressEntry.objects.filter(previous=obj).exists():
            raise Conflict("Katkının daha yeni bir sürümü var.")
        new = ProgressEntry.objects.create(
            project=obj.project,
            work=obj.work,
            case=obj.case,
            author=request.user,
            author_org=obj.author_org,
            previous=obj,
            version=obj.version + 1,
            done=text(request.data, "done", True),
            next_step=text(request.data, "next_step"),
            blocker=text(request.data, "blocker"),
        )
        audit(request.user, "progress.revised", new, {"previous_id": str(obj.pk)})
        return Response(self.get_serializer(new).data)
