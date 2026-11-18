import ipaddress
import json
import os
import socket
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from rest_framework.exceptions import ValidationError


def _env_list(name):
    raw = getattr(settings, name, os.environ.get(name, ""))
    return {
        str(item).strip().lower()
        for item in (raw.split(",") if isinstance(raw, str) else raw)
        if str(item).strip()
    }


def encrypt_secrets(value):
    key = getattr(
        settings, "ATLAS_ENCRYPTION_KEY", os.environ.get("ATLAS_ENCRYPTION_KEY", "")
    )
    if not key:
        raise ValidationError(
            {"secrets": "Sunucuda ATLAS_ENCRYPTION_KEY tanımlanmalı."}
        )
    try:
        return (
            Fernet(key.encode() if isinstance(key, str) else key)
            .encrypt(json.dumps(value).encode())
            .decode()
        )
    except (ValueError, TypeError):
        raise ValidationError({"secrets": "Sunucu şifreleme anahtarı geçersiz."})


def decrypt_secrets(encrypted):
    if not encrypted:
        return {}
    key = getattr(
        settings, "ATLAS_ENCRYPTION_KEY", os.environ.get("ATLAS_ENCRYPTION_KEY", "")
    )
    try:
        return json.loads(
            Fernet(key.encode() if isinstance(key, str) else key).decrypt(
                encrypted.encode()
            )
        )
    except (ValueError, TypeError, InvalidToken):
        raise ValidationError(
            {"secrets": "Entegrasyon sırrı açılamadı; sunucu anahtarını kontrol edin."}
        )


def validate_destination(host, *, scheme="https"):
    """Only deployment-authorized destinations; a UI setting cannot expand trust."""
    host = str(host or "").strip().lower().rstrip(".")
    allowed = _env_list("ATLAS_ALLOWED_INTEGRATION_HOSTS")
    private_allowed = _env_list("ATLAS_ALLOW_PRIVATE_INTEGRATION_HOSTS")
    if not host or host not in allowed:
        raise ValidationError(
            {"destination": "Hedef sunucu deployment izin listesinde bulunmuyor."}
        )
    if scheme not in {"https", "ldaps", "ldap", "smtp", "http"}:
        raise ValidationError({"destination": "Protokol desteklenmiyor."})
    if scheme == "http" and host not in private_allowed:
        raise ValidationError({"destination": "AI bağlantısı HTTPS kullanmalı."})
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        raise ValidationError({"destination": "Hedef sunucu çözümlenemedi."})
    for address in addresses:
        if not ipaddress.ip_address(address).is_global and host not in private_allowed:
            raise ValidationError(
                {"destination": "Özel ağ hedefi için ayrıca deployment izni gerekiyor."}
            )
    return host


def validate_url(value, *, ldap=False):
    parsed = urlparse(str(value or ""))
    if parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise ValidationError(
            {"url": "Bağlantı adresi kimlik, sorgu veya fragment içermemeli."}
        )
    if ldap and parsed.scheme not in {"ldaps", "ldap"}:
        raise ValidationError(
            {"url": "LDAP için LDAPS veya sertifikası doğrulanan StartTLS gerekir."}
        )
    if not ldap and parsed.scheme not in {"https", "http"}:
        raise ValidationError({"url": "HTTP(S) adresi gerekiyor."})
    validate_destination(parsed.hostname, scheme=parsed.scheme)
    return parsed
