from django.conf import settings
from .models import User
from .policy import is_system_admin


class TestIdentityMiddleware:
    """Synthetic environments only; impersonation always disables God bypass."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        real = request.user
        request.real_user = real
        if (
            real.is_authenticated
            and settings.ATLAS_ENV in ("test", "demo")
            and settings.ATLAS_TEST_GOD_MODE
            and is_system_admin(real)
        ):
            effective = request.session.get("atlas_effective_user")
            if effective:
                user = User.objects.filter(pk=effective, is_active=True).first()
                if user:
                    user._real_actor = real
                    user._god_mode = False
                    request.user = user
                else:
                    request.session.pop("atlas_effective_user", None)
            elif request.session.get("atlas_god_mode"):
                real._god_mode = True
        elif real.is_authenticated:
            request.session.pop("atlas_effective_user", None)
            request.session.pop("atlas_god_mode", None)
        return self.get_response(request)
