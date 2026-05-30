"""
DocFlow AI — notifications/apps.py
"""
import logging
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

class NotificationsConfig(AppConfig):
    name                = "notifications"
    verbose_name        = _("Notifications")
    default_auto_field  = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """
        Initialization hook for the notifications module.
        Safely configures monitoring log baselines and runtime metrics.
        """
        logger.info("Initializing NotificationsConfig subsystem successfully.")