import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from .models import ApiClient


class ScopedJWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        try:
            claims = jwt.decode(
                header[7:],
                settings.SECRET_KEY,
                algorithms=["HS256"],
                audience=settings.JWT_AUDIENCE,
                issuer=settings.JWT_ISSUER,
                options={"require": ["exp", "iat", "sub", "aud", "iss", "jti"]},
            )
            client = ApiClient.objects.select_related("user").get(
                pk=claims["sub"], active=True, token_version=claims.get("ver")
            )
            if not client.user.is_active:
                raise ValueError()
        except Exception as exc:
            raise AuthenticationFailed(
                "Geçersiz veya süresi dolmuş API anahtarı."
            ) from exc
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            raise PermissionDenied("Dış API salt okunurdur.")
        if (
            "/admin/" in request.path
            or "/auth/" in request.path
            or "/api-clients/" in request.path
        ):
            raise PermissionDenied("Bu API kapsamına erişim yok.")
        scope = request.path.split("/api/v1/")[-1].split("/")[0] + ":read"
        if scope not in client.scopes and "atlas:read" not in client.scopes:
            raise PermissionDenied("Token kapsamı bu kaynağı içermiyor.")
        client.user._api_client = client
        return client.user, client

    def authenticate_header(self, request):
        return "Bearer"
