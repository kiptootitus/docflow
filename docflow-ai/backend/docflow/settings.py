"""
Django settings for docflow project.
"""

from pathlib import Path
from decouple import config
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# ====================== SECURITY ======================
SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=lambda v: [s.strip() for s in v.split(',') if s.strip()])


# ====================== APPLICATIONS ======================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',           # ← Add this
    # Third-party
    'rest_framework',
    'corsheaders',
    'drf_spectacular',
    'django_filters',
    'django_extensions',
    'django_celery_beat',
    'django_celery_results',
    'storages',
    'djstripe',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'djoser',
    'django_otp',

    # Local apps
    'companies',
    'documents',
    'users',
    'billing',
    'ai',
    #notifications',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    
    # Allauth middleware - MUST be added here
    'allauth.account.middleware.AccountMiddleware',
    
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'docflow.urls'

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

WSGI_APPLICATION = 'docflow.wsgi.application'


# ====================== DATABASE ======================
DATABASES = {
    'default': dj_database_url.config(
        default=f"postgres://{config('POSTGRES_USER')}:{config('POSTGRES_PASSWORD')}@localhost:5432/{config('POSTGRES_DB')}"
    )
}


# ====================== PASSWORD VALIDATION ======================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ====================== INTERNATIONALIZATION ======================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True


# ====================== STATIC & MEDIA ======================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ====================== AWS S3 (django-storages) ======================
USE_S3 = config('AWS_ACCESS_KEY_ID', default='') != ''

if USE_S3:
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME')
    
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "storages.backends.s3.S3StaticStorage"},
    }


# ====================== REST FRAMEWORK ======================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}


# ====================== SPECTACULAR ======================
SPECTACULAR_SETTINGS = {
    'TITLE': 'DocFlow API',
    'DESCRIPTION': 'AI-Powered Document Management System',
    'VERSION': '1.0.0',
}


# ====================== SIMPLE JWT ======================
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}


# ====================== CORS ======================
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', cast=lambda v: [s.strip() for s in v.split(',') if s.strip()])
CORS_ALLOW_CREDENTIALS = True


# ====================== CELERY ======================
CELERY_BROKER_URL = f"redis://:{config('REDIS_PASSWORD')}@localhost:6379/0"
CELERY_RESULT_BACKEND = 'django-db'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE


# ====================== EMAIL (SendGrid) ======================
ANYMAIL = {
    'SENDGRID_API_KEY': config('SENDGRID_API_KEY'),
}
EMAIL_BACKEND = 'anymail.backends.sendgrid.EmailBackend'
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL')


# ====================== STRIPE ======================
# ====================== STRIPE ======================
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = config('STRIPE_PUBLISHABLE_KEY')
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET')
STRIPE_LIVE_MODE = config('STRIPE_LIVE_MODE', default=False, cast=bool)
DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"   # Use this for new projects
# Set Stripe API key globally (recommended)
import stripe
stripe.api_key = STRIPE_SECRET_KEY


# ====================== AI KEYS ======================
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')
OPENAI_API_KEY = config('OPENAI_API_KEY', default='')


# ====================== OTHER ======================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
# ====================== AI CONFIGURATION ======================
AI_MODEL_PRIMARY = config('AI_MODEL_PRIMARY', default='claude-3-5-sonnet-20240620')

# Anthropic Models
ANTHROPIC_MODEL = config('ANTHROPIC_MODEL', default='claude-3-5-sonnet-20240620')
ANTHROPIC_MAX_TOKENS = config('ANTHROPIC_MAX_TOKENS', default=4096, cast=int)
ANTHROPIC_TEMPERATURE = config('ANTHROPIC_TEMPERATURE', default=0.0, cast=float)

# OpenAI Models (fallback)
OPENAI_MODEL = config('OPENAI_MODEL', default='gpt-4o')
OPENAI_MAX_TOKENS = config('OPENAI_MAX_TOKENS', default=4096, cast=int)
OPENAI_TEMPERATURE = config('OPENAI_TEMPERATURE', default=0.0, cast=float)

# General AI Settings
AI_DEFAULT_TIMEOUT = config('AI_DEFAULT_TIMEOUT', default=120, cast=int)
AI_MAX_RETRIES = config('AI_MAX_RETRIES', default=3, cast=int)
# ====================== AUTHENTICATION ======================
AUTH_USER_MODEL = 'users.User'

# allauth settings
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = 'email'

# Sites framework (required by allauth)
SITE_ID = 1