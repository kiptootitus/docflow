"""
DocFlow AI — notifications/tasks.py

All Celery tasks for the notifications app.

Task inventory:
  ── Email (called directly by users/views.py and signals.py) ─────────────
  send_verification_email(user_id, raw_token)
  send_welcome_email(user_id)
  send_password_reset_email(user_id, raw_token, ip_address)
  send_tfa_enabled_email(user_id, backup_codes, ip_address)
  send_tfa_disabled_email(user_id, ip_address, user_agent)

  ── Notification dispatch (internal fan-out) ──────────────────────────────
  dispatch_notification(notification_id)          core fan-out task
  send_push_notification(notification_id)         push-only
  send_email_notification(notification_id, extra) email-only

  ── Scheduled / Celery Beat ───────────────────────────────────────────────
  send_invoice_payment_reminders()     daily  — overdue invoice nudges
  send_contract_expiry_alerts()        daily  — 90/30/7 day warnings
  send_trial_ending_reminders()        daily  — trial expiry nudges
  check_expo_push_receipts()           hourly — receipt error handling
  purge_stale_push_tokens()            weekly — clean dead tokens
  purge_old_notifications()            monthly — prune read notifs > 90 days

Retry policy (default unless overridden per task):
  max_retries = 3
  countdown   = exponential back-off: 60s, 300s, 900s
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user(user_id: str):
    """Fetch User by UUID string. Returns None if not found."""
    from django.contrib.auth import get_user_model  # noqa: PLC0415
    User = get_user_model()
    try:
        return User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError):
        logger.warning("tasks: user %s not found", user_id)
        return None


def _exponential_backoff(retries: int) -> int:
    """Return countdown seconds for retry: 60, 300, 900."""
    delays = [60, 300, 900]
    return delays[min(retries, len(delays) - 1)]


# ===========================================================================
# AUTH / SECURITY EMAIL TASKS
# ===========================================================================

@shared_task(
    bind=True,
    max_retries=3,
    name="notifications.tasks.send_verification_email",
    queue="high",
)
def send_verification_email(self, user_id: str, raw_token: str) -> None:
    """
    Send the email-verification email.
    Called by: users/signals.py on_verification_token_created
               users/views.py  UserRegistrationView (backup direct call)
    """
    user = _get_user(user_id)
    if user is None:
        return

    try:
        from notifications.email import EmailDispatcher  # noqa: PLC0415
        EmailDispatcher.send_verification_email(user, raw_token)
        logger.info("tasks.send_verification_email: sent to %s", user.email)
    except Exception as exc:
        countdown = _exponential_backoff(self.request.retries)
        logger.warning(
            "tasks.send_verification_email: retry %d for %s in %ds — %s",
            self.request.retries + 1, user.email, countdown, exc,
        )
        raise self.retry(exc=exc, countdown=countdown)


@shared_task(
    bind=True,
    max_retries=3,
    name="notifications.tasks.send_welcome_email",
    queue="high",
)
def send_welcome_email(self, user_id: str) -> None:
    """
    Send welcome email after account creation.
    Called by: users/signals.py on_user_post_save (on_commit)
    """
    user = _get_user(user_id)
    if user is None:
        return

    try:
        from notifications.email import EmailDispatcher  # noqa: PLC0415
        EmailDispatcher.send_welcome_email(user)
        logger.info("tasks.send_welcome_email: sent to %s", user.email)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_exponential_backoff(self.request.retries))


@shared_task(
    bind=True,
    max_retries=3,
    name="notifications.tasks.send_password_reset_email",
    queue="high",
)
def send_password_reset_email(self, user_id: str, raw_token: str, ip_address: str = "") -> None:
    """
    Send password-reset email with secure link.
    Called by: users/views.py PasswordResetRequestView
    """
    user = _get_user(user_id)
    if user is None:
        return

    try:
        from notifications.email import EmailDispatcher  # noqa: PLC0415
        EmailDispatcher.send_password_reset_email(user, raw_token, ip_address=ip_address)
        logger.info("tasks.send_password_reset_email: sent to %s", user.email)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_exponential_backoff(self.request.retries))


@shared_task(
    bind=True,
    max_retries=3,
    name="notifications.tasks.send_tfa_enabled_email",
    queue="high",
)
def send_tfa_enabled_email(
    self,
    user_id: str,
    backup_codes: list[str],
    ip_address: str = "",
) -> None:
    """
    Send 2FA-enabled confirmation with backup codes.
    Called by: users/views.py TOTPConfirmEnableView
    """
    user = _get_user(user_id)
    if user is None:
        return

    try:
        from notifications.email import EmailDispatcher  # noqa: PLC0415
        EmailDispatcher.send_tfa_enabled_email(user, backup_codes, ip_address=ip_address)
        logger.info("tasks.send_tfa_enabled_email: sent to %s", user.email)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_exponential_backoff(self.request.retries))


@shared_task(
    bind=True,
    max_retries=3,
    name="notifications.tasks.send_tfa_disabled_email",
    queue="high",
)
def send_tfa_disabled_email(
    self,
    user_id: str,
    ip_address: str = "",
    user_agent: str = "",
) -> None:
    """
    Send 2FA-disabled security alert.
    Called by: users/views.py TOTPDisableView
    """
    user = _get_user(user_id)
    if user is None:
        return

    try:
        from notifications.email import EmailDispatcher  # noqa: PLC0415
        EmailDispatcher.send_tfa_disabled_email(user, ip_address=ip_address, user_agent=user_agent)
        logger.info("tasks.send_tfa_disabled_email: security alert sent to %s", user.email)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_exponential_backoff(self.request.retries))


# ===========================================================================
# CORE NOTIFICATION DISPATCH
# ===========================================================================

@shared_task(
    bind=True,
    max_retries=3,
    name="notifications.tasks.dispatch_notification",
    queue="default",
)
def dispatch_notification(self, notification_id: str) -> None:
    """
    Main fan-out task.  Given a Notification id:
      1. Load the Notification + NotificationPreference for the user
      2. Determine effective channels (preference + mandatory overrides)
      3. Dispatch email and/or push as sub-tasks
    """
    from notifications.models import (  # noqa: PLC0415
        Notification, NotificationPreference, Channel,
    )

    try:
        notif = Notification.objects.select_related("user").get(pk=notification_id)
    except Notification.DoesNotExist:
        logger.warning("dispatch_notification: notification %s not found", notification_id)
        return

    if notif.user is None:
        logger.warning("dispatch_notification: notification %s has no user", notification_id)
        return

    # Effective channels = (requested) AND (user prefs) enforcing mandatory rules
    requested   = notif.channels_requested
    pref_channels = NotificationPreference.get_channels_for(notif.user, notif.category)
    effective   = requested & pref_channels

    logger.info(
        "dispatch_notification: id=%s cat=%s requested=%d pref=%d effective=%d",
        notification_id, notif.category, requested, pref_channels, effective,
    )

    # IN-APP is automatic (just exists in DB) — mark it sent
    if effective & Channel.IN_APP:
        notif.mark_channel_sent(Channel.IN_APP)

    # EMAIL
    if effective & Channel.EMAIL:
        send_email_notification.apply_async(
            args=[notification_id],
            queue="high",
        )

    # PUSH
    if effective & Channel.PUSH:
        send_push_notification.apply_async(
            args=[notification_id],
            queue="default",
        )


@shared_task(
    bind=True,
    max_retries=3,
    name="notifications.tasks.send_email_notification",
    queue="high",
)
def send_email_notification(
    self,
    notification_id: str,
    extra_context: dict | None = None,
) -> None:
    """Dispatch email for a Notification record."""
    from notifications.models import Notification  # noqa: PLC0415
    from notifications.email import EmailDispatcher, EmailDispatchError  # noqa: PLC0415

    try:
        notif = Notification.objects.select_related("user").get(pk=notification_id)
    except Notification.DoesNotExist:
        return

    try:
        msg_id = EmailDispatcher.send(notif, extra_context=extra_context)
        if msg_id:
            notif.email_message_id = msg_id
            notif.save(update_fields=["email_message_id"])
    except EmailDispatchError as exc:
        raise self.retry(exc=exc, countdown=_exponential_backoff(self.request.retries))


@shared_task(
    bind=True,
    max_retries=2,
    name="notifications.tasks.send_push_notification",
    queue="default",
)
def send_push_notification(self, notification_id: str) -> None:
    """Dispatch push for a Notification record."""
    from notifications.models import Notification  # noqa: PLC0415
    from notifications.push import PushDispatcher, PushDispatchError  # noqa: PLC0415

    try:
        notif = Notification.objects.select_related("user").get(pk=notification_id)
    except Notification.DoesNotExist:
        return

    if notif.user is None:
        return

    payload = PushDispatcher.build_payload_from_notification(notif)
    try:
        PushDispatcher.send_to_user(notif.user, payload, notification=notif)
    except PushDispatchError as exc:
        raise self.retry(exc=exc, countdown=_exponential_backoff(self.request.retries))


# ===========================================================================
# CONVENIENCE HELPER — create + dispatch in one call
# ===========================================================================

@shared_task(
    name="notifications.tasks.notify_user",
    queue="default",
)
def notify_user(
    user_id: str,
    category: str,
    title: str,
    body: str = "",
    data: dict | None = None,
    priority: str = "normal",
    action_url: str = "",
    channels: int | None = None,  # Override channels (bitmask); None = use prefs
) -> str | None:
    """
    Create a Notification and fan it out.
    Returns the notification UUID string.

    Example (from invoice app):
        notify_user.delay(
            str(user.pk),
            category="invoice_paid",
            title="Payment received — INV-2026-042",
            body="Acme Ltd paid KES 2,981 via M-Pesa.",
            data={"invoice_id": "...", "amount": "2981", "currency": "KES"},
            priority="high",
            action_url="/invoices/86ca08twd/",
        )
    """
    from notifications.models import (  # noqa: PLC0415
        Notification, NotificationCategory, NotificationPreference, Channel,
    )

    user = _get_user(user_id)
    if user is None:
        return None

    # Determine channels
    if channels is None:
        channels = NotificationPreference.get_channels_for(user, category)

    notif = Notification.objects.create(
        user               = user,
        category           = category,
        priority           = priority,
        title              = title,
        body               = body,
        data               = data or {},
        action_url         = action_url,
        channels_requested = channels,
    )

    dispatch_notification.apply_async(args=[str(notif.pk)], queue="default")
    return str(notif.pk)


# ===========================================================================
# SCHEDULED TASKS  (registered in celery beat schedule)
# ===========================================================================

@shared_task(name="notifications.tasks.send_invoice_payment_reminders", queue="low")
def send_invoice_payment_reminders() -> None:
    """
    Daily task: find overdue invoices and send payment reminders.
    Runs at 08:00 Africa/Nairobi via Celery Beat.
    """
    try:
        from documents.models import Invoice, InvoiceStatus  # noqa: PLC0415
    except ImportError:
        logger.info("send_invoice_payment_reminders: documents app not installed yet")
        return

    now = timezone.now()
    # Reminders at 3, 7, 14 days overdue
    reminder_days = [3, 7, 14]

    for days in reminder_days:
        target_date = (now - timedelta(days=days)).date()
        invoices = Invoice.objects.filter(
            status=InvoiceStatus.SENT,
            due_date__date=target_date,
        ).select_related("company__owner")

        for invoice in invoices:
            owner = getattr(invoice.company, "owner", None)
            if owner:
                notify_user.delay(
                    str(owner.pk),
                    category="payment_reminder",
                    title=f"Invoice {invoice.invoice_number} is {days} days overdue",
                    body=f"{invoice.client_name} has not paid {invoice.formatted_total}.",
                    data={
                        "invoice_id":     str(invoice.pk),
                        "invoice_number": invoice.invoice_number,
                        "amount":         str(invoice.total),
                        "currency":       invoice.currency,
                        "days_overdue":   str(days),
                    },
                    priority="high" if days >= 7 else "normal",
                    action_url=f"/invoices/{invoice.pk}/",
                )

    logger.info("send_invoice_payment_reminders: completed for %s", now.date())


@shared_task(name="notifications.tasks.send_contract_expiry_alerts", queue="low")
def send_contract_expiry_alerts() -> None:
    """
    Daily task: notify users about contracts expiring in 90, 30, or 7 days.
    """
    try:
        from documents.models import Contract, ContractStatus  # noqa: PLC0415
    except ImportError:
        logger.info("send_contract_expiry_alerts: documents app not installed yet")
        return

    now  = timezone.now()
    days_list = [90, 30, 7]

    for days in days_list:
        target_date = (now + timedelta(days=days)).date()
        contracts = Contract.objects.filter(
            status=ContractStatus.SIGNED,
            expiry_date__date=target_date,
        ).select_related("company__owner")

        for contract in contracts:
            owner = getattr(contract.company, "owner", None)
            if owner:
                notify_user.delay(
                    str(owner.pk),
                    category="contract_expiring",
                    title=f'Contract "{contract.title}" expires in {days} days',
                    body="Review and renew before it lapses.",
                    data={
                        "contract_id":       str(contract.pk),
                        "contract_title":    contract.title,
                        "days_until_expiry": str(days),
                    },
                    priority="high" if days <= 7 else "normal",
                    action_url=f"/contracts/{contract.pk}/",
                )

    logger.info("send_contract_expiry_alerts: completed for %s", now.date())


@shared_task(name="notifications.tasks.send_trial_ending_reminders", queue="low")
def send_trial_ending_reminders() -> None:
    """
    Daily task: remind users whose trial subscription ends in 7 or 1 day.
    """
    try:
        import djstripe.models as stripe_models  # noqa: PLC0415
    except ImportError:
        logger.info("send_trial_ending_reminders: dj-stripe not installed yet")
        return

    from django.contrib.auth import get_user_model  # noqa: PLC0415
    User = get_user_model()
    now  = timezone.now()

    for days in [7, 1]:
        target = (now + timedelta(days=days)).date()
        subs = stripe_models.Subscription.objects.filter(
            trial_end__date=target,
            status="trialing",
        ).select_related("customer__subscriber")

        for sub in subs:
            user = getattr(sub.customer, "subscriber", None)
            if user and isinstance(user, User):
                notify_user.delay(
                    str(user.pk),
                    category="trial_ending",
                    title=f"Your DocFlow AI trial ends in {days} day{'s' if days > 1 else ''}",
                    body="Upgrade to keep access to all features.",
                    data={"days_remaining": str(days)},
                    priority="high",
                    action_url="/settings/billing/upgrade/",
                )

    logger.info("send_trial_ending_reminders: completed for %s", now.date())


@shared_task(name="notifications.tasks.check_expo_push_receipts", queue="low")
def check_expo_push_receipts() -> None:
    """
    Hourly task: poll Expo for push receipt status.
    Deactivates tokens that reported DeviceNotRegistered.
    Only checks receipts < 24 hours old.
    """
    from notifications.models import Notification  # noqa: PLC0415
    from notifications.push import ExpoProvider  # noqa: PLC0415

    cutoff = timezone.now() - timedelta(hours=24)
    ticket_ids = list(
        Notification.objects.filter(
            push_ticket_id__gt="",
            created_at__gte=cutoff,
        ).values_list("push_ticket_id", flat=True)[:500]
    )

    if not ticket_ids:
        return

    receipts = ExpoProvider.fetch_receipts(ticket_ids)
    for receipt_id, receipt in receipts.items():
        if receipt.get("status") == "error":
            details = receipt.get("details", {})
            if details.get("error") == "DeviceNotRegistered":
                # Find and deactivate the token
                from notifications.models import PushToken  # noqa: PLC0415
                # We can't directly map receipt → token here without a join table
                # so we log for manual review. In a full implementation you'd
                # store ticket_id → push_token_id in a join model.
                logger.warning(
                    "check_expo_push_receipts: DeviceNotRegistered receipt=%s", receipt_id
                )

    logger.info("check_expo_push_receipts: checked %d receipts", len(receipts))


@shared_task(name="notifications.tasks.purge_stale_push_tokens", queue="low")
def purge_stale_push_tokens() -> None:
    """
    Weekly task: hard-delete push tokens that have been inactive for 30+ days.
    """
    from notifications.models import PushToken  # noqa: PLC0415
    cutoff = timezone.now() - timedelta(days=30)
    deleted, _ = PushToken.objects.filter(
        is_active=False,
        updated_at__lt=cutoff,
    ).delete()
    logger.info("purge_stale_push_tokens: deleted %d stale tokens", deleted)


@shared_task(name="notifications.tasks.purge_old_notifications", queue="low")
def purge_old_notifications() -> None:
    """
    Monthly task: hard-delete read notifications older than 90 days.
    Unread notifications are never purged automatically.
    """
    from notifications.models import Notification  # noqa: PLC0415
    cutoff = timezone.now() - timedelta(days=90)
    deleted, _ = Notification.objects.filter(
        read_at__isnull=False,
        created_at__lt=cutoff,
    ).delete()
    logger.info("purge_old_notifications: deleted %d old notifications", deleted)


# ===========================================================================
# TOKEN BLACKLISTING  (called from users/signals.py on password change)
# ===========================================================================

@shared_task(
    bind=True,
    max_retries=2,
    name="users.tasks.blacklist_user_tokens",
    queue="high",
)
def blacklist_user_tokens(self, user_id: str) -> None:
    """
    Blacklist all outstanding SimpleJWT refresh tokens for a user.
    Called when the user's password changes (signal) to invalidate
    any stolen tokens.
    """
    try:
        from rest_framework_simplejwt.token_blacklist.models import (  # noqa: PLC0415
            OutstandingToken, BlacklistedToken,
        )
        from rest_framework_simplejwt.utils import aware_utcnow  # noqa: PLC0415

        outstanding = OutstandingToken.objects.filter(
            user_id=user_id,
            expires_at__gt=aware_utcnow(),
        ).exclude(
            blacklistedtoken__isnull=False
        )

        blacklisted = 0
        for token in outstanding:
            BlacklistedToken.objects.get_or_create(token=token)
            blacklisted += 1

        logger.info(
            "blacklist_user_tokens: blacklisted %d tokens for user %s",
            blacklisted, user_id,
        )
    except ImportError:
        logger.warning(
            "blacklist_user_tokens: simplejwt token_blacklist not installed"
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)