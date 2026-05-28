"""
DocFlow — Production Django Settings
"""
import os
import boto3
from .base import *  # noqa

# ──────────────────────────────────────────────────────────
# Core
# ──────────────────────────────────────────────────────────
DEBUG = False
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")

# ──────────────────────────────────────────────────────────
# Database — RDS PostgreSQL
# ──────────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE":   "django.db.backends.postgresql",
        "NAME":     os.environ["DB_NAME"],
        "USER":     os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST":     os.environ["DB_HOST"],
        "PORT":     os.environ.get("DB_PORT", "5432"),
        "OPTIONS": {
            "sslmode": "require",
            "connect_timeout": 10,
        },
        "CONN_MAX_AGE": 60,
    }
}

# ──────────────────────────────────────────────────────────
# Redis — ElastiCache (TLS)
# ──────────────────────────────────────────────────────────
REDIS_URL = os.environ["REDIS_URL"]  # rediss://host:6379/0

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {"ssl_cert_reqs": None},
        },
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# ──────────────────────────────────────────────────────────
# Celery
# ──────────────────────────────────────────────────────────
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": "CERT_NONE"}
CELERY_REDIS_BACKEND_USE_SSL = {"ssl_cert_reqs": "CERT_NONE"}
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Africa/Nairobi"

# ──────────────────────────────────────────────────────────
# Storage — S3 + CloudFront
# ──────────────────────────────────────────────────────────
AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
AWS_S3_REGION_NAME      = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")
AWS_S3_FILE_OVERWRITE   = False
AWS_DEFAULT_ACL         = None
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
CLOUDFRONT_DOMAIN = os.environ.get("CLOUDFRONT_DOMAIN", "")

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name":  AWS_STORAGE_BUCKET_NAME,
            "location":     "media",
            "custom_domain": CLOUDFRONT_DOMAIN or None,
        },
    },
    "staticfiles": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name":  os.environ.get("STATIC_BUCKET", AWS_STORAGE_BUCKET_NAME),
            "location":     "static",
            "custom_domain": CLOUDFRONT_DOMAIN or None,
        },
    },
}

# ──────────────────────────────────────────────────────────
# Security
# ──────────────────────────────────────────────────────────
SECURE_SSL_REDIRECT                 = True
SECURE_PROXY_SSL_HEADER             = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE               = True
CSRF_COOKIE_SECURE                  = True
SECURE_BROWSER_XSS_FILTER          = True
SECURE_CONTENT_TYPE_NOSNIFF        = True
SECURE_HSTS_SECONDS                 = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS      = True
SECURE_HSTS_PRELOAD                 = True
X_FRAME_OPTIONS                     = "DENY"

CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ORIGINS", "https://docflow.com").split(",")

# ──────────────────────────────────────────────────────────
# Logging — CloudWatch via stdout (ECS picks it up)
# ──────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class":     "logging.StreamHandler",
            "formatter": "json",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django":          {"handlers": ["console"], "level": "INFO",  "propagate": False},
        "django.request":  {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "celery":          {"handlers": ["console"], "level": "INFO",  "propagate": False},
    },
}

# ──────────────────────────────────────────────────────────
# Health Check URL (used by ALB)
# ──────────────────────────────────────────────────────────
# Add to your urls.py:
# path("health/", lambda r: HttpResponse("ok"), name="health"),
