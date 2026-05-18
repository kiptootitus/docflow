"""DocFlow AI — Local Development Settings"""
from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Use local file storage in dev
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Console email in dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Debug toolbar (optional)
INSTALLED_APPS += ["django_extensions"]
