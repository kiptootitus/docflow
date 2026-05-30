"""
DocFlow AI — notifications/tasks.py
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_user(user_id: str):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        return User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError):
        return None


def _exponential_backoff(retries: int) -> int:
    delays = [60, 300, 900]
    return delays[min(retries, len(delays) - 1)]


@shared_task(bind=True, max_retries=3, name="notifications.tasks.send_verification_email", queue="high")
def send_verification_email(self, user_id: str, raw_token: str) -> None:
    user = _get_user(user_id)
    if not user: return
    try:
        from notifications.email import EmailDispatcher
        EmailDispatcher.send_verification_email(user, raw_token)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_exponential_backoff(self.request.retries))


@shared_task(bind=True, max_retries=3, name="notifications.tasks.send_welcome_email", queue="high")
def send_welcome_email(self, user_id: str) -> None:
    user = _get_user(user_id)
    if not user: return
    try:
        from notifications.email import EmailDispatcher
        EmailDispatcher.send_welcome_email(user)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_exponential_backoff(self.request.retries))


@shared_task(bind=True, max_retries=3, name="notifications.tasks.send_password_reset_email", queue="high")
def send_password_reset_email(self, user_id: str, raw_token: str, ip_address: str = "") -> None:
    user = _get_user(user_id)
    if not user: return
    try:
        from notifications.email import EmailDispatcher
        EmailDispatcher.send_password_reset_email(user, raw_token, ip_address=ip_address)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_exponential_backoff(self.request.retries))


@shared_task(bind=True, max_retries=3, name="notifications.tasks.send_tfa_enabled_email", queue="high")
def send_tfa_enabled_email(self, user_id: str, backup_codes: list[str], ip_address: str = "") -> None:
    user = _get_user(user_id)
    if not user: return
    try:
        from notifications.email import EmailDispatcher
        EmailDispatcher.send_tfa_enabled_email(user, backup_codes, ip_address=ip_address)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_exponential_backoff(self.request.retries))


@shared_task(bind=True, max_retries=3, name="notifications.tasks.send_tfa_disabled_email", queue="high")
def send_tfa_disabled_email(self, user_id: str, ip_address: str = "", user_agent: str = "") -> None:
    user = _get_user(user_id)
    if not user: return
    try:
        from notifications.email import EmailDispatcher
        EmailDispatcher.send_tfa_disabled_email(user, ip_address=ip_address, user_agent=user_agent)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_exponential_backoff(self.request.retries))


@shared_task(bind=True, max_retries=3, name="notifications.tasks.dispatch_notification", queue="default")
def dispatch_notification(self, notification_id: str) -> None:
    from notifications.models import Notification, NotificationPreference, Channel

    try:
        notif = Notification.objects.select_related("user").get(pk=notification_id)
    except Notification.DoesNotExist:
        return

    if not notif.user:
        return

    requested = notif.channels_requested
    pref_channels = NotificationPreference.get_channels_for(notif.user, notif.category)
    effective = requested & pref_channels

    if effective & Channel.IN_APP:
        notif.mark_channel_sent(Channel.IN_APP)

    if effective & Channel.EMAIL:
        send_email_notification.apply_async(args=[notification_id], queue="high")

    if effective & Channel.PUSH:
        send_push_notification.apply_async(args=[notification_id], queue="default")


@shared_task(bind=True, max_retries=3, name="notifications.tasks.send_email_notification", queue="high")
def send_email_notification(self, notification_id: str, extra_context: dict | None = None) -> None:
    from notifications.models import Notification
    from notifications.email import EmailDispatcher, EmailDispatchError

    try:
        notif = Notification.objects.select_related("user").get(pk=notification_id)
    except Notification.DoesNotExist:
        return

    try:
        msg_id = EmailDispatcher.send(notif, extra_context=extra_context)
        if msg_id:
            notif.email_message_id = msg_id
            notif.mark_channel_sent(2)
    except EmailDispatchError as exc:
        raise self.retry(exc=exc, countdown=_exponential_backoff(self.request.retries))


@shared_task(bind=True, max_retries=2, name="notifications.tasks.send_push_notification", queue="default")
def send_push_notification(self, notification_id: str) -> None:
    from notifications.models import Notification
    from notifications.push import PushDispatcher, PushDispatchError

    try:
        notif = Notification.objects.select_related("user").get(pk=notification_id)
    except Notification.DoesNotExist:
        return

    if not notif.user:
        return

    payload = PushDispatcher.build_payload_from_notification(notif)
    try:
        PushDispatcher.send_to_user(notif.user, payload, notification=notif)
    except PushDispatchError as exc:
        raise self.retry(exc=exc, countdown=_exponential_backoff(self.request.retries))


@shared_task(name="notifications.tasks.notify_user", queue="default")
def notify_user(
    user_id: str,
    category: str,
    title: str,
    body: str = "",
    data: dict | None = None,
    priority: str = "normal",
    action_url: str = "",
    channels: int | None = None,
) -> str | None:
    from notifications.models import Notification, NotificationPreference

    user = _get_user(user_id)
    if not user:
        return None

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


@shared_task(name="notifications.tasks.send_invoice_payment_reminders", queue="low")
def send_invoice_payment_reminders() -> None:
    try:
        from documents.models import Invoice, InvoiceStatus
    except ImportError:
        return

    now = timezone.now()
    for days in [3, 7, 14]:
        target_date = (now - timedelta(days=days)).date()
        invoices = Invoice.objects.filter(status=InvoiceStatus.SENT, due_date__date=target_date).select_related("company__owner")

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


@shared_task(name="notifications.tasks.send_contract_expiry_alerts", queue="low")
def send_contract_expiry_alerts() -> None:
    try:
        from documents.models import Contract, ContractStatus
    except ImportError:
        return

    now = timezone.now()
    for days in [90, 30, 7]:
        target_date = (now + timedelta(days=days)).date()
        contracts = Contract.objects.filter(status=ContractStatus.SIGNED, expiry_date__date=target_date).select_related("company__owner")

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


@shared_task(name="notifications.tasks.send_trial_ending_reminders", queue="low")
def send_trial_ending_reminders() -> None:
    try:
        import djstripe.models as stripe_models
    except ImportError:
        return

    from django.contrib.auth import get_user_model
    User = get_user_model()
    now  = timezone.now()

    for days in [7, 1]:
        target = (now + timedelta(days=days)).date()
        subs = stripe_models.Subscription.objects.filter(trial_end__date=target, status="trialing").select_related("customer__subscriber")

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


@shared_task(name="notifications.tasks.check_expo_push_receipts", queue="low")
def check_expo_push_receipts() -> None:
    from notifications.models import Notification, PushToken
    from notifications.push import ExpoProvider

    cutoff = timezone.now() - timedelta(hours=24)
    notifications = Notification.objects.filter(push_ticket_id__gt="", created_at__gte=cutoff)[:500]
    ticket_map = {n.push_ticket_id: n for n in notifications if n.push_ticket_id}

    if not ticket_map:
        return

    receipts = ExpoProvider.fetch_receipts(list(ticket_map.keys()))
    for ticket_id, receipt in receipts.items():
        if receipt.get("status") == "error" and receipt.get("details", {}).get("error") == "DeviceNotRegistered":
            target_notif = ticket_map.get(ticket_id)
            if target_notif and target_notif.user_id:
                PushToken.objects.filter(user_id=target_notif.user_id, platform="expo").update(is_active=False)


@shared_task(name="notifications.tasks.purge_stale_push_tokens", queue="low")
def purge_stale_push_tokens() -> None:
    from notifications.models import PushToken
    cutoff = timezone.now() - timedelta(days=30)
    PushToken.objects.filter(is_active=False, updated_at__lt=cutoff).delete()


@shared_task(name="notifications.tasks.purge_old_notifications", queue="low")
def purge_old_notifications() -> None:
    from notifications.models import Notification
    cutoff = timezone.now() - timedelta(days=90)
    Notification.objects.filter(read_at__isnull=False, created_at__lt=cutoff).delete()


@shared_task(bind=True, max_retries=2, name="users.tasks.blacklist_user_tokens", queue="high")
def blacklist_user_tokens(self, user_id: str) -> None:
    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        from rest_framework_simplejwt.utils import aware_utcnow

        outstanding = OutstandingToken.objects.filter(user_id=user_id, expires_at__gt=aware_utcnow()).exclude(blacklistedtoken__isnull=False)
        for token in outstanding:
            BlacklistedToken.objects.get_or_create(token=token)
    except ImportError:
        pass
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
    
@shared_task(name="notifications.tasks.send_alert_notification", queue="high")
def send_alert_notification(alert_id: str) -> None:
    """Send revenue alert notification"""
    from notifications.models import Notification
    from analytics.models import RevenueAlert  # if needed

    try:
        alert = RevenueAlert.objects.get(pk=alert_id)
    except RevenueAlert.DoesNotExist:
        return

    # Create in-app + email notification
    notify_user.delay(
        user_id=str(alert.user.pk) if hasattr(alert, 'user') and alert.user else str(alert.company.owner.pk),
        category="revenue_alert",
        title=alert.title,
        body=alert.message or alert.description,
        data={
            "alert_id": str(alert.pk),
            "alert_type": alert.alert_type,
            "current_value": str(alert.current_value),
            "threshold": str(alert.threshold),
        },
        priority="high",
        action_url="/analytics/alerts/",
    )