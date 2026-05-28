"""
DocFlow AI — users/models.py
Custom AbstractBaseUser with email login, Role-based access,
two-factor auth (TOTP), avatar upload to S3, and audit timestamps.

Design principles:
  • No username — email is the primary identifier.
  • Role enum is stored per-company via CompanyMembership (separate app),
    but a global `role` field marks super-admins vs regular accounts.
  • UUIDs as primary keys to prevent enumeration attacks.
  • All timestamps stored as UTC.
  • SoftDeleteMixin: objects are deactivated, never hard-deleted.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(StrEnum):
    """Platform-level role.  Fine-grained per-company roles live in companies.models."""
    SUPER_ADMIN = "super_admin"   # Anthropic/internal staff
    OWNER       = "owner"         # Workspace owner (pays the bill)
    STAFF       = "staff"         # Invited team member
    ACCOUNTANT  = "accountant"    # View financials, no edit
    CLIENT      = "client"        # Read-only portal access


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class UserManager(BaseUserManager["User"]):
    """Custom manager — create_user / create_superuser by email."""

    use_in_migrations = True

    def _create_user(
        self,
        email: str,
        password: str | None,
        **extra_fields,
    ) -> "User":
        if not email:
            raise ValueError(_("An email address is required."))
        email = self.normalize_email(email)
        user: User = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields,
    ) -> "User":
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", UserRole.OWNER)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields,
    ) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", UserRole.SUPER_ADMIN)
        extra_fields.setdefault("is_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self._create_user(email, password, **extra_fields)

    def active(self):
        """Queryset shortcut: only non-deleted, active users."""
        return self.filter(is_active=True, deleted_at__isnull=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _avatar_upload_path(instance: "User", filename: str) -> str:
    """Store avatars under users/<uuid>/avatar/<filename> in S3."""
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"users/{instance.pk}/avatar/avatar.{ext}"


# ---------------------------------------------------------------------------
# User Model
# ---------------------------------------------------------------------------

class User(AbstractBaseUser, PermissionsMixin):
    """
    DocFlow AI user account.

    Authentication:  email + password  (JWT via djoser/Simple JWT)
    Social login:    Google OAuth 2.0  (django-allauth)
    2FA:             TOTP              (django-otp)
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_index=True,
    )
    email = models.EmailField(
        _("email address"),
        unique=True,
        max_length=255,
        db_index=True,
    )
    first_name = models.CharField(_("first name"), max_length=80, blank=True)
    last_name  = models.CharField(_("last name"),  max_length=80, blank=True)
    avatar     = models.ImageField(
        _("profile picture"),
        upload_to=_avatar_upload_path,
        null=True,
        blank=True,
    )

    # ------------------------------------------------------------------
    # Role & status
    # ------------------------------------------------------------------
    role = models.CharField(
        _("platform role"),
        max_length=20,
        choices=[(r.value, r.name.replace("_", " ").title()) for r in UserRole],
        default=UserRole.OWNER,
        db_index=True,
    )
    is_active   = models.BooleanField(_("active"), default=True)
    is_staff    = models.BooleanField(_("staff"), default=False)   # Django admin access
    is_verified = models.BooleanField(_("email verified"), default=False)

    # ------------------------------------------------------------------
    # Two-factor authentication helpers
    # ------------------------------------------------------------------
    totp_enabled = models.BooleanField(_("2FA enabled"), default=False)

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------
    timezone_name = models.CharField(
        _("timezone"),
        max_length=60,
        default="UTC",
        help_text=_("IANA timezone string, e.g. 'Africa/Nairobi'"),
    )
    language = models.CharField(
        _("language"),
        max_length=10,
        default="en",
        help_text=_("BCP 47 language tag, e.g. 'en', 'fr', 'sw'"),
    )

    # ------------------------------------------------------------------
    # Soft-delete & timestamps
    # ------------------------------------------------------------------
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    last_login_ip = models.GenericIPAddressField(
        _("last login IP"), null=True, blank=True
    )
    deleted_at = models.DateTimeField(
        _("deleted at"), null=True, blank=True, db_index=True
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    # ------------------------------------------------------------------
    # Django auth plumbing
    # ------------------------------------------------------------------
    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        verbose_name        = _("user")
        verbose_name_plural = _("users")
        ordering            = ["-date_joined"]
        indexes = [
            models.Index(fields=["email", "is_active"]),
            models.Index(fields=["role", "is_active"]),
        ]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def get_full_name(self) -> str:  # Django convention
        return self.full_name

    def get_short_name(self) -> str:
        return self.first_name or self.email.split("@")[0]

    def soft_delete(self) -> None:
        """Deactivate account without removing the DB row."""
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_active", "deleted_at", "updated_at"])

    def restore(self) -> None:
        """Reactivate a previously soft-deleted account."""
        self.is_active = True
        self.deleted_at = None
        self.save(update_fields=["is_active", "deleted_at", "updated_at"])

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"


# ---------------------------------------------------------------------------
# Email Verification Token
# ---------------------------------------------------------------------------

class EmailVerificationToken(models.Model):
    """
    One-time token sent via email to verify ownership.
    Tokens expire after TOKEN_TTL_HOURS; used tokens are kept for audit.
    """

    TOKEN_TTL_HOURS = 24

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="verification_tokens",
    )
    token      = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = _("email verification token")
        verbose_name_plural = _("email verification tokens")
        ordering            = ["-created_at"]

    @property
    def is_expired(self) -> bool:
        from datetime import timedelta
        return timezone.now() > self.created_at + timedelta(hours=self.TOKEN_TTL_HOURS)

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    def consume(self) -> None:
        """Mark token as used and verify the user's email."""
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])
        self.user.is_verified = True
        self.user.save(update_fields=["is_verified", "updated_at"])

    def __str__(self) -> str:
        return f"VerifyToken({self.user.email}, used={self.is_used})"


# ---------------------------------------------------------------------------
# Password Reset Token
# ---------------------------------------------------------------------------

class PasswordResetToken(models.Model):
    """
    Secure single-use token for password resets.
    Stored as SHA-256 hash — raw token is sent to the user only once.
    """

    TOKEN_TTL_HOURS = 2

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token_hash = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text=_("SHA-256 hash of the raw token."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    used_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = _("password reset token")
        verbose_name_plural = _("password reset tokens")
        ordering            = ["-created_at"]

    @property
    def is_expired(self) -> bool:
        from datetime import timedelta
        return timezone.now() > self.created_at + timedelta(hours=self.TOKEN_TTL_HOURS)

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    def consume(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])

    def __str__(self) -> str:
        return f"PasswordResetToken({self.user.email}, used={self.is_used})"


# ---------------------------------------------------------------------------
# UserAuditLog
# ---------------------------------------------------------------------------

class UserAuditLog(models.Model):
    """
    Immutable audit trail for security-critical user events.
    Rows are never updated or deleted — append-only.
    """

    class EventType(models.TextChoices):
        LOGIN_SUCCESS    = "login_success",    _("Login success")
        LOGIN_FAILED     = "login_failed",     _("Login failed")
        LOGOUT           = "logout",           _("Logout")
        PASSWORD_CHANGED = "password_changed", _("Password changed")
        PASSWORD_RESET   = "password_reset",   _("Password reset")
        EMAIL_CHANGED    = "email_changed",    _("Email changed")
        EMAIL_VERIFIED   = "email_verified",   _("Email verified")
        TOTP_ENABLED     = "totp_enabled",     _("2FA enabled")
        TOTP_DISABLED    = "totp_disabled",    _("2FA disabled")
        ROLE_CHANGED     = "role_changed",     _("Role changed")
        ACCOUNT_DELETED  = "account_deleted",  _("Account deleted")
        ACCOUNT_RESTORED = "account_restored", _("Account restored")

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs",
    )
    event      = models.CharField(max_length=30, choices=EventType.choices, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata   = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name        = _("user audit log")
        verbose_name_plural = _("user audit logs")
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "event"]),
            models.Index(fields=["event", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.event}] {self.user} @ {self.created_at:%Y-%m-%d %H:%M}"