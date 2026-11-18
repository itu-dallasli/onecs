from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from core.models import RoleGrant


class GrantSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleGrant
        fields = [
            "id",
            "role",
            "org_node",
            "includes_descendants",
            "active",
            "expires_at",
            "permissions",
        ]


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    roles = GrantSerializer(source="role_grants", many=True, read_only=True)
    primary_org_name = serializers.CharField(
        source="primary_org.name", read_only=True, allow_null=True
    )
    ldap_metadata = serializers.SerializerMethodField()

    def get_ldap_metadata(self, user) -> dict | None:
        if user.identity_source != "ldap":
            return None
        try:
            return user.ldap_identity.metadata
        except AttributeError:
            return None

    class Meta:
        model = get_user_model()
        fields = [
            "id",
            "username",
            "display_name",
            "email",
            "is_active",
            "identity_source",
            "primary_org",
            "primary_org_name",
            "expertise",
            "roles",
            "password",
            "access_version",
            "ldap_metadata",
        ]
        read_only_fields = ["id", "access_version"]

    def validate_identity_source(self, value):
        if value not in {"local", "ldap"}:
            raise serializers.ValidationError("Kaynak local veya ldap olmalı.")
        if self.instance and value != self.instance.identity_source:
            raise serializers.ValidationError(
                "Mevcut hesabın kimlik kaynağı değiştirilemez."
            )
        return value

    def validate_expertise(self, value):
        if (
            not isinstance(value, list)
            or len(value) > 20
            or any(not isinstance(item, str) or len(item) > 100 for item in value)
        ):
            raise serializers.ValidationError(
                "En fazla 20 kısa uzmanlık alanı girilebilir."
            )
        return value

    def validate(self, attrs):
        source = attrs.get(
            "identity_source",
            self.instance.identity_source if self.instance else "local",
        )
        if attrs.get("password"):
            if source != "local":
                raise serializers.ValidationError(
                    {"password": "LDAP parolası uygulamaya kaydedilmez."}
                )
            validate_password(attrs["password"], self.instance)
        if not self.instance and source == "local" and not attrs.get("password"):
            raise serializers.ValidationError(
                {"password": "Yerel kullanıcı için parola gerekiyor."}
            )
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = get_user_model()(**validated_data)
        user.set_password(password) if password else user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.access_version += 1
        instance.save()
        return instance
