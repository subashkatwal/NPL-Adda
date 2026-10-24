"""
Django settings for NPL Adda.

All deployment-specific values come from environment variables (see .env.example).
"""
import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(f"Environment variable {name} is required.")
    return value


def env_bool(name, default=False):
    return str(env(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


# Core
SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
DEBUG = env_bool("DJANGO_DEBUG")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Public API URLs never end with a slash.
APPEND_SLASH = False

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    # Project
    "apps.common",
    "apps.accounts",
    "apps.teams",
    "apps.matches",
    "apps.fanengagement",
    "apps.content",
    "apps.memelab",
    "apps.ai_agents",
    "apps.moderation",
    "apps.backoffice",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
# Connection pooling (psycopg pool, built into Django 5.1+) reuses connections across requests.
# Size it so (gunicorn workers x DB_POOL_MAX_SIZE) stays below Postgres max_connections; put
# PgBouncer in front when running many app instances. DB_POOL_MAX_SIZE=0 disables pooling.
DB_POOL_MAX_SIZE = int(env("DB_POOL_MAX_SIZE", "10"))
_db_options = {
    # Abort runaway queries instead of letting them hold connections and locks.
    "options": f"-c statement_timeout={int(env('DB_STATEMENT_TIMEOUT_MS', '15000'))}",
}
# Hosted Postgres (Neon, Supabase) requires TLS: set POSTGRES_SSLMODE=require.
if env("POSTGRES_SSLMODE"):
    _db_options["sslmode"] = env("POSTGRES_SSLMODE")
if DB_POOL_MAX_SIZE > 0:
    _db_options["pool"] = {"min_size": int(env("DB_POOL_MIN_SIZE", "2")), "max_size": DB_POOL_MAX_SIZE, "timeout": 10}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", required=True),
        "USER": env("POSTGRES_USER", required=True),
        "PASSWORD": env("POSTGRES_PASSWORD", required=True),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 0 if DB_POOL_MAX_SIZE > 0 else 60,  # persistent connections and pooling are exclusive
        "CONN_HEALTH_CHECKS": DB_POOL_MAX_SIZE == 0,
        "OPTIONS": _db_options,
    }
}

# Cache (Redis): sessions-independent cache for expensive public reads such as leaderboards.
# REDIS_URL=none falls back to a per-process memory cache (single-instance free hosting without Redis).
_redis_url = env("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": _redis_url,
        "KEY_PREFIX": "npl_adda",
        "TIMEOUT": 300,
    }
    if _redis_url.lower() != "none"
    else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "TIMEOUT": 300}
}
LEADERBOARD_CACHE_SECONDS = int(env("LEADERBOARD_CACHE_SECONDS", "60"))

# Auth
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kathmandu"
USE_I18N = True
USE_TZ = True

# Static & media
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# Let Django serve MEDIA_ROOT when DEBUG is off (no separate web server or object storage on free hosting).
SERVE_MEDIA = env_bool("DJANGO_SERVE_MEDIA", False)
# Cloudinary keeps uploaded and rendered images when all three are set (free hosting disks are ephemeral).
CLOUDINARY_CLOUD_NAME = env("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = env("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = env("CLOUDINARY_API_SECRET", "")
_use_cloudinary = all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET])
STORAGES = {
    "default": {"BACKEND": "apps.common.storage.CloudinaryMediaStorage" if _use_cloudinary
                else "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "apps.accounts.authentication.GuestSessionAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "meme_generation": env("MEME_GENERATION_RATE", "20/hour"),
        "meme_render": env("MEME_RENDER_RATE", "60/min"),
        "meme_upload": env("MEME_UPLOAD_RATE", "20/hour"),
        "meme_engage": env("MEME_ENGAGE_RATE", "60/min"),
        "meme_comment": env("MEME_COMMENT_RATE", "10/min"),
        "avatar_upload": env("AVATAR_UPLOAD_RATE", "10/hour"),
        "auth": env("AUTH_RATE", "10/min"),
        "auth_register": env("AUTH_REGISTER_RATE", "10/hour"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_TOKEN_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("JWT_REFRESH_TOKEN_DAYS", "7"))),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "NPL Adda API",
    "DESCRIPTION": "Independent digital fan community for Nepali cricket supporters.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "SeasonStatusEnum": "apps.matches.models.Season.Status",
        "MatchStatusEnum": "apps.matches.models.Match.Status",
        "PollStatusEnum": "apps.fanengagement.models.Poll.Status",
        "PostStatusEnum": "apps.content.models.CommunityPost.Status",
        "MemeRequestStatusEnum": "apps.memelab.models.MemeGenerationRequest.Status",
        "MemeDraftStatusEnum": "apps.memelab.models.MemeDraft.Status",
        "AgentRunStatusEnum": "apps.ai_agents.models.AgentRun.Status",
        "ToolCallStatusEnum": "apps.ai_agents.models.AgentToolCall.Status",
        "ReportStatusEnum": "apps.moderation.models.ModerationReport.Status",
    },
}

# Fan engagement
GUEST_SESSION_TTL_DAYS = int(env("GUEST_SESSION_TTL_DAYS", "30"))
PREDICTION_LOCK_MINUTES = int(env("PREDICTION_LOCK_MINUTES", "0"))
BALLS_PER_INNINGS = 120  # NPL is T20

# MEME Zone captions: "mock" is the deterministic offline generator. The external AI service
# (Prompt 4) will register its own provider in apps/memelab/captioning.py.
MEME_CAPTION_PROVIDER = env("MEME_CAPTION_PROVIDER", "auto")  # auto = gemini when a key is set, else mock

# Gemini (Google AI Studio) caption provider. The key stays on the server; the browser never sees it.
GEMINI_API_KEY = env("GOOGLE_GEMINI_API_KEY", "") or env("GEMINI_API_KEY", "")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-3.8-flash")
# Tried in order when the main model is busy, retired or times out (comma-separated).
GEMINI_FALLBACK_MODEL = env("GEMINI_FALLBACK_MODEL", "gemini-3-flash-preview,gemini-flash-latest")
GEMINI_TIMEOUT_SECONDS = float(env("GEMINI_TIMEOUT_SECONDS", "15"))

# Meme Zone
# Fans publish freely: memes and posts go live at once (text filters still apply, everything stays reportable,
# staff can hide/remove). Set either to True to hold new content for approval instead.
MEME_REQUIRE_REVIEW = env_bool("MEME_REQUIRE_REVIEW", False)
POST_REQUIRE_REVIEW = env_bool("POST_REQUIRE_REVIEW", False)
MEME_UPLOAD_MAX_BYTES = int(env("MEME_UPLOAD_MAX_BYTES", str(5 * 1024 * 1024)))
MEME_UPLOAD_MAX_PIXELS = int(env("MEME_UPLOAD_MAX_PIXELS", str(24_000_000)))  # decompression-bomb guard
MEME_BLOCKED_TERMS = env_list("MEME_BLOCKED_TERMS")  # extra words to refuse, on top of the built-in list
DATA_UPLOAD_MAX_MEMORY_SIZE = MEME_UPLOAD_MAX_BYTES + 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MEME_UPLOAD_MAX_BYTES + 1024 * 1024

# CORS (credentials allowed so the SPA's session cookie works if it calls the API cross-origin)
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# Browser sessions: HttpOnly session cookie (JS can't read it) + CSRF token cookie (JS must read it).
SESSION_COOKIE_AGE = int(env("SESSION_COOKIE_AGE_SECONDS", str(14 * 24 * 3600)))
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False

# Google sign-in. Only the public OAuth client ID is needed to verify ID tokens; no secret is used.
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", "")

# Production hardening (HTTPS assumed when DEBUG is off)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(env("DJANGO_SECURE_HSTS_SECONDS", "3600"))
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
