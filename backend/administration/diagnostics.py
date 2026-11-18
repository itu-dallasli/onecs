"""Public connection failures without provider bodies, addresses or credentials."""

import socket
import ssl

import httpx
from rest_framework.exceptions import ValidationError


def _validation_messages(detail):
    if isinstance(detail, dict):
        return [text for value in detail.values() for text in _validation_messages(value)]
    if isinstance(detail, (list, tuple)):
        return [text for value in detail for text in _validation_messages(value)]
    return [str(detail)]


def connection_failure_message(exc, section):
    """Classify failures; never return raw SDK exceptions or HTTP response content."""
    if isinstance(exc, ValidationError):
        # These are application-owned validation messages, not an SDK exception repr.
        return " ".join(_validation_messages(exc.detail))[:350]

    label = {"ldap": "LDAP", "ai": "Model", "smtp": "SMTP"}.get(section, "Servis")
    chain, current, seen = [], exc, set()
    while current is not None and id(current) not in seen and len(chain) < 10:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__

    # ldap3 wraps OpenSSL verification errors in LDAPStartTLSError text.
    # Inspect it only to choose fixed messages; never store or return that text.
    signatures = " ".join(str(error)[:4000].lower() for error in chain)
    verification_codes = {
        error.verify_code for error in chain
        if isinstance(error, ssl.SSLCertVerificationError) and hasattr(error, "verify_code")
    }
    if 10 in verification_codes or "certificate has expired" in signatures:
        return f"{label} TLS sertifikasının veya sertifika zincirindeki bir sertifikanın süresi dolmuş. Sunucu saatini kontrol edin; süresi dolan sertifikayı yenileyin."
    if 9 in verification_codes or "certificate is not yet valid" in signatures:
        return f"{label} TLS sertifikası henüz geçerli değil. Sunucu saatini ve sertifikanın başlangıç tarihini kontrol edin."
    if 62 in verification_codes or any(text in signatures for text in ("hostname mismatch", "ip address mismatch", "doesn't match", "not in certificate")):
        return f"{label} TLS sertifikası hedef sunucu adıyla eşleşmiyor. Bağlantı adresini ve sertifikanın sunucu adlarını kontrol edin."
    if any(text in signatures for text in ("self-signed certificate", "self signed certificate", "unable to get local issuer certificate", "unable to verify the first certificate")):
        return f"{label} TLS sertifika zincirine güvenilemiyor. Sunucunun ara sertifikalarını ve uygulamanın güvenilir CA deposunu kontrol edin."
    if any(isinstance(error, ssl.SSLError) for error in chain) or any(text in signatures for text in ("certificate_verify_failed", "certificate verify failed", "wrap socket error", "starttls")):
        return f"{label} TLS bağlantısı doğrulanamadı. Sertifika zincirini ve TLS yapılandırmasını kontrol edin."
    if any(isinstance(error, socket.gaierror) for error in chain):
        return f"{label} hedefinin DNS adı çözümlenemedi. DNS ve VPN bağlantısını kontrol edin."
    if any(isinstance(error, (TimeoutError, httpx.TimeoutException)) for error in chain) or "timed out" in signatures:
        return f"{label} bağlantısı zaman aşımına uğradı. VPN, ağ erişimi ve servis yanıt süresini kontrol edin."

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 401:
            return "Model servisi API anahtarını kabul etmedi (HTTP 401). Kayıtlı anahtarı kontrol edin."
        if status == 403:
            return "Model servisi erişimi reddetti (HTTP 403). Anahtarın model ve servis yetkisini kontrol edin."
        if status == 404:
            return "Model endpoint'i veya seçilen model bulunamadı (HTTP 404). API adresini ve ortak model adını kontrol edin."
        if status == 429:
            return "Model servisi kota veya istek sınırına ulaştı (HTTP 429). Sağlayıcı kotasını kontrol edip daha sonra deneyin."
        if status >= 500:
            return f"Model servisi geçici sunucu hatası döndürdü (HTTP {status}). Daha sonra yeniden deneyin."
        if 300 <= status < 400:
            return "Model servisi yönlendirme döndürdü. İzinli, doğrudan API endpoint'ini kullanın."
        return f"Model servisi isteği kabul etmedi (HTTP {status}). Model ve istek ayarlarını kontrol edin."

    if section == "ldap":
        from ldap3.core.exceptions import LDAPBindError, LDAPInvalidCredentialsResult, LDAPInsufficientAccessRightsResult

        if isinstance(exc, (LDAPBindError, LDAPInvalidCredentialsResult)):
            return "LDAP servis hesabı bind işlemi reddedildi. Bind kullanıcısını, kayıtlı parolayı ve hesap durumunu kontrol edin."
        if isinstance(exc, LDAPInsufficientAccessRightsResult):
            return "LDAP servis hesabının dizin okuma yetkisi yok. Base DN ve servis hesabı yetkilerini kontrol edin."
    if any(isinstance(error, (ConnectionError, httpx.ConnectError, OSError)) for error in chain):
        return f"{label} sunucusuna bağlantı kurulamadı. VPN, hedef adresi, port ve ağ erişimini kontrol edin."
    if section == "ai" and isinstance(exc, (ValueError, TypeError, KeyError)):
        return "Model servisi beklenen yanıt biçimini döndürmedi. OpenAI uyumlu endpoint ve model ayarını kontrol edin."
    return f"{label} bağlantısı doğrulanamadı. Hedef, TLS, kimlik bilgileri ve servis izinlerini kontrol edin."
