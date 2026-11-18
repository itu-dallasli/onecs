"""Independently versioned AI connections using shared, pinned model settings."""
import hashlib
import json
import time
import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .directory import _require_real_admin as require_admin
from core.services import audit
from .diagnostics import connection_failure_message
from .models import AIConnectionProfile, ConfigurationVersion, IntegrationConfiguration, IntegrationTest
from .security import decrypt_secrets, encrypt_secrets, validate_url


CONNECTION_KEYS = {"enabled", "provider", "base_url"}


def _settings_fingerprint(config):
    return hashlib.sha256(json.dumps({key: value for key, value in config.items() if key not in CONNECTION_KEYS | {"default_profile_id"}}, sort_keys=True, default=str).encode()).hexdigest()


def _profile(profile_id, *, lock=False):
    queryset = AIConnectionProfile.objects.select_related("configuration")
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    result = queryset.filter(pk=profile_id).first()
    if not result:
        raise NotFound("AI bağlantı profili bulunamadı.")
    return result


def selected_ai_snapshot():
    from .services import integration_snapshot
    _, version, config = integration_snapshot("ai")
    profile_id = config.get("default_profile_id")
    profile = AIConnectionProfile.objects.filter(pk=profile_id, active=True).select_related("configuration").first() if profile_id else None
    return {"profile_id": str(profile.pk) if profile else None, "configuration_version": profile.configuration.active_version if profile else (version.version if version else 0), "settings_version": version.version if version else 0}


def resolve_ai_configuration(profile_id=None, configuration_version=None, settings_version=None, *, for_test=False):
    from .services import DEFAULTS, integration_snapshot
    global_configuration, global_version, global_config = integration_snapshot("ai")
    if settings_version is not None and settings_version != (global_version.version if global_version else 0):
        global_version = ConfigurationVersion.objects.filter(configuration=global_configuration, version=settings_version).first() if global_configuration else None
        if not global_version:
            return None, None, {**DEFAULTS["ai"], "enabled": False}, None, 0
        global_config = {**DEFAULTS["ai"], **global_version.config}
    # Explicit pinned legacy job (no profile, version given) must not pick a new default.
    if profile_id is None and configuration_version is None:
        profile_id = global_config.get("default_profile_id")
    if profile_id:
        profile = _profile(profile_id)
        number = configuration_version if configuration_version is not None else profile.configuration.active_version
        version = profile.configuration.versions.filter(version=number).first()
        if not version or not profile.active:
            return profile.configuration, None, {**global_config, "enabled": False}, profile, global_version.version if global_version else 0
        config = {**global_config, **version.config}
        config["enabled"] = bool(profile.active and version.config.get("enabled") and (for_test or global_config.get("enabled")))
        return profile.configuration, version, config, profile, global_version.version if global_version else 0
    version = global_version
    if configuration_version is not None and configuration_version != (version.version if version else 0):
        version = ConfigurationVersion.objects.filter(configuration=global_configuration, version=configuration_version).first() if global_configuration else None
        if version:
            global_config = {**DEFAULTS["ai"], **version.config}
    return global_configuration, version, global_config, None, global_version.version if global_version else 0


def public_ai_profile(profile):
    from .services import integration_snapshot
    _, shared_version, shared = integration_snapshot("ai")
    version = profile.configuration.versions.filter(version=profile.configuration.active_version).first()
    latest = profile.configuration.tests.order_by("-checked_at").first()
    return {"id": str(profile.pk), "name": profile.name, "active": profile.active, "is_default": str(profile.pk) == str(shared.get("default_profile_id")), "section": profile.configuration.section, "version": version.version if version else 0, "settings_version": shared_version.version if shared_version else 0, "config": version.config if version else {}, "secret_fields": version.secret_fields if version else [], "configured": bool(version and version.config.get("enabled")), "ready": bool(profile.active and version and latest and latest.status == "success" and latest.configuration_version == version.version and latest.settings_fingerprint == _settings_fingerprint(shared)), "latest_test": {"status": latest.status, "message": latest.message, "checked_at": latest.checked_at, "configuration_version": latest.configuration_version} if latest else None}


def _write_profile(actor, profile, config_changes, secrets, expected_version=None):
    if not isinstance(config_changes, dict) or set(config_changes) - CONNECTION_KEYS:
        raise ValidationError({"config": "Profil bağlantı alanları enabled, provider ve base_url ile sınırlıdır; model ayarları ortak sekmededir."})
    configuration = IntegrationConfiguration.objects.select_for_update().get(pk=profile.configuration_id)
    if expected_version is not None and expected_version != configuration.active_version:
        raise ValidationError({"expected_version": "AI bağlantı sürümü değişti; güncel profili yükleyin."})
    previous = configuration.versions.filter(version=configuration.active_version).first()
    config = {"enabled": False, "provider": "openai-compatible", "base_url": "", **(previous.config if previous else {}), **config_changes}
    if not isinstance(config.get("enabled"), bool) or config["provider"] != "openai-compatible" or not isinstance(config.get("base_url"), str) or len(config["base_url"]) > 2000:
        raise ValidationError({"config": "Geçerli OpenAI uyumlu bağlantı ayarları gerekiyor."})
    if config["enabled"]:
        validate_url(config["base_url"])
    if not isinstance(secrets, dict) or set(secrets) - {"api_key"}:
        raise ValidationError({"secrets": "Yalnız api_key destekleniyor."})
    stored_secrets = decrypt_secrets(previous.encrypted_secrets) if previous else {}
    if "api_key" in secrets:
        value = secrets["api_key"]
        if value is None:
            stored_secrets.pop("api_key", None)
        elif not isinstance(value, str) or len(value) > 16384:
            raise ValidationError({"api_key": "Geçerli kısa anahtar metni gerekiyor."})
        elif value:
            stored_secrets["api_key"] = value
    version = ConfigurationVersion.objects.create(configuration=configuration, version=configuration.active_version + 1, config=config, encrypted_secrets=encrypt_secrets(stored_secrets) if stored_secrets else "", secret_fields=sorted(stored_secrets), created_by=actor)
    configuration.active_version = version.version
    configuration.save(update_fields=["active_version", "updated_at"])
    profile.configuration = configuration
    audit(actor, "ai.profile.updated", profile, {"configuration_version": version.version, "changed_fields": sorted(config_changes), "secret_changed": "api_key" in secrets})
    return public_ai_profile(profile)


@transaction.atomic
def create_ai_profile(actor, name, config=None, secrets=None):
    require_admin(actor)
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise ValidationError({"name": "1–100 karakterlik bağlantı adı gerekiyor."})
    if AIConnectionProfile.objects.filter(active=True).count() >= 8:
        raise ValidationError({"profiles": "En fazla 8 etkin bağlantı profili oluşturulabilir."})
    profile_id = uuid.uuid4()
    configuration = IntegrationConfiguration.objects.create(section="ai_" + profile_id.hex[:24])
    profile = AIConnectionProfile.objects.create(id=profile_id, name=name.strip(), configuration=configuration, created_by=actor)
    return _write_profile(actor, profile, config or {}, secrets or {}, 0)


@transaction.atomic
def update_ai_profile(actor, profile_id, name=None, config=None, secrets=None, expected_version=None):
    require_admin(actor)
    profile = _profile(profile_id, lock=True)
    if not profile.active:
        raise ValidationError({"profile": "Arşivlenmiş bağlantı değiştirilemez."})
    if name is not None:
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            raise ValidationError({"name": "1–100 karakterlik bağlantı adı gerekiyor."})
        profile.name = name.strip()
        profile.save(update_fields=["name"])
    return _write_profile(actor, profile, config or {}, secrets or {}, expected_version)


@transaction.atomic
def set_default_ai_profile(actor, profile_id, expected_version=None):
    require_admin(actor)
    from .services import update_configuration
    profile = _profile(profile_id, lock=True)
    if not profile.active:
        raise ValidationError({"profile": "Arşivlenmiş bağlantı seçilemez."})
    if expected_version is not None and expected_version != profile.configuration.active_version:
        raise ValidationError({"expected_version": "Bağlantı sürümü değişti."})
    version = profile.configuration.versions.get(version=profile.configuration.active_version)
    if not version.config.get("enabled"):
        raise ValidationError({"profile": "Varsayılan bağlantı etkin olmalı."})
    update_configuration(actor, "ai", {"default_profile_id": str(profile.pk), "enabled": True})
    audit(actor, "ai.profile.default.selected", profile, {"configuration_version": version.version})
    return public_ai_profile(profile)


@transaction.atomic
def archive_ai_profile(actor, profile_id):
    require_admin(actor)
    profile = _profile(profile_id, lock=True)
    if public_ai_profile(profile)["is_default"]:
        raise ValidationError({"profile": "Önce başka bir varsayılan bağlantı seçin."})
    profile.active = False
    profile.save(update_fields=["active"])
    audit(actor, "ai.profile.archived", profile)
    return {"id": str(profile.pk), "active": False}


def test_ai_profile(actor, profile_id, expected_version=None):
    require_admin(actor)
    from .services import _ai_call, _reserve_ai, _record_usage
    profile = _profile(profile_id)
    _, version, config, _, settings_version = resolve_ai_configuration(profile_id, for_test=True)
    if expected_version is not None and expected_version != (version.version if version else 0):
        raise ValidationError({"expected_version": "Bağlantı sürümü değişti."})
    status, message = "unconfigured", "AI bağlantısı etkin değil veya model ayarı eksik."
    if version and config.get("enabled") and config.get("model"):
        usage = _reserve_ai(actor, version, config, "connection_test", 30, 8, profile=profile, settings_version=settings_version)
        started = time.monotonic()
        try:
            result = _ai_call(config, decrypt_secrets(version.encrypted_secrets), [{"role": "user", "content": "Reply OK"}], 8)
            if not result.get("choices"):
                raise ValueError("Empty model response")
            _record_usage(usage, result, time.monotonic() - started)
            status, message = "success", "Bu bağlantı profili ortak model ayarlarıyla gerçek kısa isteğe yanıt verdi."
        except Exception as exc:
            usage.status, usage.completed_at = "unknown", timezone.now()
            usage.save(update_fields=["status", "completed_at"])
            status, message = "failure", connection_failure_message(exc, "ai")
    saved = IntegrationTest.objects.create(configuration=profile.configuration, configuration_version=version.version if version else 0, settings_fingerprint=_settings_fingerprint(config), status=status, message=message, checked_by=actor)
    audit(actor, "ai.profile.tested", profile, {"status": status, "configuration_version": saved.configuration_version, "settings_version": settings_version})
    return {"status": status, "message": message, "checked_at": saved.checked_at, "configuration_version": saved.configuration_version, "profile": public_ai_profile(profile)}
