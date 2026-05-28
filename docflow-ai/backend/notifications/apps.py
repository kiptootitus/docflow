"""
DocFlow AI — notifications/apps.py
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class NotificationsConfig(AppConfig):
    name                = "notifications"
    verbose_name        = _("Notifications")
    default_auto_field  = "django.db.models.BigAutoField"

    def ready(self) -> None:
        pass  # Signal receivers added here when needed


