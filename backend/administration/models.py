"""Versioned integration settings; secrets never enter API representations."""

import uuid

from django.conf import settings
from django.db import models


class IntegrationConfiguration(models.Model):
    section = models.CharField(max_length=30, unique=True)
    active_version = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class ConfigurationVersion(models.Model):
    configuration = models.ForeignKey(
        IntegrationConfiguration, related_name="versions", on_delete=models.CASCADE
    )
    version = models.PositiveIntegerField()
    config = models.JSONField(default=dict)
    encrypted_secrets = models.TextField(blank=True)
    secret_fields = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["configuration", "version"], name="admin_config_version_unique"
            )
        ]


class IntegrationTest(models.Model):
    configuration = models.ForeignKey(
        IntegrationConfiguration, related_name="tests", on_delete=models.CASCADE
    )
    configuration_version = models.PositiveIntegerField()
    settings_fingerprint = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20)
    message = models.CharField(max_length=400)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    checked_at = models.DateTimeField(auto_now_add=True)


class AIUsage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    model = models.CharField(max_length=120)
    operation = models.CharField(max_length=40)
    status = models.CharField(max_length=20, default="reserved")
    configuration_version = models.PositiveIntegerField()
    profile = models.ForeignKey("AIConnectionProfile", null=True, on_delete=models.PROTECT)
    settings_version = models.PositiveIntegerField(default=0)
    request_id = models.CharField(max_length=100, blank=True)
    request_fingerprint = models.CharField(max_length=64, blank=True)
    result = models.JSONField(default=dict)
    input_tokens = models.PositiveIntegerField(null=True)
    output_tokens = models.PositiveIntegerField(null=True)
    reserved_tokens = models.PositiveIntegerField(default=0)
    measurement = models.CharField(max_length=20, default="unknown")
    estimated_cost = models.DecimalField(max_digits=18, decimal_places=8, null=True)
    currency = models.CharField(max_length=3, default="USD")
    price_snapshot = models.JSONField(default=dict)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "operation", "request_id"],
                condition=~models.Q(request_id=""),
                name="ai_job_request_unique",
            )
        ]


class LDAPIdentity(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ldap_identity"
    )
    subject = models.CharField(max_length=300, unique=True)
    distinguished_name = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict)
    synced_at = models.DateTimeField(null=True)


class LDAPManagedGrant(models.Model):
    """Only these grants are reconciled from verified directory membership."""

    identity = models.ForeignKey(
        LDAPIdentity, on_delete=models.CASCADE, related_name="managed_grants"
    )
    grant = models.OneToOneField(
        "core.RoleGrant", on_delete=models.CASCADE, related_name="ldap_managed"
    )
    key = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["identity", "key"], name="ldap_managed_grant_unique"
            )
        ]


class AIConnectionProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    configuration = models.OneToOneField(IntegrationConfiguration, on_delete=models.PROTECT)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class LDAPImportBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    configuration_version = models.PositiveIntegerField()
    kind = models.CharField(max_length=10)
    base_dn = models.CharField(max_length=1000)
    candidates = models.JSONField(default=list)
    imported_subjects = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
