"""
DocFlow AI — notifications/models.py

Two core models:

  Notification
    A persisted in-app notification record (bell icon in the UI).
    Every notification has a channel bitmask so one record can fan out
    to email + push + in-app simultaneously while keeping a single
    source of truth.

  NotificationPreference
    Per-user, per-category opt-in/opt-out settings.
    Governs whether email and/or push are sent for each category.

  PushToken
    Stores Expo / FCM / APNS device tokens per user.
    A user can have multiple devices (phone + tablet + web PWA).

Design decisions:
  • UUID PKs everywhere — no enumerable integer IDs in URLs.
  • Soft-read: notifications are marked read, never hard-deleted.
  • Category drives both routing (which channel) and UX (icon, colour).
  • Channels are a bitmask integer stored in SmallIntegerField so a
    single DB field answers "was this sent via email?", "push?", etc.
  • All foreign keys use SET_NULL so deleting a user doesn't cascade
    and destroy audit history.
"""

from __future__ import annotations

import uuid
from enum import IntFlag

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Channel bitmask
# ---------------------------------------------------------------------------

class Channel(IntFlag):
    """
    Bitmask representing which delivery channels were used / are requested.

    Usage:
        channels = Channel.EMAIL | Channel.PUSH   # = 3
        bool(channels & Channel.EMAIL)            # True
        bool(channels & Channel.IN_APP)           # False
    """
    IN_APP = 1
    EMAIL  = 2
    PUSH   = 4


# ---------------------------------------------------------------------------
# Notification categories
# ---------------------------------------------------------------------------

class NotificationCategory(models.TextChoices):
    # ── Auth / Security ────────────────────────────────────────────────
    SECURITY          = "security",          _("Security alert")
    PASSWORD_CHANGED  = "password_changed",  _("Password changed")
    TWO_FA_ENABLED    = "two_fa_enabled",    _("2FA enabled")
    TWO_FA_DISABLED   = "two_fa_disabled",   _("2FA disabled")
    NEW_LOGIN         = "new_login",         _("New login detected")

    # ── Invoices ───────────────────────────────────────────────────────
    INVOICE_SENT      = "invoice_sent",      _("Invoice sent")
    INVOICE_VIEWED    = "invoice_viewed",    _("Invoice viewed by client")
    INVOICE_PAID      = "invoice_paid",      _("Invoice paid")
    INVOICE_OVERDUE   = "invoice_overdue",   _("Invoice overdue")
    PAYMENT_REMINDER  = "payment_reminder",  _("Payment reminder")
    PAYMENT_RECEIVED  = "payment_received",  _("Payment received")

    # ── Contracts ──────────────────────────────────────────────────────
    CONTRACT_SIGNED   = "contract_signed",   _("Contract signed")
    CONTRACT_EXPIRING = "contract_expiring", _("Contract expiring soon")
    CONTRACT_EXPIRED  = "contract_expired",  _("Contract expired")
    AI_REVIEW_DONE    = "ai_review_done",    _("AI contract review complete")

    # ── Billing / Subscription ─────────────────────────────────────────
    SUBSCRIPTION_UPGRADED  = "subscription_upgraded",  _("Subscription upgraded")
    SUBSCRIPTION_CANCELLED = "subscription_cancelled", _("Subscription cancelled")
    PAYMENT_FAILED         = "payment_failed",         _("Payment failed")
    TRIAL_ENDING           = "trial_ending",           _("Trial ending soon")

    # ── System ─────────────────────────────────────────────────────────
    SYSTEM              = "system",              _("System announcement")
    COMPLIANCE_ALERT    = "compliance_alert",    _("Compliance alert")
    WELCOME             = "welcome",             _("Welcome")


# Priority levels — controls push notification urgency and UI badge colour
class NotificationPriority(models.TextChoices):
    LOW      = "low",      _("Low")
    NORMAL   = "normal",   _("Normal")
    HIGH     = "high",     _("High")
    CRITICAL = "critical", _("Critical")  # Security / account threats


# ---------------------------------------------------------------------------
# PushToken
# ---------------------------------------------------------------------------

class PushTokenPlatform(models.TextChoices):
    EXPO    = "expo",    _("Expo Push")
    FCM     = "fcm",     _("Firebase (Android)")
    APNS    = "apns",    _("Apple (iOS)")
    WEB     = "web",     _("Web Push")


class PushToken(models.Model):
    """
    Device push token for a user.
    A user can have multiple tokens (multiple devices).
    Tokens are rotated by the mobile app on each launch via PATCH /notifications/push-tokens/<id>/.
    Stale tokens (is_active=False) are kept for 30 days for debugging then purged by Celery beat.
    """

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_tokens",
    )
    token      = models.TextField(
        unique=True,
        help_text=_("Expo push token, FCM registration ID, or APNS device token."),
    )
    platform   = models.CharField(
        max_length=10,
        choices=PushTokenPlatform.choices,
        default=PushTokenPlatform.EXPO,
        db_index=True,
    )
    device_name = models.CharField(
        _("device name"),
        max_length=120,
        blank=True,
        help_text=_("Human-readable label, e.g. 'Alice's iPhone 15'."),
    )
    is_active  = models.BooleanField(_("active"), default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = _("push token")
        verbose_name_plural = _("push tokens")
        ordering            = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["platform", "is_active"]),
        ]

    def deactivate(self) -> None:
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])

    def __str__(self) -> str:
        return f"PushToken({self.user_id} / {self.platform} / active={self.is_active})"


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------

class Notification(models.Model):
    """
    A single notification record.

    Lifecycle:
      created  →  pending channels dispatched by tasks.py
               →  read_at set when user marks it read
               →  never deleted (soft read only)

    channels_sent bitmask tells us exactly what was dispatched.
    channels_requested tells us what was originally requested.
    They can differ when a user has disabled a channel in preferences.
    """

    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="notifications",
        db_index=True,
    )
    category  = models.CharField(
        max_length=40,
        choices=NotificationCategory.choices,
        db_index=True,
    )
    priority  = models.CharField(
        max_length=10,
        choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL,
        db_index=True,
    )

    # ── Content ────────────────────────────────────────────────────────
    title   = models.CharField(_("title"),   max_length=160)
    body    = models.TextField(_("body"),    blank=True)
    # Extra structured data — e.g. {"invoice_id": "...", "amount": 1200}
    data    = models.JSONField(_("data"),    default=dict, blank=True)
    # Deep-link URL for mobile push tap action
    action_url = models.CharField(max_length=500, blank=True)

    # ── Channels ───────────────────────────────────────────────────────
    # Bitmask integers (Channel enum above)
    channels_requested = models.SmallIntegerField(
        _("channels requested"),
        default=Channel.IN_APP,
        help_text=_("OR of Channel flags requested at creation time."),
    )
    channels_sent = models.SmallIntegerField(
        _("channels sent"),
        default=0,
        help_text=_("OR of Channel flags actually dispatched."),
    )

    # ── Read state ─────────────────────────────────────────────────────
    read_at    = models.DateTimeField(_("read at"), null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # ── Delivery tracking ──────────────────────────────────────────────
    email_message_id = models.CharField(
        _("SendGrid message-id"), max_length=255, blank=True,
        help_text=_("Returned by SendGrid on successful dispatch."),
    )
    push_ticket_id = models.CharField(
        _("Expo push ticket id"), max_length=255, blank=True,
    )

    class Meta:
        verbose_name        = _("notification")
        verbose_name_plural = _("notifications")
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "read_at"]),
            models.Index(fields=["user", "category"]),
            models.Index(fields=["category", "created_at"]),
            models.Index(fields=["priority", "created_at"]),
        ]

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    @property
    def via_email(self) -> bool:
        return bool(self.channels_sent & Channel.EMAIL)

    @property
    def via_push(self) -> bool:
        return bool(self.channels_sent & Channel.PUSH)

    @property
    def via_in_app(self) -> bool:
        return bool(self.channels_sent & Channel.IN_APP)

    # ── Methods ────────────────────────────────────────────────────────

    def mark_read(self) -> None:
        if not self.is_read:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at"])

    def mark_channel_sent(self, channel: Channel) -> None:
        """Atomically OR in a channel flag after successful dispatch."""
        self.channels_sent = self.channels_sent | int(channel)
        self.save(update_fields=["channels_sent"])

    def __str__(self) -> str:
        status = "read" if self.is_read else "unread"
        return f"[{self.category}] {self.title[:40]} ({status})"

    def __repr__(self) -> str:
        return f"<Notification id={self.id} cat={self.category} user={self.user_id}>"


# ---------------------------------------------------------------------------
# NotificationPreference
# ---------------------------------------------------------------------------

# Default channel preferences per category — used when no override exists.
# Channels is an OR of Channel flags.
CATEGORY_DEFAULTS: dict[str, int] = {
    # Security — always send email + push, never suppress
    NotificationCategory.SECURITY:          Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.PASSWORD_CHANGED:  Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.TWO_FA_ENABLED:    Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.TWO_FA_DISABLED:   Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.NEW_LOGIN:         Channel.EMAIL | Channel.IN_APP,

    # Invoices — email + push + in-app by default
    NotificationCategory.INVOICE_SENT:      Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.INVOICE_VIEWED:    Channel.IN_APP,
    NotificationCategory.INVOICE_PAID:      Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.INVOICE_OVERDUE:   Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.PAYMENT_REMINDER:  Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.PAYMENT_RECEIVED:  Channel.EMAIL | Channel.PUSH | Channel.IN_APP,

    # Contracts
    NotificationCategory.CONTRACT_SIGNED:   Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.CONTRACT_EXPIRING: Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.CONTRACT_EXPIRED:  Channel.EMAIL | Channel.IN_APP,
    NotificationCategory.AI_REVIEW_DONE:    Channel.PUSH  | Channel.IN_APP,

    # Billing
    NotificationCategory.SUBSCRIPTION_UPGRADED:  Channel.EMAIL | Channel.IN_APP,
    NotificationCategory.SUBSCRIPTION_CANCELLED: Channel.EMAIL | Channel.IN_APP,
    NotificationCategory.PAYMENT_FAILED:         Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.TRIAL_ENDING:           Channel.EMAIL | Channel.PUSH | Channel.IN_APP,

    # System
    NotificationCategory.SYSTEM:            Channel.EMAIL | Channel.IN_APP,
    NotificationCategory.COMPLIANCE_ALERT:  Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.WELCOME:           Channel.EMAIL | Channel.IN_APP,
}

# Categories whose email channel CANNOT be disabled (security-critical)
MANDATORY_EMAIL_CATEGORIES = frozenset({
    NotificationCategory.SECURITY,
    NotificationCategory.PASSWORD_CHANGED,
    NotificationCategory.TWO_FA_ENABLED,
    NotificationCategory.TWO_FA_DISABLED,
    NotificationCategory.PAYMENT_FAILED,
})


class NotificationPreference(models.Model):
    """
    One row per (user, category) pair.  If no row exists the system falls
    back to CATEGORY_DEFAULTS.

    The channels field is a bitmask (same Channel enum) indicating which
    delivery channels the user wants for that category.

    Security-critical categories (MANDATORY_EMAIL_CATEGORIES) always
    include email regardless of the stored preference.
    """

    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    category = models.CharField(
        max_length=40,
        choices=NotificationCategory.choices,
        db_index=True,
    )
    # Bitmask — which channels does this user want for this category?
    channels = models.SmallIntegerField(
        _("enabled channels"),
        default=Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = _("notification preference")
        verbose_name_plural = _("notification preferences")
        unique_together     = [("user", "category")]
        indexes = [
            models.Index(fields=["user", "category"]),
        ]

    # ── Class-level helpers ────────────────────────────────────────────

    @classmethod
    def get_channels_for(cls, user, category: str) -> int:
        """
        Return the effective channel bitmask for (user, category).
        Falls back to CATEGORY_DEFAULTS if no preference row exists.
        Enforces mandatory email for security-critical categories.
        """
        try:
            pref = cls.objects.get(user=user, category=category)
            channels = pref.channels
        except cls.DoesNotExist:
            channels = CATEGORY_DEFAULTS.get(category, Channel.IN_APP)

        # Force email for mandatory categories regardless of preference
        if category in MANDATORY_EMAIL_CATEGORIES:
            channels = channels | int(Channel.EMAIL)

        return channels

    def __str__(self) -> str:
        return f"NotifPref({self.user_id} / {self.category} / channels={self.channels})"