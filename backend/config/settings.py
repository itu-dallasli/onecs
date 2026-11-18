import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
_env_file = BASE_DIR.parent / ".env"
if _env_file.exists():
    import shlex

    for _line in _env_file.read_text().splitlines():
        if not _line.strip() or _line.lstrip().startswith("#") or "=" not in _line:
            continue
        _key, _value = _line.split("=", 1)
        if _key.strip() not in os.environ:
            _parts = shlex.split(_value, comments=True)
            os.environ[_key.strip()] = " ".join(_parts)


def env_bool(key, default="false"):
    return os.environ.get(key, default).lower() in ("true", "1", "yes")


SECRET_KEY = os.environ.get(
    "ATLAS_SECRET_KEY",
    os.environ.get(
        "DJANGO_SECRET_KEY", "atlas-local-development-only-change-before-deployment"
    ),
)
DEBUG = env_bool("DJANGO_DEBUG", "true")
ALLOWED_HOSTS = os.environ.get(
    "ALLOWED_HOSTS",
    os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver"),
).split(",")
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "core",
]
if (BASE_DIR / "administration" / "apps.py").exists():
    INSTALLED_APPS.append("administration")
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.TestIdentityMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ]
        },
    }
]
_db = urlparse(
    os.environ.get("DATABASE_URL", "postgresql://atlas@127.0.0.1:55432/atlas")
)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _db.path.lstrip("/"),
        "USER": _db.username or "atlas",
        "PASSWORD": _db.password or "",
        "HOST": _db.hostname or "127.0.0.1",
        "PORT": _db.port or 55432,
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 5},
    }
}
AUTH_USER_MODEL = "core.User"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
LANGUAGE_CODE = "tr-tr"
TIME_ZONE = "Europe/Istanbul"
USE_TZ = True
STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_TRUSTED_ORIGINS = os.environ.get(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:3100,http://127.0.0.1:3100,http://localhost:5173,http://127.0.0.1:5173,http://localhost:3001,http://127.0.0.1:3001,http://localhost:8000,http://127.0.0.1:8000",
).split(",")
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "core.authentication.ScopedJWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "core.exceptions.exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min"},
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Atlas API",
    "DESCRIPTION": "Rol ve kayıt kapsamı ile korunan Atlas yönetişim API. Dış JWT tüketicileri salt okunurdur.",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    "SERVE_AUTHENTICATION": ["rest_framework.authentication.SessionAuthentication"],
}
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "atlas@example.test")
ATLAS_ENV = os.environ.get("ATLAS_ENV", "development")
ATLAS_TEST_GOD_MODE = os.environ.get("ATLAS_TEST_GOD_MODE", "false").lower() == "true"
if ATLAS_TEST_GOD_MODE and ATLAS_ENV not in ("test", "demo"):
    raise RuntimeError("God Mode yalnız sentetik test/demo ortamında açılabilir.")
if not DEBUG and SECRET_KEY.startswith("atlas-local-"):
    raise RuntimeError("Üretim için DJANGO_SECRET_KEY zorunludur.")
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
JWT_ISSUER = "atlas"
JWT_AUDIENCE = "atlas-readonly-api"

SPECTACULAR_SETTINGS["PREPROCESSING_HOOKS"] = ["core.schema.canonical_endpoints"]
SESSION_COOKIE_NAME = "atlas_sessionid"
CSRF_COOKIE_NAME = "atlas_csrftoken"
