from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes

from core.models import (
    AuditEvent,
    OrgNode,
    RoleGrant,
    BackgroundJob,
    OutboxEvent,
    Report,
)
from core.policy import require_admin, has_role, can_manage_org
from core.services import audit
from core.exceptions import Conflict

from .models import AIUsage, IntegrationConfiguration, AIConnectionProfile
from .serializers import UserSerializer
from .services import (
    SECTIONS,
    public_configuration,
    provision_ldap_identity,
    test_integration,
    update_configuration,
)


ROLE_NAMES = [
    "EMPLOYEE",
    "TEAM_MANAGER",
    "UNIT_HEAD",
    "DIRECTOR",
    "PROJECT_MANAGER",
    "SYSTEM_ADMIN",
]
BUSINESS_ROLES = {"TEAM_MANAGER", "UNIT_HEAD", "DIRECTOR", "PROJECT_MANAGER"}


def _require_admin(request):
    # Token clients are read-only and cannot reach configuration or impersonate an admin.
    if request.auth:
        raise PermissionDenied("Entegrasyon tokenları yönetim arayüzünü kullanamaz.")
    real_actor = getattr(request.user, "_real_actor", request.user)
    if real_actor.pk != request.user.pk:
        raise PermissionDenied(
            "Kullanıcı görünümü denenirken yönetim ayarları değiştirilemez."
        )
    require_admin(request.user)


class AdminView(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        _require_admin(request)


class SettingsView(AdminView):
    @extend_schema(
        tags=["Administration"],
        responses=OpenApiTypes.OBJECT,
        description="Versioned integration configuration. Secret values are never returned.",
    )
    def get(self, request, section=None):
        if section:
            return Response(public_configuration(section))
        return Response(
            {"sections": [public_configuration(item) for item in sorted(SECTIONS)]}
        )

    @transaction.atomic
    @extend_schema(
        tags=["Administration"],
        request=OpenApiTypes.OBJECT,
        responses=OpenApiTypes.OBJECT,
        description="Change config/secrets with expected_version optimistic concurrency. Requires an actual administrator session.",
    )
    def patch(self, request, section=None):
        if section is None:
            raise ValidationError(
                {"section": "Değiştirilecek ayar sekmesini belirtin."}
            )
        if not isinstance(request.data.get("config", {}), dict):
            raise ValidationError({"config": "Nesne gerekiyor."})
        if request.data.get("activate", True) is not True:
            raise ValidationError(
                {
                    "activate": "Taslak ayar sürümü henüz desteklenmiyor; etkinleştirmeyi açık seçin."
                }
            )
        result = update_configuration(
            request.user,
            section,
            request.data.get("config", {}),
            request.data.get("secrets", {}),
            request.data.get("expected_version"),
        )
        audit(
            request.user,
            "integration.configuration.updated",
            IntegrationConfiguration.objects.get(section=section),
            {
                "section": section,
                "version": result["version"],
                "changed_fields": sorted(request.data.get("config", {})),
                "secret_fields_changed": sorted(request.data.get("secrets", {})),
            },
        )
        return Response(result)


class SettingsIndexView(SettingsView):
    @extend_schema(
        operation_id="admin_settings_index",
        tags=["Administration"],
        responses=OpenApiTypes.OBJECT,
        description="List available configuration sections without exposing stored secret values.",
    )
    def get(self, request, section=None):
        return super().get(request, section)


class IntegrationTestView(AdminView):
    @extend_schema(
        tags=["Administration"],
        request=OpenApiTypes.OBJECT,
        responses=OpenApiTypes.OBJECT,
        description="Run an actual bounded connection test against a deployment-authorized target.",
    )
    def post(self, request, section):
        result = test_integration(request.user, section, request.data.get("recipient"))
        audit(
            request.user,
            "integration.connection.tested",
            IntegrationConfiguration.objects.get(section=section),
            {
                "section": section,
                "status": result["status"],
                "configuration_version": result["configuration_version"],
            },
        )
        return Response(
            result,
            status=200
            if result["status"] == "success"
            else (409 if result["status"] == "unconfigured" else 400),
        )


def _usage_date(value, key):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        raise ValidationError({key: "YYYY-MM-DD tarihi gerekiyor."})


class AIUsageView(AdminView):
    @extend_schema(
        tags=["Administration"],
        responses=OpenApiTypes.OBJECT,
        description="Provider usage and estimated cost with from/to YYYY-MM-DD, model and operation filters; unknown values remain null.",
    )
    def get(self, request):
        records = AIUsage.objects.select_related("actor", "profile").order_by("-created_at")
        since, until = (
            _usage_date(request.query_params.get("from"), "from"),
            _usage_date(request.query_params.get("to"), "to"),
        )
        if since and until and since > until:
            raise ValidationError({"to": "Bitiş tarihi başlangıçtan önce olamaz."})
        if since:
            records = records.filter(created_at__date__gte=since)
        if until:
            records = records.filter(created_at__date__lte=until)
        if request.query_params.get("model"):
            records = records.filter(model=request.query_params["model"])
        if request.query_params.get("operation"):
            records = records.filter(operation=request.query_params["operation"])
        if request.query_params.get("profile_id"):
            records = records.filter(profile_id=request.query_params["profile_id"])
        totals = records.aggregate(
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            estimated_cost=Sum("estimated_cost"),
            reserved_tokens=Sum("reserved_tokens"),
        )
        totals.update(
            {
                "calls": records.count(),
                "unknown_measurements": records.filter(measurement="unknown").count(),
                "currency": "USD",
                "cost_label": "Yapılandırılmış fiyatlarla hesaplanan tahmin",
            }
        )
        results = [
            {
                "id": item.pk,
                "actor": item.actor.display_name or item.actor.username
                if item.actor
                else None,
                "model": item.model,
                "operation": item.operation,
                "profile_id": str(item.profile_id) if item.profile_id else None,
                "profile_name": item.profile.name if item.profile_id else "Eski / ortak bağlantı",
                "configuration_version": item.configuration_version,
                "settings_version": item.settings_version,
                "status": item.status,
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
                "reserved_tokens": item.reserved_tokens,
                "measurement": item.measurement,
                "estimated_cost": item.estimated_cost,
                "duration_ms": item.duration_ms,
                "created_at": item.created_at,
            }
            for item in records[:200]
        ]
        return Response({"totals": totals, "results": results})


class LDAPDiscoverView(AdminView):
    @extend_schema(tags=["Administration"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        from .services import directory_discover
        try:
            return Response(directory_discover(request.user))
        except (ValidationError, PermissionDenied):
            raise
        except Exception:
            raise ValidationError({"ldap": "RootDSE okunamadı; bağlantı, TLS ve servis okuma kapsamını kontrol edin."})


class LDAPSearchView(AdminView):
    @extend_schema(tags=["Administration"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        from .services import directory_search
        try:
            result = directory_search(request.user, request.data.get("kind", "users"), request.data.get("query", ""), request.data.get("base_dn"))
        except (ValidationError, PermissionDenied):
            raise
        except Exception:
            raise ValidationError({"ldap": "Dizin sorgusu tamamlanamadı; bağlantı, TLS ve servis okuma kapsamını kontrol edin."})
        return Response(result)


class LDAPImportView(AdminView):
    @transaction.atomic
    @extend_schema(tags=["Administration"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        from .services import directory_import
        if not request.data.get("batch_id"):
            raise ValidationError({"batch_id": "Önizleme paketi gerekiyor."})
        users = directory_import(request.user, request.data["batch_id"], request.data.get("entries"), request.data.get("expected_config_version"))
        return Response({"count": len(users), "imported": UserSerializer(users, many=True).data})


class AIProfilesView(AdminView):
    @extend_schema(operation_id="admin_ai_profiles_list", tags=["Administration"], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        from .services import public_ai_profile, selected_ai_snapshot
        profiles = AIConnectionProfile.objects.select_related("configuration").filter(active=True).order_by("created_at")
        return Response({"results": [public_ai_profile(profile) for profile in profiles], "default_profile_id": selected_ai_snapshot()["profile_id"]})

    @extend_schema(tags=["Administration"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        from .services import create_ai_profile
        return Response(create_ai_profile(request.user, request.data.get("name"), request.data.get("config"), request.data.get("secrets")), status=201)


class AIProfileDetailView(AdminView):
    @extend_schema(operation_id="admin_ai_profile_retrieve", tags=["Administration"], responses=OpenApiTypes.OBJECT)
    def get(self, request, profile_id):
        from .services import public_ai_profile
        profile = AIConnectionProfile.objects.select_related("configuration").filter(pk=profile_id).first()
        if not profile:
            raise NotFound("AI bağlantı profili bulunamadı.")
        return Response(public_ai_profile(profile))

    @extend_schema(tags=["Administration"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def patch(self, request, profile_id):
        from .services import update_ai_profile
        return Response(update_ai_profile(request.user, profile_id, request.data.get("name"), request.data.get("config"), request.data.get("secrets"), request.data.get("expected_version")))

    @extend_schema(tags=["Administration"], responses=OpenApiTypes.OBJECT)
    def delete(self, request, profile_id):
        from .services import archive_ai_profile
        return Response(archive_ai_profile(request.user, profile_id))


class AIProfileTestView(AdminView):
    @extend_schema(tags=["Administration"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request, profile_id):
        from .services import test_ai_profile
        result = test_ai_profile(request.user, profile_id, request.data.get("expected_version"))
        return Response(result, status=200 if result["status"] == "success" else 409 if result["status"] == "unconfigured" else 400)


class AIProfileDefaultView(AdminView):
    @extend_schema(tags=["Administration"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request, profile_id):
        from .services import set_default_ai_profile
        return Response(set_default_ai_profile(request.user, profile_id, request.data.get("expected_version")))


def _grant_roles(actor, target, roles):
    if actor.pk == target.pk:
        raise PermissionDenied("Kendi rol ve kapsamınızı değiştiremezsiniz.")
    if not isinstance(roles, list) or len(roles) > 25:
        raise ValidationError({"roles": "En fazla 25 rol atanabilir."})
    business_allowed = has_role(actor, "DIRECTOR")
    if (
        not business_allowed
        and target.role_grants.filter(role__in=BUSINESS_ROLES, active=True).exists()
    ):
        raise PermissionDenied(
            "İş yönetimi rollerini değiştirmek için direktör yetkisi gerekiyor."
        )
    prepared = []
    for entry in roles:
        if not isinstance(entry, dict) or entry.get("role") not in ROLE_NAMES:
            raise ValidationError({"roles": "Geçersiz rol."})
        role = entry["role"]
        if role in BUSINESS_ROLES and not business_allowed:
            raise PermissionDenied(
                "Teknik yöneticilik tek başına iş yönetimi rolü verme yetkisi sağlamaz."
            )
        org = None
        if entry.get("org_node"):
            org = OrgNode.objects.filter(pk=entry["org_node"], active=True).first()
            if not org:
                raise ValidationError({"org_node": "Etkin organizasyon bulunamadı."})
        if role != "SYSTEM_ADMIN" and not org:
            org = target.primary_org
            if not org:
                raise ValidationError(
                    {"org_node": "Bu rol için organizasyon kapsamı gerekiyor."}
                )
        if role in BUSINESS_ROLES and not can_manage_org(actor, org):
            raise PermissionDenied(
                "İş rolü yalnız kendi yönetim kapsamınızda verilebilir."
            )
        expires_at = (
            parse_datetime(entry["expires_at"]) if entry.get("expires_at") else None
        )
        if entry.get("expires_at") and (
            not expires_at
            or timezone.is_naive(expires_at)
            or expires_at <= timezone.now()
        ):
            raise ValidationError(
                {"expires_at": "Gelecekte saat dilimli tarih gerekiyor."}
            )
        if entry.get("permissions"):
            raise ValidationError(
                {
                    "permissions": "Özel delegasyonlar ilgili domain akışından verilmelidir."
                }
            )
        prepared.append(
            {
                "role": role,
                "org_node": org,
                "includes_descendants": bool(entry.get("includes_descendants", True)),
                "active": bool(entry.get("active", True)),
                "expires_at": expires_at,
                "granted_by": actor,
            }
        )
    target.role_grants.update(active=False)
    for item in prepared:
        RoleGrant.objects.create(user=target, **item)
    get_user_model().objects.filter(pk=target.pk).update(
        access_version=F("access_version") + 1
    )


class UsersView(AdminView):
    @extend_schema(tags=["Administration"], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        users = (
            get_user_model()
            .objects.select_related("primary_org")
            .prefetch_related("role_grants")
            .order_by("username")
        )
        query = request.query_params.get("search", "").strip()[:100]
        if query:
            users = users.filter(
                Q(username__icontains=query)
                | Q(display_name__icontains=query)
                | Q(email__icontains=query)
            )
        if request.query_params.get("archived") != "true":
            users = users.filter(is_active=True)
        source = request.query_params.get(
            "source", request.query_params.get("identity_source")
        )
        if source in {"local", "ldap"}:
            users = users.filter(identity_source=source)
        return Response(
            {
                "count": users.count(),
                "results": UserSerializer(users[:250], many=True).data,
            }
        )

    @transaction.atomic
    @extend_schema(
        tags=["Administration"], request=UserSerializer, responses={201: UserSerializer}
    )
    def post(self, request):
        # Identity provisioning is an explicitly trusted, audited technical action.
        # It may place a new ordinary employee in an org; it never grants management
        # authority. Business-role grants require the director's current scope.
        data = dict(request.data)
        roles = data.pop("roles", None)
        serializer = UserSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        if user.identity_source == "ldap":
            provision_ldap_identity(user)
        if roles is not None:
            _grant_roles(request.user, user, roles)
            user.refresh_from_db(fields=["access_version"])
        elif user.primary_org:
            RoleGrant.objects.create(
                user=user,
                role="EMPLOYEE",
                org_node=user.primary_org,
                granted_by=request.user,
            )
        audit(
            request.user,
            "identity.user.created",
            user,
            {"source": user.identity_source},
        )
        return Response(UserSerializer(user).data, status=201)


class UserDetailView(AdminView):
    @transaction.atomic
    @extend_schema(
        tags=["Administration"],
        request=UserSerializer,
        responses=UserSerializer,
        description="A technical administrator cannot grant business roles, change their own access, or reset a business manager's credentials without director authority.",
    )
    def patch(self, request, user_id):
        user = get_user_model().objects.select_for_update().filter(pk=user_id).first()
        if not user:
            raise NotFound("Kullanıcı bulunamadı.")
        data = dict(request.data)
        roles = data.pop("roles", None)
        expected_version = data.pop("expected_access_version", None)
        if expected_version is not None and expected_version != user.access_version:
            raise Conflict("Kullanıcı kaydı değişti. Güncel kaydı yükleyin.")
        if user.pk == request.user.pk and (
            roles is not None
            or "is_active" in data
            or "primary_org" in data
            or "username" in data
        ):
            raise PermissionDenied("Kendi erişim kapsamınızı değiştiremezsiniz.")
        if (
            user.role_grants.filter(role__in=BUSINESS_ROLES, active=True).exists()
            and user.pk != request.user.pk
            and not has_role(request.user, "DIRECTOR")
        ):
            raise PermissionDenied(
                "İş yöneticisinin kapsamını değiştirmek için direktör yetkisi gerekiyor."
            )
        serializer = UserSerializer(user, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        if roles is not None:
            _grant_roles(request.user, user, roles)
            user.refresh_from_db(fields=["access_version"])
        audit(
            request.user,
            "identity.user.updated",
            user,
            {
                "fields": sorted(key for key in data if key != "password"),
                "password_changed": "password" in data,
                "roles_changed": roles is not None,
            },
        )
        return Response(UserSerializer(user).data)


class RolesView(AdminView):
    @extend_schema(tags=["Administration"], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(
            {
                "roles": [
                    {
                        "value": role,
                        "code": role,
                        "label": role.replace("_", " "),
                        "business_role": role in BUSINESS_ROLES,
                    }
                    for role in ROLE_NAMES
                ],
                "business_grant_allowed": has_role(request.user, "DIRECTOR"),
            }
        )


class AuditView(AdminView):
    @extend_schema(
        tags=["Administration"],
        responses=OpenApiTypes.OBJECT,
        description="Metadata-only audit trail. Restricted domain payloads and secrets are excluded.",
    )
    def get(self, request):
        records = AuditEvent.objects.select_related("actor", "real_actor").order_by(
            "-created_at"
        )
        if request.query_params.get("action"):
            records = records.filter(
                action__icontains=request.query_params["action"][:100]
            )
        results = [
            {
                "id": item.pk,
                "action": item.action,
                "actor": str(item.actor) if item.actor else None,
                "real_actor": str(item.real_actor) if item.real_actor else None,
                "object_type": item.object_type,
                "object_id": item.object_id,
                "created_at": item.created_at,
            }
            for item in records[:250]
        ]
        # Audit payloads can contain restricted domain details: generic technical viewer gets metadata only.
        return Response({"count": records.count(), "results": results})


def _job_metadata(record, kind):
    return {
        "id": record.pk,
        "kind": kind,
        "task_kind": record.kind if kind == "job" else "EMAIL_NOTIFICATION",
        "status": record.status,
        "attempts": record.attempts,
        "last_error": record.last_error,
        "next_attempt_at": record.next_attempt_at,
        "lease_until": record.lease_until,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "version": record.version,
    }


class JobsView(AdminView):
    @extend_schema(
        tags=["Administration"],
        responses=OpenApiTypes.OBJECT,
        description="Durable jobs and outbox delivery metadata. Domain payload, report text and email body are excluded.",
    )
    def get(self, request):
        jobs, outbox = BackgroundJob.objects.all(), OutboxEvent.objects.all()
        if request.query_params.get("status"):
            jobs = jobs.filter(status=request.query_params["status"][:30])
            outbox = outbox.filter(status=request.query_params["status"][:30])
        kind = request.query_params.get("kind")
        if kind not in (None, "", "job", "outbox"):
            raise ValidationError({"kind": "job veya outbox seçin."})
        if kind == "job":
            outbox = outbox.none()
        elif kind == "outbox":
            jobs = jobs.none()
        results = [
            _job_metadata(item, "job") for item in jobs.order_by("-created_at")[:200]
        ]
        results += [
            _job_metadata(item, "outbox")
            for item in outbox.order_by("-created_at")[:200]
        ]
        results.sort(key=lambda item: item["created_at"], reverse=True)
        return Response(
            {"count": jobs.count() + outbox.count(), "results": results[:200]}
        )


class JobRetryView(AdminView):
    @transaction.atomic
    @extend_schema(
        tags=["Administration"],
        request=OpenApiTypes.OBJECT,
        responses=OpenApiTypes.OBJECT,
        description="Deliberate retry of a failed durable job/delivery. UNKNOWN email requires acknowledge_unknown=true because delivery may already have happened.",
    )
    def post(self, request, job_id):
        kind = request.data.get("kind")
        if kind not in {"job", "outbox"}:
            raise ValidationError({"kind": "job veya outbox seçin."})
        model = BackgroundJob if kind == "job" else OutboxEvent
        record = model.objects.select_for_update().filter(pk=job_id).first()
        if not record:
            raise NotFound("Kalıcı işlem bulunamadı.")
        allowed = (
            {"FAILED"}
            if kind == "job"
            else {"FAILED", "UNKNOWN", "WAITING_CONFIGURATION", "BLOCKED"}
        )
        if record.status not in allowed:
            raise ValidationError(
                {"status": "Bu durumdaki işlem elle yeniden başlatılamaz."}
            )
        if (
            record.status == "UNKNOWN"
            and request.data.get("acknowledge_unknown") is not True
        ):
            raise ValidationError(
                {
                    "acknowledge_unknown": "İleti daha önce teslim edilmiş olabilir. Olası mükerrer gönderimi açıkça onaylayın."
                }
            )
        if kind == "job" and not record.actor.is_active:
            raise ValidationError(
                {"actor": "İş sahibi etkin değil; yeniden deneme yapılamaz."}
            )
        before = {"status": record.status, "attempts": record.attempts}
        record.status, record.attempts, record.next_attempt_at = (
            "PENDING",
            0,
            timezone.now(),
        )
        record.lease_until, record.lease_token, record.last_error = None, None, ""
        record.version += 1
        record.save()
        if kind == "job":
            Report.objects.filter(job=record, status="FAILED").update(
                status="GENERATING"
            )
        audit(
            request.user,
            "operations.manual_retry",
            record,
            {
                "kind": kind,
                "previous": before,
                "acknowledge_unknown": request.data.get("acknowledge_unknown") is True,
                "reason": str(
                    request.data.get(
                        "reason", "Yönetici tarafından kontrollü yeniden deneme"
                    )
                )[:500],
            },
        )
        return Response(_job_metadata(record, kind))
