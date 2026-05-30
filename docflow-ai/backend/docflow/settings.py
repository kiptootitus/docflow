"""
DocFlow AI — docflow/settings.py

Single settings file for all environments.
Environment-specific values are controlled exclusively via .env
"""

import os
import sys
import django
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────────────────────
# BASE
# ─────────────────────────────────────────────────────────────────────────────

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load the environment variables explicitly from your root .env file
load_dotenv(os.path.join(BASE_DIR, ".env"))
TESTING = "pytest" in sys.modules or "test" in sys.argv

# ─────────────────────────────────────────────────────────────────────────────
# SECURITY
# ─────────────────────────────────────────────────────────────────────────────

# Force HTTP for development (prevents HTTPS warnings)
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

SECRET_KEY = os.getenv("SECRET_KEY", default="gc4^32ku%i3lqu-&hq*e%rokwj8j1%8e+apil(sq=!7#1scf*m")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Allow all hosts during development
ALLOWED_HOSTS = ['*', 'localhost', '127.0.0.1', '0.0.0.0']

# For development - disable HTTPS redirect
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = None
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Disable HTTPS enforcement
USE_X_FORWARDED_HOST = False
USE_X_FORWARDED_PORT = False
# ─────────────────────────────────────────────────────────────────────────────
# APPLICATIONS
# ─────────────────────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.postgres",

    # Third-party
    "rest_framework",
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
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "anymail",

    # Local apps
    "users.apps.UsersConfig",
    "companies.apps.CompaniesConfig",
    "documents.apps.DocumentsConfig",
    "ai.apps.AiConfig",
    "notifications.apps.NotificationsConfig",
    "analytics.apps.AnalyticsConfig",
    "intergrations.apps.IntergrationsConfig",
]

# ─────────────────────────────────────────────────────────────────────────────
# MIDDLEWARE
# ─────────────────────────────────────────────────────────────────────────────

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ─────────────────────────────────────────────────────────────────────────────
# URLS & TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

ROOT_URLCONF = "docflow.urls"
WSGI_APPLICATION = "docflow.wsgi.application"

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
            ],
        },
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────────────────

DATABASES = {
    "default": {
        "ENGINE":   "django.db.backends.postgresql",
        "NAME":     os.getenv("POSTGRES_DB",       default="docflow"),
        "USER":     os.getenv("POSTGRES_USER",     default="docflow"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", default="docflow254"),
        "HOST":     os.getenv("POSTGRES_HOST",     default="db"),
        "PORT":     os.getenv("POSTGRES_PORT",     default="5432"),
    }
}

DATABASES["default"]["ATOMIC_REQUESTS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─────────────────────────────────────────────────────────────────────────────
# CACHE (Redis)
# ─────────────────────────────────────────────────────────────────────────────

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
        },
        "KEY_PREFIX": "docflow",
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# STATIC & MEDIA
# ─────────────────────────────────────────────────────────────────────────────

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

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
    "DEFAULT_PAGINATION_CLASS": "docflow.pagination.StandardCursorPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/hour",
        "user": "300/hour",
        "auth": "10/hour",
        "sensitive": "20/hour",
    },
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,
}

# ─────────────────────────────────────────────────────────────────────────────
# DRF SPECTACULAR
# ─────────────────────────────────────────────────────────────────────────────

SPECTACULAR_SETTINGS = {
    "TITLE": "DocFlow AI API",
    "DESCRIPTION": "AI-Powered Invoicing, Contracts & Document Management",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]",
    "SECURITY": [{"BearerAuth": []}],
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "displayRequestDuration": True,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# SIMPLE JWT
# ─────────────────────────────────────────────────────────────────────────────

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ["Bearer"],
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.getenv("JWT_SIGNING_KEY", default=SECRET_KEY),
    "JTI_CLAIM": "jti",
    "TOKEN_TYPE_CLAIM": "token_type",
}

# ─────────────────────────────────────────────────────────────────────────────
# CORS & CSRF Configuration
# ─────────────────────────────────────────────────────────────────────────────

cors_raw = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000",
)
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://docflow-.*\.vercel\.app$",
    r"^https://.*\.docflowai\.com$",
]

csrf_raw = os.getenv(
    "CSRF_TRUSTED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000",
)
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in csrf_raw.split(",") if origin.strip()]

CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ["Content-Disposition", "X-Request-ID"]

# ─────────────────────────────────────────────────────────────────────────────
# EMAIL (SendGrid)
# ─────────────────────────────────────────────────────────────────────────────

ANYMAIL = {
    "SENDGRID_API_KEY": os.getenv("SENDGRID_API_KEY", default=""),
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend" if DEBUG else "anymail.backends.sendgrid.EmailBackend"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", default="noreply@docflowai.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", default="http://localhost:3000")

# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION
# ─────────────────────────────────────────────────────────────────────────────

AUTH_USER_MODEL = "users.User"
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Modern django-allauth specifications
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None

GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", default="")
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", default="")

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "APP": {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "key": "",
        },
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# STRIPE
# ─────────────────────────────────────────────────────────────────────────────

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", default="")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", default="")
STRIPE_LIVE_MODE = os.getenv("STRIPE_LIVE_MODE", default=False)

DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"
DJSTRIPE_WEBHOOK_SECRET = STRIPE_WEBHOOK_SECRET
DJSTRIPE_USE_NATIVE_JSONFIELD = True

# ─────────────────────────────────────────────────────────────────────────────
# AI
# ─────────────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", default="")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", default="")
AI_MODEL_PRIMARY = os.getenv("AI_MODEL_PRIMARY", default="claude-3-5-sonnet-20240620")

# ─────────────────────────────────────────────────────────────────────────────
# CELERY
# ─────────────────────────────────────────────────────────────────────────────

CELERY_BROKER_URL = os.getenv("REDIS_URL")
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL")

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Africa/Nairobi"
CELERY_ENABLE_UTC = False

CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
CELERY_TASK_ALWAYS_EAGER = TESTING
CELERY_TASK_EAGER_PROPAGATES = TESTING

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "send-invoice-payment-reminders": {
        "task": "notifications.tasks.send_invoice_payment_reminders",
        "schedule": crontab(hour=8, minute=0),
    },
    "send-contract-expiry-alerts": {
        "task": "notifications.tasks.send_contract_expiry_alerts",
        "schedule": crontab(hour=8, minute=15),
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "{asctime} [{levelname}] {name} | {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "DEBUG" if DEBUG else "INFO",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# FIELD ENCRYPTION (django-encrypted-model-fields)
# ─────────────────────────────────────────────────────────────────────────────

FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", default="CZ0HJKLsPx9i7rkZ-Y1I6AqM1C_PPTJo_tfH2SE_nIM=")

# Convert to bytes (required by the library)
if isinstance(FIELD_ENCRYPTION_KEY, str):
    FIELD_ENCRYPTION_KEY = FIELD_ENCRYPTION_KEY.encode('utf-8')

# Safety check
if not FIELD_ENCRYPTION_KEY or len(FIELD_ENCRYPTION_KEY) < 32:
    raise django.core.exceptions.ImproperlyConfigured(
        "FIELD_ENCRYPTION_KEY must be set in your .env file. "
        "It should be a strong random string (at least 32 characters)."
    )