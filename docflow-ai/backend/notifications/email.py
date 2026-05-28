"""
DocFlow AI — notifications/email.py

Email delivery layer using Django Anymail + SendGrid.

Architecture:
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  EmailDispatcher                                                         │
  │    Central class.  Called by tasks.py.                                   │
  │    Renders the right HTML template, builds the Anymail message,          │
  │    sends it, and records the SendGrid message-id on the Notification.    │
  │                                                                          │
  │  Template registry                                                       │
  │    Maps NotificationCategory → (subject_template, html_template_path)   │
  │    All HTML templates live in notifications/templates/notifications/     │
  │                                                                          │
  │  Retry policy                                                            │
  │    Hard failures raise EmailDispatchError so Celery can retry the task.  │
  │    Soft failures (bad address, spam block) are logged and swallowed.     │
  └──────────────────────────────────────────────────────────────────────────┘

Required Django settings:
    EMAIL_BACKEND      = "anymail.backends.sendgrid.EmailBackend"
    ANYMAIL            = {"SENDGRID_API_KEY": "<key>"}
    DEFAULT_FROM_EMAIL = "DocFlow AI <hello@docflowai.com>"
    FRONTEND_URL       = "https://app.docflowai.com"
    SUPPORT_URL        = "https://support.docflowai.com"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class EmailDispatchError(Exception):
    """Raised for transient failures — Celery will retry the task."""


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EmailTemplate:
    subject: str
    html_template: str             # path inside templates/
    txt_template:  str | None = None  # optional plain-text override


# Maps NotificationCategory value → EmailTemplate
TEMPLATE_REGISTRY: dict[str, EmailTemplate] = {
    # ── Auth ──────────────────────────────────────────────────────────
    "welcome": EmailTemplate(
        subject="Welcome to DocFlow AI — verify your email",
        html_template="notifications/email_welcome.html",
    ),
    "security": EmailTemplate(
        subject="⚠️ Security alert on your DocFlow AI account",
        html_template="notifications/email_security_alert.html",
    ),
    "password_changed": EmailTemplate(
        subject="Your DocFlow AI password was changed",
        html_template="notifications/email_password_reset.html",
    ),
    "two_fa_enabled": EmailTemplate(
        subject="✓ Two-factor authentication enabled — DocFlow AI",
        html_template="notifications/email_tfa_enabled.html",
    ),
    "two_fa_disabled": EmailTemplate(
        subject="⚠️ Two-factor authentication removed — DocFlow AI",
        html_template="notifications/email_tfa_disabled.html",
    ),
    "new_login": EmailTemplate(
        subject="New sign-in to your DocFlow AI account",
        html_template="notifications/email_new_login.html",
    ),

    # ── Invoices ──────────────────────────────────────────────────────
    "invoice_sent": EmailTemplate(
        subject="Invoice sent — {{ invoice_number }}",
        html_template="notifications/email_invoice_sent.html",
    ),
    "invoice_paid": EmailTemplate(
        subject="🎉 Payment received — {{ invoice_number }}",
        html_template="notifications/email_invoice_paid.html",
    ),
    "invoice_overdue": EmailTemplate(
        subject="⚠️ Invoice overdue — {{ invoice_number }}",
        html_template="notifications/email_invoice_overdue.html",
    ),
    "payment_reminder": EmailTemplate(
        subject="Friendly reminder: Invoice {{ invoice_number }} is due soon",
        html_template="notifications/email_payment_reminder.html",
    ),
    "payment_received": EmailTemplate(
        subject="Payment of {{ amount }} received",
        html_template="notifications/email_payment_received.html",
    ),

    # ── Contracts ─────────────────────────────────────────────────────
    "contract_signed": EmailTemplate(
        subject="✓ Contract signed — {{ contract_title }}",
        html_template="notifications/email_contract_signed.html",
    ),
    "contract_expiring": EmailTemplate(
        subject="⏱ Contract expiring in {{ days_until_expiry }} days",
        html_template="notifications/email_contract_expiring.html",
    ),
    "ai_review_done": EmailTemplate(
        subject="AI contract review complete — {{ contract_title }}",
        html_template="notifications/email_ai_review.html",
    ),

    # ── Billing ───────────────────────────────────────────────────────
    "payment_failed": EmailTemplate(
        subject="Action required: Payment failed on your DocFlow AI account",
        html_template="notifications/email_payment_failed.html",
    ),
    "trial_ending": EmailTemplate(
        subject="Your DocFlow AI trial ends in {{ days_remaining }} days",
        html_template="notifications/email_trial_ending.html",
    ),
    "subscription_cancelled": EmailTemplate(
        subject="Your DocFlow AI subscription has been cancelled",
        html_template="notifications/email_subscription_cancelled.html",
    ),
    "compliance_alert": EmailTemplate(
        subject="🔴 Compliance alert — action required",
        html_template="notifications/email_compliance_alert.html",
    ),
}


# ---------------------------------------------------------------------------
# Base context — injected into every template
# ---------------------------------------------------------------------------

def _base_context(user=None) -> dict[str, Any]:
    """Context variables available in every email template."""
    from django.utils.formats import date_format  # noqa: PLC0415
    return {
        "year":           timezone.now().year,
        "app_name":       "DocFlow AI",
        "app_url":        getattr(settings, "FRONTEND_URL", "https://app.docflowai.com"),
        "support_url":    getattr(settings, "SUPPORT_URL", "https://support.docflowai.com"),
        "unsubscribe_url": getattr(settings, "UNSUBSCRIBE_URL", "https://app.docflowai.com/unsubscribe"),
        "settings_url":   getattr(settings, "FRONTEND_URL", "https://app.docflowai.com") + "/settings/security",
        "enable_2fa_url": getattr(settings, "FRONTEND_URL", "https://app.docflowai.com") + "/settings/security#2fa",
        "security_url":   getattr(settings, "FRONTEND_URL", "https://app.docflowai.com") + "/settings/security",
        # User fields (safe defaults if user is None)
        "first_name": getattr(user, "first_name", "") or "there",
        "last_name":  getattr(user, "last_name", ""),
        "email":      getattr(user, "email", ""),
        "full_name":  getattr(user, "full_name", "") if user else "",
    }


# ---------------------------------------------------------------------------
# Subject renderer — supports simple {{ var }} interpolation in subjects
# ---------------------------------------------------------------------------

def _render_subject(template: str, context: dict) -> str:
    """
    Render a subject string that may contain {{ variable }} placeholders.
    Uses a minimal string-format approach — subjects are short and safe.
    """
    try:
        from django.template import Context, Template  # noqa: PLC0415
        return Template(template).render(Context(context))
    except Exception:
        return template  # Fall back to raw template on error


# ---------------------------------------------------------------------------
# EmailDispatcher
# ---------------------------------------------------------------------------

class EmailDispatcher:
    """
    Sends a single email for a given Notification.

    Usage (called from tasks.py):
        EmailDispatcher.send(notification, extra_context={...})

    Returns the SendGrid message-id string on success,
    or raises EmailDispatchError on transient failures.
    """

    @classmethod
    def send(
        cls,
        notification,                      # notifications.models.Notification
        extra_context: dict | None = None,
        to_email: str | None = None,       # override recipient (e.g. verification emails)
    ) -> str | None:
        """
        Render, build, and send the email for the given notification.
        Returns SendGrid message-id on success, None if silently skipped.
        """
        category = notification.category
        user     = notification.user

        template_def = TEMPLATE_REGISTRY.get(category)
        if template_def is None:
            logger.warning(
                "EmailDispatcher: no template registered for category '%s' — skipping.",
                category,
            )
            return None

        # Build context
        ctx = _base_context(user)
        ctx.update(extra_context or {})
        ctx.update({
            "notification": notification,
            "title":        notification.title,
            "body":         notification.body,
            "data":         notification.data,
        })

        subject = _render_subject(template_def.subject, ctx)

        # Render HTML
        try:
            html_body = render_to_string(template_def.html_template, ctx)
        except Exception as exc:
            logger.exception(
                "EmailDispatcher: template render failed for '%s': %s",
                template_def.html_template, exc,
            )
            raise EmailDispatchError(
                f"Template render failed: {template_def.html_template}"
            ) from exc

        # Plain-text fallback
        if template_def.txt_template:
            try:
                txt_body = render_to_string(template_def.txt_template, ctx)
            except Exception:
                txt_body = cls._html_to_plain(html_body)
        else:
            txt_body = cls._html_to_plain(html_body)

        recipient = to_email or (user.email if user else None)
        if not recipient:
            logger.warning(
                "EmailDispatcher: no recipient for notification %s — skipping.", notification.pk
            )
            return None

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "DocFlow AI <hello@docflowai.com>")

        # Build message
        msg = EmailMultiAlternatives(
            subject   = subject,
            body      = txt_body,
            from_email= from_email,
            to        = [recipient],
        )
        msg.attach_alternative(html_body, "text/html")

        # Anymail-specific metadata for SendGrid
        try:
            msg.esp_extra = {
                "categories": [category, "docflow-ai"],
                "custom_args": {
                    "notification_id": str(notification.pk),
                    "user_id":         str(user.pk) if user else "",
                    "category":        category,
                },
            }
        except Exception:
            pass  # esp_extra is best-effort

        # Send
        try:
            msg.send(fail_silently=False)
        except Exception as exc:
            error_str = str(exc).lower()

            # Permanent failures — don't retry (bad address, spam block)
            if any(kw in error_str for kw in ["550", "invalid email", "unsubscribed", "bounce"]):
                logger.warning(
                    "EmailDispatcher: permanent failure for %s (%s): %s",
                    recipient, category, exc,
                )
                return None

            # Transient failure — raise so Celery retries
            logger.exception(
                "EmailDispatcher: transient failure for %s (%s): %s",
                recipient, category, exc,
            )
            raise EmailDispatchError(str(exc)) from exc

        # Extract message-id from Anymail response
        message_id: str = ""
        try:
            message_id = msg.anymail_status.message_id or ""
        except AttributeError:
            pass

        logger.info(
            "EmailDispatcher: sent category='%s' to='%s' message_id='%s'",
            category, recipient, message_id,
        )
        return message_id

    # ── Convenience senders (called directly by tasks.py) ─────────────

    @classmethod
    def send_verification_email(cls, user, raw_token: str) -> None:
        """Send the email-verification email (called from tasks.send_verification_email)."""
        verify_url = (
            f"{getattr(settings, 'FRONTEND_URL', 'https://app.docflowai.com')}"
            f"/verify-email?token={raw_token}"
        )
        from notifications.models import Notification, NotificationCategory  # noqa: PLC0415
        notif = Notification.objects.create(
            user=user,
            category=NotificationCategory.WELCOME,
            title="Verify your DocFlow AI email address",
            body="Click the link in this email to verify your address.",
            channels_requested=2,  # EMAIL only
        )
        msg_id = cls.send(notif, extra_context={"verify_url": verify_url})
        if msg_id:
            notif.email_message_id = msg_id
            notif.mark_channel_sent(2)  # Channel.EMAIL
            notif.save(update_fields=["email_message_id", "channels_sent"])

    @classmethod
    def send_welcome_email(cls, user) -> None:
        """Send the welcome email after email is verified."""
        verify_url = (
            f"{getattr(settings, 'FRONTEND_URL', 'https://app.docflowai.com')}/dashboard"
        )
        from notifications.models import Notification, NotificationCategory  # noqa: PLC0415
        notif = Notification.objects.create(
            user=user,
            category=NotificationCategory.WELCOME,
            title=f"Welcome to DocFlow AI, {user.first_name}!",
            body="Your account is ready. Start by setting up your company.",
            channels_requested=2,  # EMAIL only
        )
        msg_id = cls.send(notif, extra_context={"verify_url": verify_url})
        if msg_id:
            notif.email_message_id = msg_id
            notif.mark_channel_sent(2)
            notif.save(update_fields=["email_message_id", "channels_sent"])

    @classmethod
    def send_password_reset_email(cls, user, raw_token: str, ip_address: str = "") -> None:
        """Send the password reset email."""
        reset_url = (
            f"{getattr(settings, 'FRONTEND_URL', 'https://app.docflowai.com')}"
            f"/password-reset/confirm?token={raw_token}"
        )
        from notifications.models import Notification, NotificationCategory  # noqa: PLC0415
        notif = Notification.objects.create(
            user=user,
            category=NotificationCategory.PASSWORD_CHANGED,
            priority="high",
            title="Reset your DocFlow AI password",
            body="A password reset was requested for your account.",
            channels_requested=2,
        )
        msg_id = cls.send(notif, extra_context={
            "reset_url":    reset_url,
            "requested_at": timezone.now().strftime("%d %b %Y at %H:%M UTC"),
            "ip_address":   ip_address or "Unknown",
        })
        if msg_id:
            notif.email_message_id = msg_id
            notif.mark_channel_sent(2)
            notif.save(update_fields=["email_message_id", "channels_sent"])

    @classmethod
    def send_tfa_enabled_email(cls, user, backup_codes: list[str], ip_address: str = "") -> None:
        """Send 2FA-enabled confirmation with backup codes."""
        from notifications.models import Notification, NotificationCategory  # noqa: PLC0415
        notif = Notification.objects.create(
            user=user,
            category=NotificationCategory.TWO_FA_ENABLED,
            priority="high",
            title="Two-factor authentication enabled",
            body="2FA has been activated on your account.",
            channels_requested=2,
        )
        # Build backup_code_N context vars for template
        code_ctx = {f"backup_code_{i+1}": code for i, code in enumerate(backup_codes[:8])}
        msg_id = cls.send(notif, extra_context={
            "backup_codes": backup_codes,
            **code_ctx,
            "enabled_at": timezone.now().strftime("%d %b %Y at %H:%M UTC"),
            "ip_address": ip_address or "Unknown",
        })
        if msg_id:
            notif.email_message_id = msg_id
            notif.mark_channel_sent(2)
            notif.save(update_fields=["email_message_id", "channels_sent"])

    @classmethod
    def send_tfa_disabled_email(cls, user, ip_address: str = "", user_agent: str = "") -> None:
        """Send 2FA-disabled security alert."""
        from notifications.models import Notification, NotificationCategory  # noqa: PLC0415
        notif = Notification.objects.create(
            user=user,
            category=NotificationCategory.TWO_FA_DISABLED,
            priority="critical",
            title="Two-factor authentication was disabled",
            body="2FA has been turned off on your account.",
            channels_requested=6,  # EMAIL | PUSH
        )
        msg_id = cls.send(notif, extra_context={
            "disabled_at": timezone.now().strftime("%d %b %Y at %H:%M UTC"),
            "ip_address":  ip_address or "Unknown",
            "user_agent":  (user_agent or "Unknown")[:120],
            "enable_2fa_url": (
                f"{getattr(settings, 'FRONTEND_URL', 'https://app.docflowai.com')}"
                f"/settings/security#2fa"
            ),
            "security_url": (
                f"{getattr(settings, 'FRONTEND_URL', 'https://app.docflowai.com')}"
                f"/settings/security"
            ),
        })
        if msg_id:
            notif.email_message_id = msg_id
            notif.mark_channel_sent(2)
            notif.save(update_fields=["email_message_id", "channels_sent"])

    # ── Internal helpers ──────────────────────────────────────────────

    @staticmethod
    def _html_to_plain(html: str) -> str:
        """
        Very lightweight HTML → plain text converter.
        Used as fallback when no .txt template exists.
        Strips tags, collapses whitespace.
        """
        import re  # noqa: PLC0415
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text