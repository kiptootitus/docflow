"""
DocFlow AI — notifications/email.py
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


class EmailDispatchError(Exception):
    pass


@dataclass(frozen=True)
class EmailTemplate:
    subject: str
    html_template: str
    txt_template:  str | None = None


TEMPLATE_REGISTRY: dict[str, EmailTemplate] = {
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


def _base_context(user=None) -> dict[str, Any]:
    return {
        "year":           timezone.now().year,
        "app_name":       "DocFlow AI",
        "app_url":        getattr(settings, "FRONTEND_URL", "https://app.docflowai.com"),
        "support_url":    getattr(settings, "SUPPORT_URL", "https://support.docflowai.com"),
        "unsubscribe_url": getattr(settings, "UNSUBSCRIBE_URL", "https://app.docflowai.com/unsubscribe"),
        "settings_url":   getattr(settings, "FRONTEND_URL", "https://app.docflowai.com") + "/settings/security",
        "enable_2fa_url": getattr(settings, "FRONTEND_URL", "https://app.docflowai.com") + "/settings/security#2fa",
        "security_url":   getattr(settings, "FRONTEND_URL", "https://app.docflowai.com") + "/settings/security",
        "first_name": getattr(user, "first_name", "") or "there",
        "last_name":  getattr(user, "last_name", ""),
        "email":      getattr(user, "email", ""),
        "full_name":  getattr(user, "full_name", "") if user else "",
    }


def _render_subject(template: str, context: dict) -> str:
    try:
        from django.template import Context, Template
        return Template(template).render(Context(context))
    except Exception:
        return template


class EmailDispatcher:

    @classmethod
    def send(
        cls,
        notification,
        extra_context: dict | None = None,
        to_email: str | None = None,
    ) -> str | None:
        category = notification.category
        user     = notification.user

        template_def = TEMPLATE_REGISTRY.get(category)
        if template_def is None:
            logger.warning("EmailDispatcher: no template registered for category '%s'.", category)
            return None

        ctx = _base_context(user)
        ctx.update(extra_context or {})
        ctx.update({
            "notification": notification,
            "title":        notification.title,
            "body":         notification.body,
            "data":         notification.data,
        })

        subject = _render_subject(template_def.subject, ctx)

        try:
            html_body = render_to_string(template_def.html_template, ctx)
        except Exception as exc:
            logger.exception("EmailDispatcher: template render failed for '%s': %s", template_def.html_template, exc)
            raise EmailDispatchError(f"Template render failed: {template_def.html_template}") from exc

        if template_def.txt_template:
            try:
                txt_body = render_to_string(template_def.txt_template, ctx)
            except Exception:
                txt_body = cls._html_to_plain(html_body)
        else:
            txt_body = cls._html_to_plain(html_body)

        recipient = to_email or (user.email if user else None)
        if not recipient:
            logger.warning("EmailDispatcher: no recipient for notification %s.", notification.pk)
            return None

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "DocFlow AI <hello@docflowai.com>")

        msg = EmailMultiAlternatives(
            subject   = subject,
            body      = txt_body,
            from_email= from_email,
            to        = [recipient],
        )
        msg.attach_alternative(html_body, "text/html")

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
            pass

        try:
            msg.send(fail_silently=False)
        except Exception as exc:
            error_str = str(exc).lower()
            if any(kw in error_str for kw in ["550", "invalid email", "unsubscribed", "bounce"]):
                logger.warning("EmailDispatcher: permanent failure for %s (%s): %s", recipient, category, exc)
                return None

            logger.exception("EmailDispatcher: transient failure for %s (%s): %s", recipient, category, exc)
            raise EmailDispatchError(str(exc)) from exc

        message_id: str = ""
        try:
            message_id = msg.anymail_status.message_id or ""
        except AttributeError:
            pass

        logger.info("EmailDispatcher: sent category='%s' to='%s' message_id='%s'", category, recipient, message_id)
        return message_id

    @classmethod
    def send_verification_email(cls, user, raw_token: str) -> None:
        verify_url = f"{getattr(settings, 'FRONTEND_URL', 'https://app.docflowai.com')}/verify-email?token={raw_token}"
        from notifications.models import Notification, NotificationCategory
        notif = Notification.objects.create(
            user=user,
            category=NotificationCategory.WELCOME,
            title="Verify your DocFlow AI email address",
            body="Click the link in this email to verify your address.",
            channels_requested=2,
        )
        msg_id = cls.send(notif, extra_context={"verify_url": verify_url})
        if msg_id:
            notif.email_message_id = msg_id
            notif.mark_channel_sent(2)
            notif.save(update_fields=["email_message_id", "channels_sent"])

    @classmethod
    def send_welcome_email(cls, user) -> None:
        verify_url = f"{getattr(settings, 'FRONTEND_URL', 'https://app.docflowai.com')}/dashboard"
        from notifications.models import Notification, NotificationCategory
        notif = Notification.objects.create(
            user=user,
            category=NotificationCategory.WELCOME,
            title=f"Welcome to DocFlow AI, {user.first_name}!",
            body="Your account is ready. Start by setting up your company.",
            channels_requested=2,
        )
        msg_id = cls.send(notif, extra_context={"verify_url": verify_url})
        if msg_id:
            notif.email_message_id = msg_id
            notif.mark_channel_sent(2)
            notif.save(update_fields=["email_message_id", "channels_sent"])

    @classmethod
    def send_password_reset_email(cls, user, raw_token: str, ip_address: str = "") -> None:
        reset_url = f"{getattr(settings, 'FRONTEND_URL', 'https://app.docflowai.com')}/password-reset/confirm?token={raw_token}"
        from notifications.models import Notification, NotificationCategory
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
        from notifications.models import Notification, NotificationCategory
        notif = Notification.objects.create(
            user=user,
            category=NotificationCategory.TWO_FA_ENABLED,
            priority="high",
            title="Two-factor authentication enabled",
            body="2FA has been activated on your account.",
            channels_requested=2,
        )
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
        from notifications.models import Notification, NotificationCategory
        notif = Notification.objects.create(
            user=user,
            category=NotificationCategory.TWO_FA_DISABLED,
            priority="critical",
            title="Two-factor authentication was disabled",
            body="2FA has been turned off on your account.",
            channels_requested=6,
        )
        msg_id = cls.send(notif, extra_context={
            "disabled_at": timezone.now().strftime("%d %b %Y at %H:%M UTC"),
            "ip_address":  ip_address or "Unknown",
            "user_agent":  (user_agent or "Unknown")[:120],
            "enable_2fa_url": f"{getattr(settings, 'FRONTEND_URL', 'https://app.docflowai.com')}/settings/security#2fa",
            "security_url": f"{getattr(settings, 'FRONTEND_URL', 'https://app.docflowai.com')}/settings/security",
        })
        if msg_id:
            notif.email_message_id = msg_id
            notif.mark_channel_sent(2)
            notif.save(update_fields=["email_message_id", "channels_sent"])

    @staticmethod
    def _html_to_plain(html: str) -> str:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        return re.sub(r"\s+", " ", text).strip()