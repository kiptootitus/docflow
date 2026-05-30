"""
DocFlow AI — notifications/models.py
"""
from __future__ import annotations

import uuid
from enum import IntFlag

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Channel(IntFlag):
    IN_APP = 1
    EMAIL  = 2
    PUSH   = 4


class NotificationCategory(models.TextChoices):
    SECURITY          = "security",          _("Security alert")
    PASSWORD_CHANGED  = "password_changed",  _("Password changed")
    TWO_FA_ENABLED    = "two_fa_enabled",    _("2FA enabled")
    TWO_FA_DISABLED   = "two_fa_disabled",   _("2FA disabled")
    NEW_LOGIN         = "new_login",         _("New login detected")

    INVOICE_SENT      = "invoice_sent",      _("Invoice sent")
    INVOICE_VIEWED    = "invoice_viewed",    _("Invoice viewed by client")
    INVOICE_PAID      = "invoice_paid",      _("Invoice paid")
    INVOICE_OVERDUE   = "invoice_overdue",   _("Invoice overdue")
    PAYMENT_REMINDER  = "payment_reminder",  _("Payment reminder")
    PAYMENT_RECEIVED  = "payment_received",  _("Payment received")

    CONTRACT_SIGNED   = "contract_signed",   _("Contract signed")
    CONTRACT_EXPIRING = "contract_expiring", _("Contract expiring soon")
    CONTRACT_EXPIRED  = "contract_expired",  _("Contract expired")
    AI_REVIEW_DONE    = "ai_review_done",    _("AI contract review complete")

    SUBSCRIPTION_UPGRADED  = "subscription_upgraded",  _("Subscription upgraded")
    SUBSCRIPTION_CANCELLED = "subscription_cancelled", _("Subscription cancelled")
    PAYMENT_FAILED         = "payment_failed",         _("Payment failed")
    TRIAL_ENDING           = "trial_ending",           _("Trial ending soon")

    SYSTEM              = "system",              _("System announcement")
    COMPLIANCE_ALERT    = "compliance_alert",    _("Compliance alert")
    WELCOME             = "welcome",             _("Welcome")


class NotificationPriority(models.TextChoices):
    LOW      = "low",      _("Low")
    NORMAL   = "normal",   _("Normal")
    HIGH     = "high",     _("High")
    CRITICAL = "critical", _("Critical")


class PushTokenPlatform(models.TextChoices):
    EXPO    = "expo",    _("Expo Push")
    FCM     = "fcm",     _("Firebase (Android)")
    APNS    = "apns",    _("Apple (iOS)")
    WEB     = "web",     _("Web Push")


class PushToken(models.Model):
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


class Notification(models.Model):
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

    title   = models.CharField(_("title"),   max_length=160)
    body    = models.TextField(_("body"),    blank=True)
    data    = models.JSONField(_("data"),    default=dict, blank=True)
    action_url = models.CharField(max_length=500, blank=True)

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

    read_at    = models.DateTimeField(_("read at"), null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

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

    def mark_read(self) -> None:
        if not self.is_read:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at"])

    def mark_channel_sent(self, channel: Channel) -> None:
        self.channels_sent = self.channels_sent | int(channel)
        self.save(update_fields=["channels_sent"])

    def __str__(self) -> str:
        status = "read" if self.is_read else "unread"
        return f"[{self.category}] {self.title[:40]} ({status})"

    def __repr__(self) -> str:
        return f"<Notification id={self.id} cat={self.category} user={self.user_id}>"


CATEGORY_DEFAULTS: dict[str, int] = {
    NotificationCategory.SECURITY:          Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.PASSWORD_CHANGED:  Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.TWO_FA_ENABLED:    Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.TWO_FA_DISABLED:   Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.NEW_LOGIN:         Channel.EMAIL | Channel.IN_APP,

    NotificationCategory.INVOICE_SENT:      Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.INVOICE_VIEWED:    Channel.IN_APP,
    NotificationCategory.INVOICE_PAID:      Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.INVOICE_OVERDUE:   Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.PAYMENT_REMINDER:  Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.PAYMENT_RECEIVED:  Channel.EMAIL | Channel.PUSH | Channel.IN_APP,

    NotificationCategory.CONTRACT_SIGNED:   Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.CONTRACT_EXPIRING: Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.CONTRACT_EXPIRED:  Channel.EMAIL | Channel.IN_APP,
    NotificationCategory.AI_REVIEW_DONE:    Channel.PUSH  | Channel.IN_APP,

    NotificationCategory.SUBSCRIPTION_UPGRADED:  Channel.EMAIL | Channel.IN_APP,
    NotificationCategory.SUBSCRIPTION_CANCELLED: Channel.EMAIL | Channel.IN_APP,
    NotificationCategory.PAYMENT_FAILED:         Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.TRIAL_ENDING:           Channel.EMAIL | Channel.PUSH | Channel.IN_APP,

    NotificationCategory.SYSTEM:            Channel.EMAIL | Channel.IN_APP,
    NotificationCategory.COMPLIANCE_ALERT:  Channel.EMAIL | Channel.PUSH | Channel.IN_APP,
    NotificationCategory.WELCOME:           Channel.EMAIL | Channel.IN_APP,
}

MANDATORY_EMAIL_CATEGORIES = frozenset({
    NotificationCategory.SECURITY,
    NotificationCategory.PASSWORD_CHANGED,
    NotificationCategory.TWO_FA_ENABLED,
    NotificationCategory.TWO_FA_DISABLED,
    NotificationCategory.PAYMENT_FAILED,
})


class NotificationPreference(models.Model):
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

    @classmethod
    def get_channels_for(cls, user, category: str) -> int:
        try:
            pref = cls.objects.get(user=user, category=category)
            channels = pref.channels
        except cls.DoesNotExist:
            channels = CATEGORY_DEFAULTS.get(category, Channel.IN_APP)

        if category in MANDATORY_EMAIL_CATEGORIES:
            channels = channels | int(Channel.EMAIL)

        return channels

    def __str__(self) -> str:
        return f"NotifPref({self.user_id} / {self.category} / channels={self.channels})"