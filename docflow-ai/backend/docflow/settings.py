"""
Django settings for docflow project.
"""

from pathlib import Path
from decouple import config
from datetime import timedelta
import dj_database_url
import os

# ====================== BASE DIRECTORY ======================
BASE_DIR = Path(__file__).resolve().parent.parent


# ====================== SECURITY ======================
SECRET_KEY = config(
    'SECRET_KEY',
    default='django-insecure-change-this-in-production'
)

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
)

# HTTPS / Proxy Security
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG


# ====================== APPLICATIONS ======================
INSTALLED_APPS = [
    # Django Apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    # Third-Party Apps
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
    'rest_framework.authtoken',

    'django_filters',
    'django_extensions',
    'django_celery_beat',
    'django_celery_results',
    'storages',
    'djstripe',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',  # if using Google login
    'djoser',
    'django_otp',
    'anymail',

    # Local Apps
    'companies',
    'documents',
    'users',
    'billing',
    'ai',
]


# ====================== MIDDLEWARE ======================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# ====================== URLS / WSGI ======================
ROOT_URLCONF = 'docflow.urls'

WSGI_APPLICATION = 'docflow.wsgi.application'


# ====================== TEMPLATES ======================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


# ====================== DATABASE ======================
# Option 1: DATABASE_URL (Docker / Production)
if os.environ.get('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('DATABASE_URL'),
            conn_max_age=600,
            conn_health_checks=True,
        )
    }

# Option 2: Individual Variables
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('POSTGRES_DB', default='docflow'),
            'USER': config('POSTGRES_USER', default='docflow'),
            'PASSWORD': config('POSTGRES_PASSWORD', default='docflow'),
            'HOST': config('POSTGRES_HOST', default='localhost'),
            'PORT': config('POSTGRES_PORT', default='5432'),
        }
    }


# ====================== PASSWORD VALIDATION ======================
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# ====================== INTERNATIONALIZATION ======================
LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Nairobi'

USE_I18N = True

USE_TZ = True


# ====================== STATIC FILES ======================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ====================== AWS S3 STORAGE ======================
USE_S3 = config('AWS_ACCESS_KEY_ID', default='') != ''

if USE_S3:
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME')

    AWS_QUERYSTRING_AUTH = False
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False

    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage"
        },
        "staticfiles": {
            "BACKEND": "storages.backends.s3.S3StaticStorage"
        },
    }


# ====================== REST FRAMEWORK ======================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],

    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],

    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend'
    ],

    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',

    'DEFAULT_PAGINATION_CLASS':
        'rest_framework.pagination.PageNumberPagination',

    'PAGE_SIZE': 20,
}


# ====================== DRF SPECTACULAR ======================
SPECTACULAR_SETTINGS = {
    'TITLE': 'DocFlow API',
    'DESCRIPTION': 'AI-Powered Document Management System',
    'VERSION': '1.0.0',
}


# ====================== SIMPLE JWT ======================
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),

    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),

    'ROTATE_REFRESH_TOKENS': True,

    'BLACKLIST_AFTER_ROTATION': True,

    'UPDATE_LAST_LOGIN': True,

    'AUTH_HEADER_TYPES': ('Bearer',),
}


# ====================== CORS ======================
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
)

CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
)

CORS_ALLOW_CREDENTIALS = True


# ====================== CELERY ======================
REDIS_URL = os.environ.get('REDIS_URL')

if REDIS_URL:
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL

else:
    REDIS_HOST = config('REDIS_HOST', default='localhost')
    REDIS_PORT = config('REDIS_PORT', default='6379')
    REDIS_PASSWORD = config('REDIS_PASSWORD', default='')

    if REDIS_PASSWORD:
        CELERY_BROKER_URL = (
            f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"
        )

        CELERY_RESULT_BACKEND = (
            f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"
        )

    else:
        CELERY_BROKER_URL = (
            f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
        )

        CELERY_RESULT_BACKEND = (
            f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
        )

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE


# ====================== EMAIL (SENDGRID) ======================
ANYMAIL = {
    'SENDGRID_API_KEY': config(
        'SENDGRID_API_KEY',
        default=''
    ),
}

EMAIL_BACKEND = 'anymail.backends.sendgrid.EmailBackend'

DEFAULT_FROM_EMAIL = config(
    'DEFAULT_FROM_EMAIL',
    default='noreply@example.com'
)


# ====================== STRIPE ======================
STRIPE_SECRET_KEY = config(
    'STRIPE_SECRET_KEY',
    default=''
)

STRIPE_PUBLISHABLE_KEY = config(
    'STRIPE_PUBLISHABLE_KEY',
    default=''
)

STRIPE_WEBHOOK_SECRET = config(
    'STRIPE_WEBHOOK_SECRET',
    default=''
)

STRIPE_LIVE_MODE = config(
    'STRIPE_LIVE_MODE',
    default=False,
    cast=bool
)

DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"


# ====================== AI KEYS ======================
ANTHROPIC_API_KEY = config(
    'ANTHROPIC_API_KEY',
    default=''
)

OPENAI_API_KEY = config(
    'OPENAI_API_KEY',
    default=''
)


# ====================== AI CONFIGURATION ======================
AI_MODEL_PRIMARY = config(
    'AI_MODEL_PRIMARY',
    default='claude-3-5-sonnet-20240620'
)

# Anthropic
ANTHROPIC_MODEL = config(
    'ANTHROPIC_MODEL',
    default='claude-3-5-sonnet-20240620'
)

ANTHROPIC_MAX_TOKENS = config(
    'ANTHROPIC_MAX_TOKENS',
    default=4096,
    cast=int
)

ANTHROPIC_TEMPERATURE = config(
    'ANTHROPIC_TEMPERATURE',
    default=0.0,
    cast=float
)

# OpenAI
OPENAI_MODEL = config(
    'OPENAI_MODEL',
    default='gpt-4o'
)

OPENAI_MAX_TOKENS = config(
    'OPENAI_MAX_TOKENS',
    default=4096,
    cast=int
)

OPENAI_TEMPERATURE = config(
    'OPENAI_TEMPERATURE',
    default=0.0,
    cast=float
)

# General AI Settings
AI_DEFAULT_TIMEOUT = config(
    'AI_DEFAULT_TIMEOUT',
    default=120,
    cast=int
)

AI_MAX_RETRIES = config(
    'AI_MAX_RETRIES',
    default=3,
    cast=int
)


# ====================== AUTHENTICATION ======================
AUTH_USER_MODEL = 'users.User'

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
)

# allauth
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = 'email'

# Recommended for newer allauth versions
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']

# Sites Framework
SITE_ID = 1


# ====================== DEFAULT PRIMARY KEY ======================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
# ====================== CELERY ======================

# SAFE REDIS CONFIG (Docker + Local compatible)
REDIS_URL = os.environ.get("REDIS_URL")

if REDIS_URL:
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
else:
    REDIS_HOST = config("REDIS_HOST", default="redis")  # 👈 FIXED (NOT localhost)
    REDIS_PORT = config("REDIS_PORT", default="6379")
    REDIS_PASSWORD = config("REDIS_PASSWORD", default="")

    if REDIS_PASSWORD:
        REDIS_CONN = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"
    else:
        REDIS_CONN = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

    CELERY_BROKER_URL = REDIS_CONN
    CELERY_RESULT_BACKEND = REDIS_CONN


# ====================== CELERY OPTIONS ======================

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = False

# 🔥 IMPORTANT FIXES (your stability issues)
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_REJECT_ON_WORKER_LOST = True

CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = 10

CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 3600
CELERY_TASK_SOFT_TIME_LIMIT = 3300

CELERY_RESULT_EXPIRES = 3600

CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": 3600,
}