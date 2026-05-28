"""
DocFlow AI — users/apps.py

AppConfig for the users app.
Connects all signal receivers exactly once when Django is ready.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    name = "users"
    verbose_name = _("Users")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """
        Import signal module to register all receivers.
        Called once by Django after all apps are loaded.
        """
        import users.signals  # noqa: F401  — side-effect import