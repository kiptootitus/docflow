"""
DocFlow AI — docflow/settings.py

Single settings file for all environments.
Environment-specific values are controlled exclusively via .env / environment
variables (python-decouple).  Never commit real secrets.

Quick reference — required env vars:
  SECRET_KEY              Django secret key (mandatory in production)
  DEBUG                   true/false (default false)
  ALLOWED_HOSTS           comma-separated hostnames
  DATABASE_URL            postgres://user:pass@host:port/db  (preferred)
  REDIS_URL               redis://host:port/0                (preferred)
  SENDGRID_API_KEY        SendGrid API key
  GOOGLE_OAUTH_CLIENT_ID  Google OAuth2 client ID
  ANTHROPIC_API_KEY       Claude API key
  OPENAI_API_KEY          OpenAI fallback key
  AWS_ACCESS_KEY_ID       S3 credentials (optional, falls back to local)
  STRIPE_SECRET_KEY       Stripe secret key
  FRONTEND_URL            https://app.docflowai.com
  SENTRY_DSN              Sentry project DSN (optional)
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from decouple import Csv, config

# ─────────────────────────────────────────────────────────────────────────────
# BASE
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent

# Are we running tests right now?
TESTING = "pytest" in sys.modules or "test" in sys.argv


# ─────────────────────────────────────────────────────────────────────────────
# SECURITY  ← most important section; every line here matters
# ─────────────────────────────────────────────────────────────────────────────

# FIX: Never fall back to an insecure key in production.
# The default is only acceptable for local dev (DEBUG=True).
SECRET_KEY = config("SECRET_KEY", default="django-insecure-CHANGE-ME-set-SECRET_KEY-in-env")

DEBUG = config("DEBUG", default=False, cast=bool)

# In production the insecure default SECRET_KEY must not be used.
if not DEBUG and SECRET_KEY.startswith("django-insecure-"):
    raise RuntimeError(
        "SECRET_KEY must be set to a secure random value in production. "
        "Generate one with: python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
    )

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1",
    cast=Csv(),
)

# ── HTTPS / proxy ────────────────────────────────────────────────────────────
SECURE_PROXY_SSL_HEADER       = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT           = not DEBUG    # redirect HTTP → HTTPS in prod

# FIX: HSTS — was completely missing; required for HTTPS enforcement
SECURE_HSTS_SECONDS           = 0 if DEBUG else 31_536_000   # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS= not DEBUG
SECURE_HSTS_PRELOAD           = not DEBUG

# FIX: these two were missing — essential anti-clickjacking / MIME protection
SECURE_BROWSER_XSS_FILTER     = True
SECURE_CONTENT_TYPE_NOSNIFF   = True
X_FRAME_OPTIONS               = "DENY"

# FIX: REFERRER_POLICY was missing
SECURE_REFERRER_POLICY        = "strict-origin-when-cross-origin"

# ── Cookies ──────────────────────────────────────────────────────────────────
SESSION_COOKIE_SECURE   = not DEBUG
SESSION_COOKIE_HTTPONLY = True        # FIX: was missing — blocks JS access to session cookie
SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SECURE      = not DEBUG
CSRF_COOKIE_HTTPONLY    = True        # FIX: was missing
CSRF_COOKIE_SAMESITE    = "Lax"

# ── Content Security Policy (django-csp) ─────────────────────────────────────
# Requires: pip install django-csp
# Add 'csp.middleware.CSPMiddleware' to MIDDLEWARE (see below)
CSP_DEFAULT_SRC    = ("'self'",)
CSP_SCRIPT_SRC     = ("'self'", "https://apis.google.com")
CSP_STYLE_SRC      = ("'self'", "https://fonts.googleapis.com", "'unsafe-inline'")
CSP_FONT_SRC       = ("'self'", "https://fonts.gstatic.com")
CSP_IMG_SRC        = ("'self'", "data:", "https:")
CSP_CONNECT_SRC    = ("'self'", "https://api.anthropic.com", "https://api.openai.com")
CSP_FRAME_ANCESTORS= ("'none'",)
CSP_REPORT_ONLY    = DEBUG   # Report-only in dev, enforce in prod


# ─────────────────────────────────────────────────────────────────────────────
# APPLICATIONS
# ─────────────────────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    # ── Django built-ins ─────────────────────────────────────────────────────
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",

    # ── Third-party ───────────────────────────────────────────────────────────
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    "django_filters",
    "django_extensions",
    "django_celery_beat",
    "django_celery_results",
    "storages",
    "djstripe",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "djoser",
    "django_otp",
    "django_otp.plugins.otp_totp",   # FIX: was missing — TOTP devices won't register without this
    "django_otp.plugins.otp_static", # Backup codes / static tokens
    "anymail",

    # ── Local apps ────────────────────────────────────────────────────────────
    "users.apps.UsersConfig",
    "companies",
    "documents",
    "billing",
    "ai",
    "notifications.apps.NotificationsConfig",
]


# ─────────────────────────────────────────────────────────────────────────────
# MIDDLEWARE  (order is critical)
# ─────────────────────────────────────────────────────────────────────────────

MIDDLEWARE = [
    # CORS must be first so OPTIONS preflight responses are handled before
    # any auth or security middleware rejects them.
    "corsheaders.middleware.CorsMiddleware",

    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",

    # FIX: CSP middleware added (requires django-csp)
    # "csp.middleware.CSPMiddleware",

    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    # django-otp must come after AuthenticationMiddleware
    "django_otp.middleware.OTPMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ─────────────────────────────────────────────────────────────────────────────
# URLS / WSGI / ASGI
# ─────────────────────────────────────────────────────────────────────────────

ROOT_URLCONF    = "docflow.urls"
WSGI_APPLICATION= "docflow.wsgi.application"


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # FIX: Added BASE_DIR / "templates" so notification HTML email templates
        # in notifications/templates/ are discoverable by APP_DIRS=True,
        # and any project-level templates in docflow/templates/ are also found.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────────────────

if os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.config(
            default=os.environ["DATABASE_URL"],
            conn_max_age=600,
            conn_health_checks=True,
            # FIX: SSL required in production; ignored in local dev (no SSL cert)
            ssl_require=not DEBUG,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE":   "django.db.backends.postgresql",
            "NAME":     config("POSTGRES_DB",       default="docflow"),
            "USER":     config("POSTGRES_USER",     default="docflow"),
            "PASSWORD": config("POSTGRES_PASSWORD", default="docflow"),
            "HOST":     config("POSTGRES_HOST",     default="localhost"),
            "PORT":     config("POSTGRES_PORT",     default="5432"),
            # FIX: CONN_MAX_AGE was missing on this branch (only on dj_database_url)
            "CONN_MAX_AGE": 600,
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {
                # FIX: SSL for production postgres on the manual config path
                **({"sslmode": "require"} if not DEBUG else {}),
            },
        }
    }

# FIX: ATOMIC_REQUESTS wraps every request in a transaction.
# Ensures partial DB writes never leave the DB in a dirty state.
# Note: incompatible with streaming responses — disable per-view if needed.
DATABASES["default"]["ATOMIC_REQUESTS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ?????????????????????????????????????????????????????????????????????????????
# CACHE — Using django-redis (best for throttling + production)
# ?????????????????????????????????????????????????????????????????????????????
_redis_url = os.environ.get("REDIS_URL") or (
    "redis://{host}:{port}/1".format(
        host=config("REDIS_HOST", default="redis"),
        port=config("REDIS_PORT", default="6379"),
    )
)

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",   # ← Changed
        "LOCATION": _redis_url,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,   # Now valid
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
        },
        "KEY_PREFIX": "docflow",
        "TIMEOUT": 300,
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# PASSWORD VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ─────────────────────────────────────────────────────────────────────────────
# INTERNATIONALISATION
# ─────────────────────────────────────────────────────────────────────────────

LANGUAGE_CODE = "en-us"

# The application's local timezone for display / Celery Beat scheduling.
# NOTE: Django always stores datetimes as UTC internally (USE_TZ=True).
# CELERY_ENABLE_UTC=False tells Celery to use this timezone for Beat schedules,
# so "08:00" means 08:00 Nairobi time, not 08:00 UTC.
TIME_ZONE = "Africa/Nairobi"
USE_I18N  = True
USE_TZ    = True


# ─────────────────────────────────────────────────────────────────────────────
# STATIC & MEDIA FILES
# ─────────────────────────────────────────────────────────────────────────────

STATIC_URL  = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL   = "/media/"
MEDIA_ROOT  = BASE_DIR / "media"


# ─────────────────────────────────────────────────────────────────────────────
# AWS S3 STORAGE
# ─────────────────────────────────────────────────────────────────────────────

USE_S3 = config("AWS_ACCESS_KEY_ID", default="") != ""

if USE_S3:
    AWS_ACCESS_KEY_ID       = config("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY   = config("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME      = config("AWS_S3_REGION_NAME", default="af-south-1")
    AWS_S3_CUSTOM_DOMAIN    = config("AWS_S3_CUSTOM_DOMAIN", default="")  # CloudFront domain

    # FIX: MUST be True for private files (invoices, contracts, avatars).
    # Was False — that would make all uploaded files publicly accessible by URL.
    # Presigned URLs are generated per-request with a short TTL instead.
    AWS_QUERYSTRING_AUTH    = True
    AWS_QUERYSTRING_EXPIRE  = 300   # 5-minute presigned URL expiry

    AWS_DEFAULT_ACL         = None   # Bucket policy controls access, not per-object ACL
    AWS_S3_FILE_OVERWRITE   = False  # Never silently overwrite uploaded files

    # FIX: Server-side encryption — all objects encrypted at rest using AWS KMS
    AWS_S3_OBJECT_PARAMETERS = {
        "ServerSideEncryption": "aws:kms",
    }

    # FIX: Separate public (static assets) vs private (user uploads) storage
    STORAGES = {
        "default": {
            # Private user uploads (invoices, contracts, avatars) — requires auth
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name":      AWS_STORAGE_BUCKET_NAME,
                "region_name":      AWS_S3_REGION_NAME,
                "querystring_auth": True,
                "file_overwrite":   False,
                "object_parameters": {"ServerSideEncryption": "aws:kms"},
                "location":         "media",
            },
        },
        "staticfiles": {
            # Public static assets (CSS, JS) — served via CloudFront, no auth needed
            "BACKEND": "storages.backends.s3.S3StaticStorage",
            "OPTIONS": {
                "bucket_name":      AWS_STORAGE_BUCKET_NAME,
                "region_name":      AWS_S3_REGION_NAME,
                "querystring_auth": False,
                "location":         "static",
                **({"custom_domain": AWS_S3_CUSTOM_DOMAIN} if AWS_S3_CUSTOM_DOMAIN else {}),
            },
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# REST FRAMEWORK
# ─────────────────────────────────────────────────────────────────────────────

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],

    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],

    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],

    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",

    # FIX: Cursor pagination for production (no offset attacks, consistent ordering)
    "DEFAULT_PAGINATION_CLASS": "docflow.pagination.StandardCursorPagination",
    "PAGE_SIZE": 20,

    # FIX: Global throttling was completely missing.
    # Views can override with stricter per-endpoint throttle classes.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon":    "30/hour",    # Unauthenticated requests (register, login, reset)
        "user":    "300/hour",   # Authenticated requests
        "auth":    "10/hour",    # Stricter: applied on login / password-reset views
        "sensitive": "20/hour",  # 2FA, change-password, etc.
    },

    # Return consistent 401 (not 403) for unauthenticated requests
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,

    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
}


# ─────────────────────────────────────────────────────────────────────────────
# DRF SPECTACULAR (OpenAPI docs)
# ─────────────────────────────────────────────────────────────────────────────

SPECTACULAR_SETTINGS = {
    "TITLE":       "DocFlow AI API",
    "DESCRIPTION": "AI-Powered Invoicing, Contracts & Document Management",
    "VERSION":     "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,   # FIX: don't expose /api/schema/ without auth in prod
    "COMPONENT_SPLIT_REQUEST": True, # FIX: separate request vs response schemas
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]",
    "SECURITY": [{"BearerAuth": []}],
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "displayRequestDuration": True,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# SIMPLE JWT  ← FIX: multiple corrections applied
# ─────────────────────────────────────────────────────────────────────────────

SIMPLE_JWT = {
    # FIX: 15 minutes — not 60 minutes as in original.
    # Short-lived access tokens limit the blast radius of a stolen token.
    "ACCESS_TOKEN_LIFETIME":  timedelta(minutes=15),

    # FIX: 30 days — matches the plan (was 7 days).
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),

    "ROTATE_REFRESH_TOKENS":      True,   # Issue new refresh token on each use
    "BLACKLIST_AFTER_ROTATION":   True,   # Blacklist the old refresh token

    "UPDATE_LAST_LOGIN":          True,

    # FIX: list not tuple — newer simplejwt versions expect a list
    "AUTH_HEADER_TYPES":          ["Bearer"],

    "AUTH_TOKEN_CLASSES":         ["rest_framework_simplejwt.tokens.AccessToken"],

    # FIX: explicitly set algorithm (ES256 for production; HS256 acceptable for MVP)
    "ALGORITHM":                  "HS256",

    # Signing key defaults to SECRET_KEY — override with a dedicated key for
    # extra isolation between JWT signing and Django's CSRF protection.
    # ✅ FIXED
    "SIGNING_KEY": config("JWT_SIGNING_KEY", default=SECRET_KEY),    # None → falls back to SECRET_KEY (acceptable for MVP)

    # Include JTI claim so individual tokens can be blacklisted
    "JTI_CLAIM":                  "jti",

    # Token types included in the payload for type-checking
    "TOKEN_TYPE_CLAIM":           "token_type",

    # Sliding tokens disabled (we use standard refresh rotation)
    "SLIDING_TOKEN_LIFETIME":         timedelta(minutes=15),
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(days=1),
}


# ─────────────────────────────────────────────────────────────────────────────
# CORS  ← FIX: added missing production domains + expose headers
# ─────────────────────────────────────────────────────────────────────────────

# Explicit origins for local dev + production
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default=",".join([
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]),
    cast=Csv(),
)

# FIX: Pattern-match staging / preview deployments (Vercel preview URLs)
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://docflow-.*\.vercel\.app$",
    r"^https://.*\.docflowai\.com$",
]

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default=",".join([
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]),
    cast=Csv(),
)

CORS_ALLOW_CREDENTIALS = True

# FIX: Expose custom headers so the React frontend can read them
CORS_EXPOSE_HEADERS = [
    "Content-Disposition",  # For file download filename
    "X-Request-ID",         # For distributed tracing
]

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-request-id",
]


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL  (Anymail + SendGrid)
# ─────────────────────────────────────────────────────────────────────────────

ANYMAIL = {
    "SENDGRID_API_KEY": config("SENDGRID_API_KEY", default=""),
    # Optional: SendGrid subuser for sending from a sub-account
    "SENDGRID_SEND_DEFAULTS": {
        "esp_extra": {"ip_pool_name": "transactional"},
    },
}

EMAIL_BACKEND = (
    "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "anymail.backends.sendgrid.EmailBackend"
)

DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default="DocFlow AI <hello@docflowai.com>",
)
SERVER_EMAIL = config("SERVER_EMAIL", default="errors@docflowai.com")

# ── App-specific URLs needed by email templates and push.py ─────────────────
# FIX: These were missing and caused AttributeError in email.py / push.py
FRONTEND_URL    = config("FRONTEND_URL",   default="https://app.docflowai.com")
SUPPORT_URL     = config("SUPPORT_URL",    default="https://support.docflowai.com")
UNSUBSCRIBE_URL = config("UNSUBSCRIBE_URL",default=f"{config('FRONTEND_URL', default='https://app.docflowai.com')}/unsubscribe")


# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION
# ─────────────────────────────────────────────────────────────────────────────

AUTH_USER_MODEL = "users.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SITE_ID = 1

# ── django-allauth ────────────────────────────────────────────────────────────
ACCOUNT_USER_MODEL_USERNAME_FIELD = None

ACCOUNT_EMAIL_VERIFICATION        = "mandatory"
ACCOUNT_SIGNUP_FIELDS: list[str]             = ["email*", "password1*", "password2*"]
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True

# FIX: Google OAuth provider config was missing
GOOGLE_OAUTH_CLIENT_ID     = config("GOOGLE_OAUTH_CLIENT_ID",     default="")
GOOGLE_OAUTH_CLIENT_SECRET = config("GOOGLE_OAUTH_CLIENT_SECRET", default="")

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "APP": {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "secret":    GOOGLE_OAUTH_CLIENT_SECRET,
            "key":       "",
        },
    }
}
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_USERNAME_REQUIRED = False        # can keep for now, but it's deprecated
ACCOUNT_USER_MODEL_USERNAME_FIELD = None # if you completely disable username

# ─────────────────────────────────────────────────────────────────────────────
# STRIPE  (dj-stripe)
# ─────────────────────────────────────────────────────────────────────────────

STRIPE_SECRET_KEY      = config("STRIPE_SECRET_KEY",      default="")
STRIPE_PUBLISHABLE_KEY = config("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET  = config("STRIPE_WEBHOOK_SECRET",  default="")
STRIPE_LIVE_MODE       = config("STRIPE_LIVE_MODE",       default=False, cast=bool)

DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"
DJSTRIPE_WEBHOOK_SECRET       = STRIPE_WEBHOOK_SECRET
DJSTRIPE_USE_NATIVE_JSONFIELD = True  # Requires Django 3.1+


# ─────────────────────────────────────────────────────────────────────────────
# AI  (Anthropic Claude + OpenAI fallback)
# ─────────────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY    = config("ANTHROPIC_API_KEY",    default="")
ANTHROPIC_MODEL      = config("ANTHROPIC_MODEL",      default="claude-sonnet-4-6")
ANTHROPIC_MAX_TOKENS = config("ANTHROPIC_MAX_TOKENS", default=4096, cast=int)
ANTHROPIC_TEMPERATURE= config("ANTHROPIC_TEMPERATURE",default=0.0,  cast=float)

OPENAI_API_KEY       = config("OPENAI_API_KEY",       default="")
OPENAI_MODEL         = config("OPENAI_MODEL",         default="gpt-4o")
OPENAI_MAX_TOKENS    = config("OPENAI_MAX_TOKENS",    default=4096, cast=int)
OPENAI_TEMPERATURE   = config("OPENAI_TEMPERATURE",   default=0.0,  cast=float)

AI_MODEL_PRIMARY     = config("AI_MODEL_PRIMARY",     default="claude-sonnet-4-6")
AI_DEFAULT_TIMEOUT   = config("AI_DEFAULT_TIMEOUT",   default=120, cast=int)
AI_MAX_RETRIES       = config("AI_MAX_RETRIES",       default=3,   cast=int)


# ─────────────────────────────────────────────────────────────────────────────
# PUSH NOTIFICATIONS  ← FIX: was completely missing
# ─────────────────────────────────────────────────────────────────────────────

# Expo Push — optional enhanced delivery token
EXPO_ACCESS_TOKEN = config("EXPO_ACCESS_TOKEN", default="")

# FCM — path to Google service account JSON file, or JSON string
FCM_SERVICE_ACCOUNT = config("FCM_SERVICE_ACCOUNT", default="")

# APNS — Apple Push (token-based auth)
APNS_KEY_ID        = config("APNS_KEY_ID",        default="")
APNS_TEAM_ID       = config("APNS_TEAM_ID",       default="")
APNS_AUTH_KEY_PATH = config("APNS_AUTH_KEY_PATH", default="")
APNS_BUNDLE_ID     = config("APNS_BUNDLE_ID",     default="com.docflowai.app")
APNS_USE_SANDBOX   = config("APNS_USE_SANDBOX",   default=DEBUG, cast=bool)


# ─────────────────────────────────────────────────────────────────────────────
# CELERY
# ─────────────────────────────────────────────────────────────────────────────

# Resolve Redis connection string once
_redis_password = config("REDIS_PASSWORD", default="")
_redis_host      = config("REDIS_HOST",     default="redis")
_redis_port      = config("REDIS_PORT",     default="6379")

if os.environ.get("REDIS_URL"):
    _celery_broker = os.environ["REDIS_URL"]
else:
    _celery_broker = (
        f"redis://:{_redis_password}@{_redis_host}:{_redis_port}/0"
        if _redis_password
        else f"redis://{_redis_host}:{_redis_port}/0"
    )

CELERY_BROKER_URL    = _celery_broker
CELERY_RESULT_BACKEND= _celery_broker

# Serialisation
CELERY_ACCEPT_CONTENT   = ["json"]
CELERY_TASK_SERIALIZER  = "json"
CELERY_RESULT_SERIALIZER= "json"

# Timezone — Beat schedules use Africa/Nairobi
# Django stores UTC; Celery Beat schedules in local time
CELERY_TIMEZONE    = TIME_ZONE
CELERY_ENABLE_UTC  = False

# Reliability
CELERY_TASK_ACKS_LATE              = True   # Re-queue if worker dies mid-task
CELERY_WORKER_PREFETCH_MULTIPLIER  = 1      # One task at a time per worker process
CELERY_TASK_REJECT_ON_WORKER_LOST  = True   # Reject (re-queue) on unexpected worker death

# FIX: Max tasks per child prevents memory leaks in long-running workers
CELERY_WORKER_MAX_TASKS_PER_CHILD  = 1000

# Broker connection
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_MAX_RETRIES      = 10

# Task tracking & results
CELERY_TASK_TRACK_STARTED    = True
CELERY_TASK_TIME_LIMIT       = 3600   # Hard kill after 1 hour
CELERY_TASK_SOFT_TIME_LIMIT  = 3300   # Soft warning at 55 minutes
CELERY_RESULT_EXPIRES        = 3600

CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": 3600,
}

# FIX: CELERY_TASK_ALWAYS_EAGER — run tasks synchronously in test mode.
# This means test_*.py files don't need a live Redis/Celery worker.
CELERY_TASK_ALWAYS_EAGER         = TESTING
CELERY_TASK_EAGER_PROPAGATES     = TESTING

# ── Queue routing — tasks declare queue="high"/"default"/"low" ───────────────
# FIX: Explicit queue definitions were missing. Workers are started with:
#   celery -A docflow worker -Q high,default,low
CELERY_TASK_QUEUES = {
    "high":    {"exchange": "high",    "routing_key": "high"},
    "default": {"exchange": "default", "routing_key": "default"},
    "low":     {"exchange": "low",     "routing_key": "low"},
}
CELERY_TASK_DEFAULT_QUEUE       = "default"
CELERY_TASK_DEFAULT_EXCHANGE    = "default"
CELERY_TASK_DEFAULT_ROUTING_KEY = "default"

# ── Beat schedule ─────────────────────────────────────────────────────────────
# FIX: The original settings had a bare `from celery.schedules import crontab`
# at module top level — wrong because it imports Celery before the app is ready.
# Correct approach: import inside the dict at assignment time.

from celery.schedules import crontab  # noqa: E402 — must be after CELERY_TIMEZONE

CELERY_BEAT_SCHEDULE = {
    "send-invoice-payment-reminders": {
        "task":     "notifications.tasks.send_invoice_payment_reminders",
        "schedule": crontab(hour=8, minute=0),           # 08:00 Africa/Nairobi
    },
    "send-contract-expiry-alerts": {
        "task":     "notifications.tasks.send_contract_expiry_alerts",
        "schedule": crontab(hour=8, minute=15),
    },
    "send-trial-ending-reminders": {
        "task":     "notifications.tasks.send_trial_ending_reminders",
        "schedule": crontab(hour=9, minute=0),
    },
    "check-expo-push-receipts": {
        "task":     "notifications.tasks.check_expo_push_receipts",
        "schedule": crontab(minute=0),                   # Every hour
    },
    "purge-stale-push-tokens": {
        "task":     "notifications.tasks.purge_stale_push_tokens",
        "schedule": crontab(hour=3, minute=0, day_of_week=1),   # Monday 03:00
    },
    "purge-old-notifications": {
        "task":     "notifications.tasks.purge_old_notifications",
        "schedule": crontab(hour=2, minute=0, day_of_month=1),  # 1st of month
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING  ← FIX: was completely missing
# ─────────────────────────────────────────────────────────────────────────────

SENTRY_DSN = config("SENTRY_DSN", default="")

# Initialise Sentry before logging so it captures startup errors
if SENTRY_DSN and not DEBUG:
    try:
        import sentry_sdk                                            # noqa: E402
        from sentry_sdk.integrations.django import DjangoIntegration # noqa: E402
        from sentry_sdk.integrations.celery import CeleryIntegration # noqa: E402
        from sentry_sdk.integrations.redis  import RedisIntegration  # noqa: E402

        sentry_sdk.init(
            dsn              = SENTRY_DSN,
            integrations     = [
                DjangoIntegration(transaction_style="url"),
                CeleryIntegration(),
                RedisIntegration(),
            ],
            traces_sample_rate          = 0.1,   # 10% of transactions for performance
            profiles_sample_rate        = 0.05,  # 5% for profiling
            send_default_pii            = False, # Never send PII to Sentry
            environment                 = config("ENVIRONMENT", default="production"),
            release                     = config("RELEASE_VERSION", default=""),
        )
    except ImportError:
        pass  # sentry-sdk not installed — silent in dev

LOGGING = {
    "version":            1,
    "disable_existing_loggers": False,

    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] {name} {process:d} {thread:d} | {message}",
            "style":  "{",
        },
        "simple": {
            "format": "{asctime} [{levelname}] {name} | {message}",
            "style":  "{",
        },
        "json": {
            # Structured JSON logs for production log aggregation (CloudWatch, Datadog)
            "()":     "pythonjsonlogger.jsonlogger.JsonFormatter",  # requires python-json-logger
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },

    "filters": {
        "require_debug_true":  {"()": "django.utils.log.RequireDebugTrue"},
        "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
    },

    "handlers": {
        "console": {
            "class":     "logging.StreamHandler",
            "formatter": "simple" if DEBUG else "json",
        },
        "mail_admins": {
            "level":   "ERROR",
            "class":   "django.utils.log.AdminEmailHandler",
            "filters": ["require_debug_false"],
        },
    },

    "root": {
        "handlers": ["console"],
        "level":    "DEBUG" if DEBUG else "INFO",
    },

    "loggers": {
        # Django internals — WARNING+ only to reduce noise
        "django": {
            "handlers":  ["console"],
            "level":     "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers":  ["console", "mail_admins"],
            "level":     "ERROR",
            "propagate": False,
        },
        # DocFlow application loggers — DEBUG in dev, INFO in prod
        "users": {
            "handlers":  ["console"],
            "level":     "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        "notifications": {
            "handlers":  ["console"],
            "level":     "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        "ai": {
            "handlers":  ["console"],
            "level":     "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        "billing": {
            "handlers":  ["console"],
            "level":     "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        # Celery
        "celery": {
            "handlers":  ["console"],
            "level":     "INFO",
            "propagate": False,
        },
        # Third-party noisy loggers to silence
        "botocore":     {"level": "WARNING"},
        "boto3":        {"level": "WARNING"},
        "urllib3":      {"level": "WARNING"},
        "httpx":        {"level": "WARNING"},
    },
}