"""
Django settings for the NEONQ project (milestone M1).

Configuration is driven by environment variables so the same code runs in
local development (SQLite), Docker Compose (PostgreSQL) and production.
See .env.example for the supported variables.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from a local .env file if present (no-op in production).
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


# --- Core ---------------------------------------------------------------

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-secret-key-change-me")

DEBUG = env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# --- Applications -------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third-party
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.discord",
    # Project apps
    "accounts",
    "games",
    "recruitments",
    "applications",
    "notifications",
    "moderation",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    # Forces logged-in users through terms + profile setup (F-SAFE-06).
    "accounts.middleware.OnboardingMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "notifications.views.unread_count",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database -----------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(DATABASE_URL, conn_max_age=600),
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --- Authentication -----------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # admin (password) login
    "allauth.account.auth_backends.AuthenticationBackend",  # Discord OAuth
]

SITE_ID = 1

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "post_login"
LOGOUT_REDIRECT_URL = "home"

# --- django-allauth -----------------------------------------------------

# This is a social-only, passwordless service: users authenticate with
# Discord and have no local username/email/password. discord_id is the
# natural key, set in the adapter.
SOCIALACCOUNT_ONLY = True
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USER_MODEL_EMAIL_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_LOGIN_METHODS: set[str] = set()
# Non-empty so allauth does not fall back to its username/password defaults;
# the local signup form is never used under SOCIALACCOUNT_ONLY.
ACCOUNT_SIGNUP_FIELDS: list[str] = ["email"]
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_EMAIL_REQUIRED = False
SOCIALACCOUNT_ADAPTER = "accounts.adapters.DiscordSocialAccountAdapter"

# account.W001 (login-method/signup-field cross-check) does not apply to a
# social-only setup where the local account flow is disabled.
SILENCED_SYSTEM_CHECKS = ["account.W001"]

SOCIALACCOUNT_PROVIDERS = {
    "discord": {
        "SCOPE": ["identify"],
        "APPS": [
            {
                "client_id": os.environ.get("DISCORD_CLIENT_ID", ""),
                "secret": os.environ.get("DISCORD_CLIENT_SECRET", ""),
                "key": "",
            }
        ],
    }
}

# --- Cache --------------------------------------------------------------

# Redis in production (CACHE_URL), in-memory locally. Used to cache Riot API
# responses (N-13) and enforce the manual rank-refresh cooldown.
CACHE_URL = os.environ.get("CACHE_URL", "")
if CACHE_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": CACHE_URL}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --- Riot API (M3) ------------------------------------------------------

RIOT_API_KEY = os.environ.get("RIOT_API_KEY", "")
# Platform routing (rank endpoints) and regional routing (account endpoint).
RIOT_PLATFORM = os.environ.get("RIOT_PLATFORM", "jp1")
RIOT_REGIONAL = os.environ.get("RIOT_REGIONAL", "asia")
# How long Riot responses stay cached (seconds); default 24h (N-13, F-ACC-08).
RIOT_CACHE_TTL = int(os.environ.get("RIOT_CACHE_TTL", str(60 * 60 * 24)))
# Minimum interval between user-triggered rank refreshes (seconds).
RIOT_REFRESH_COOLDOWN = int(os.environ.get("RIOT_REFRESH_COOLDOWN", "600"))

# --- Internationalization ----------------------------------------------

LANGUAGE_CODE = "ja"
TIME_ZONE = "Asia/Tokyo"
USE_I18N = True
USE_TZ = True

# --- Static files -------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Manifest (hashed filenames for cache-busting) requires collectstatic to have
# built the manifest, so it is opt-in for production. Dev/test use plain
# compressed storage, which needs no manifest.
_staticfiles_backend = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
    if env_bool("DJANGO_MANIFEST_STATIC", False)
    else "whitenoise.storage.CompressedStaticFilesStorage"
)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": _staticfiles_backend},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Security (production) ----------------------------------------------

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

# --- Project-specific policy -------------------------------------------

# F-UNIQ-07: minimum Discord account age (in days) required to register.
MIN_DISCORD_ACCOUNT_AGE_DAYS = int(os.environ.get("MIN_DISCORD_ACCOUNT_AGE_DAYS", "90"))

# Local demo mode: passwordless dev login that bypasses Discord OAuth so the
# full flow can be tried without credentials. Defaults to DEBUG; never enable
# in real production.
DEV_LOGIN_ENABLED = env_bool("DEV_LOGIN_ENABLED", DEBUG)

# F-SAFE-08: simple NG-word filter for recruitment text. Comma-separated env override.
NG_WORDS = [
    w.strip()
    for w in os.environ.get("NG_WORDS", "死ね,殺す").split(",")
    if w.strip()
]

# --- Error monitoring (M7, N-12) ---------------------------------------

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
    )
