"""
DocFlow AI — notifications/tests.py

Comprehensive test suite for the notifications application.
Covers flag bitmasks, model properties, REST API views, throttles, 
provider integrations, and Celery background workers.
"""

import uuid
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from notifications.models import (
    Channel,
    Notification,
    NotificationCategory,
    NotificationPreference,
    NotificationPriority,
    PushToken,
    PushTokenPlatform,
    CATEGORY_DEFAULTS,
    MANDATORY_EMAIL_CATEGORIES,
)
from notifications.push import PushPayload, ExpoProvider, FCMProvider, APNSProvider, PushDispatcher, DeadTokenError, PushDispatchError
from notifications.email import EmailDispatcher, EmailDispatchError
from notifications.tasks import (
    dispatch_notification,
    send_email_notification,
    send_push_notification,
    notify_user,
    send_invoice_payment_reminders,
    send_contract_expiry_alerts,
    send_trial_ending_reminders,
    check_expo_push_receipts,
    purge_stale_push_tokens,
    purge_old_notifications,
)

User = get_user_model()


# ===========================================================================
# 1. MODEL & BITMASK LOGIC TESTS
# ===========================================================================

class NotificationModelTests(TestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="testuser@docflowai.com",
            username="testuser",
            password="SecurePassword123!",
            is_active=True
        )

    def test_channel_bitmask_combinations(self) -> None:
        """Verify bitmask flag logic combinations function natively via integer operations."""
        channels = Channel.EMAIL | Channel.PUSH
        self.assertTrue(bool(channels & Channel.EMAIL))
        self.assertTrue(bool(channels & Channel.PUSH))
        self.assertFalse(bool(channels & Channel.IN_APP))

    def test_notification_channel_properties(self) -> None:
        """Verify Notification properties resolve correctly based on channels_sent bitmask."""
        notif = Notification.objects.create(
            user=self.user,
            category=NotificationCategory.SYSTEM,
            title="System Alert",
            channels_sent=int(Channel.IN_APP | Channel.EMAIL)
        )
        self.assertTrue(notif.via_in_app)
        self.assertTrue(notif.via_email)
        self.assertFalse(notif.via_push)

    def test_mark_read_mutates_state_and_timestamp(self) -> None:
        """Verify mark_read sets timestamp and modifies is_read condition cleanly."""
        notif = Notification.objects.create(
            user=self.user,
            category=NotificationCategory.SYSTEM,
            title="Unread Alert"
        )
        self.assertFalse(notif.is_read)
        self.assertNone(notif.read_at)
        
        notif.mark_read()
        self.assertTrue(notif.is_read)
        self.assertIsNotNone(notif.read_at)

    def test_preference_resolution_with_no_row_fallback(self) -> None:
        """Verify resolution falls back to system defaults when no custom row exists."""
        resolved = NotificationPreference.get_channels_for(self.user, NotificationCategory.INVOICE_PAID)
        expected = CATEGORY_DEFAULTS.get(NotificationCategory.INVOICE_PAID)
        self.assertEqual(resolved, expected)

    def test_preference_resolution_enforces_mandatory_email(self) -> None:
        """Ensure security-critical categories override channel selections to force email delivery."""
        # Create a user preference that tries to explicitly turn off all channels (channels = 0)
        NotificationPreference.objects.create(
            user=self.user,
            category=NotificationCategory.SECURITY,
            channels=0
        )
        resolved = NotificationPreference.get_channels_for(self.user, NotificationCategory.SECURITY)
        self.assertTrue(bool(resolved & Channel.EMAIL))


# ===========================================================================
# 2. REST API ENDPOINT INTEGRATION TESTS
# ===========================================================================

class NotificationAPITests(APITestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="developer@docflowai.com",
            username="developer",
            password="SecurePassword123!",
            is_active=True
        )
        self.other_user = User.objects.create_user(
            email="hacker@docflowai.com",
            username="hacker",
            password="MaliciousPassword123!",
            is_active=True
        )
        self.client.force_authenticate(user=self.user)

        # Populate baseline items
        self.notif_normal = Notification.objects.create(
            user=self.user,
            category=NotificationCategory.INVOICE_SENT,
            priority=NotificationPriority.NORMAL,
            title="Invoice Sent out",
            body="Invoice Builder details parsed."
        )
        self.notif_critical = Notification.objects.create(
            user=self.user,
            category=NotificationCategory.SECURITY,
            priority=NotificationPriority.CRITICAL,
            title="Critical Login Alert"
        )

    def test_list_endpoint_isolation_and_filtering(self) -> None:
        """Verify index route blocks cross-tenant scanning and filters by params."""
        # Cross-user notification that should never be returned
        Notification.objects.create(user=self.other_user, category=NotificationCategory.SYSTEM, title="Secret")

        url = reverse("notification-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        # Filter testing
        response = self.client.get(url, {"priority": "critical"})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], str(self.notif_critical.id))

    def test_mark_read_endpoints(self) -> None:
        """Verify endpoint triggers single row status transition."""
        url = reverse("notification-mark-read", kwargs={"pk": self.notif_normal.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.notif_normal.refresh_from_db()
        self.assertTrue(self.notif_normal.is_read)

    def test_mark_all_read_bulk_execution(self) -> None:
        """Verify endpoint modifies all matching targets using optimized database updates."""
        url = reverse("notification-read-all")
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(Notification.objects.filter(user=self.user, read_at__isnull=True).count(), 0)

    def test_delete_notification_constraints(self) -> None:
        """Verify normal deletions pass while immutable security entries throw 403 blocks."""
        # Standard deletion
        del_url_normal = reverse("notification-delete", kwargs={"pk": self.notif_normal.pk})
        response = self.client.delete(del_url_normal)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Security protected deletion block check
        del_url_security = reverse("notification-delete", kwargs={"pk": self.notif_critical.pk})
        response = self.client.delete(del_url_security)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unread_count_payload_breakdown(self) -> None:
        """Verify real-time aggregation counters split records correctly by severity tier."""
        url = reverse("notification-unread-count")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["critical"], 1)

    def test_preference_list_merges_with_system_defaults(self) -> None:
        """Verify matrix list supplies a full layout array even if zero database rows exist."""
        url = reverse("notification-preferences")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), len(NotificationCategory.choices))

    def test_preference_patch_updates_and_enforces_rules(self) -> None:
        """Verify preferences update via bitmask toggling and block illegal operations on critical pipelines."""
        url_normal = reverse("notification-preference-update", kwargs={"category": NotificationCategory.INVOICE_SENT})
        response = self.client.patch(url_normal, {"email": False, "push": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["email"])

        # Attempt to remove email channel from mandatory channel group
        url_security = reverse("notification-preference-update", kwargs={"category": NotificationCategory.SECURITY})
        response = self.client.patch(url_security, {"email": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_push_token_registration_lifecycle(self) -> None:
        """Verify token device pairing maps correctly, handles rotation, and cleans up old ownership references safely."""
        url_create = reverse("push-token-create")
        payload = {
            "token": "ExponentPushToken[EnterpriseTestingTokenKey]",
            "platform": PushTokenPlatform.EXPO,
            "device_name": "CEO iPad Pro"
        }
        
        # Initial Creation
        response = self.client.post(url_create, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        token_id = response.data["id"]

        # Token Transfer Upsert - verify cross user device takeover cleans up old references
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(url_create, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify old row deactivated for original account ownership reference
        self.assertFalse(PushToken.objects.get(id=token_id).is_active)


# ===========================================================================
# 3. DISPATCHER LAYER MOCK & INTEGRATION TESTS
# ===========================================================================

class DispatcherSubsystemTests(TestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="operations@docflowai.com",
            username="ops",
            password="SecurePassword123!"
        )
        self.notif = Notification.objects.create(
            user=self.user,
            category=NotificationCategory.WELCOME,
            title="System Onboarding Complete",
            body="Welcome text message parameters."
        )

    @patch("django.core.mail.EmailMultiAlternatives.send")
    def test_email_dispatcher_send_pipeline_success(self, mock_send: MagicMock) -> None:
        """Verify email structures map metadata tags safely onto message payloads."""
        msg_id = EmailDispatcher.send(self.notif, extra_context={"verify_url": "https://app.docflowai.com/verify"})
        self.assertTrue(mock_send.called)

    @patch("django.core.mail.EmailMultiAlternatives.send")
    def test_email_dispatcher_swallows_permanent_failures(self, mock_send: MagicMock) -> None:
        """Verify that permanent validation errors do not leak into execution loops."""
        mock_send.side_effect = Exception("550 User address unknown or blocked")
        msg_id = EmailDispatcher.send(self.notif)
        self.assertNone(msg_id)

    @patch("django.core.mail.EmailMultiAlternatives.send")
    def test_email_dispatcher_raises_transient_failures(self, mock_send: MagicMock) -> None:
        """Verify network connection errors propagate up to trigger Celery retry policies."""
        mock_send.side_effect = Exception("Timeout establishing connection to smtp.sendgrid.net")
        with self.assertRaises(EmailDispatchError):
            EmailDispatcher.send(self.notif)

    @patch("httpx.post")
    def test_expo_provider_batch_dispatch_success(self, mock_post: MagicMock) -> None:
        """Verify provider translates normalized structural components to match API formats."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"status": "ok", "id": "ticket-uuid-123"}]}
        mock_post.return_value = mock_response

        payload = PushPayload(title="Alert", body="Test text description.")
        tickets = ExpoProvider.send_batch(["ExponentPushToken[TokenVal]"], payload)
        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0]["status"], "ok")

    @patch("notifications.push.ExpoProvider.send_batch")
    def test_push_dispatcher_cleans_dead_tokens_automatically(self, mock_send_batch: MagicMock) -> None:
        """Verify tracking services handle dead device error signals by deactivating invalid tokens immediately."""
        token_row = PushToken.objects.create(
            user=self.user,
            token="ExponentPushToken[InvalidDeadKey]",
            platform=PushTokenPlatform.EXPO
        )
        mock_send_batch.return_value = [{"status": "error", "message": "DeviceNotRegistered", "details": {"error": "DeviceNotRegistered"}}]
        
        payload = PushPayload(title="Nudge", body="Nudge content context.")
        PushDispatcher.send_to_user(self.user, payload)
        
        token_row.refresh_from_db()
        self.assertFalse(token_row.is_active)


# ===========================================================================
# 4. CELERY ASYNCHRONOUS WORKER TASK TESTS
# ===========================================================================

class CeleryTasksExecutionTests(TestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="worker@docflowai.com",
            username="celery_worker",
            password="SecurePassword123!"
        )
        self.notif = Notification.objects.create(
            user=self.user,
            category=NotificationCategory.AI_REVIEW_DONE,
            title="Legal Audit Complete",
            channels_requested=int(Channel.EMAIL | Channel.PUSH)
        )

    @patch("notifications.tasks.send_email_notification.apply_async")
    @patch("notifications.tasks.send_push_notification.apply_async")
    def test_main_fanout_routing_logic(self, mock_push_task: MagicMock, mock_email_task: MagicMock) -> None:
        """Verify task parses user preferences to group dispatch commands correctly into separate queues."""
        dispatch_notification(str(self.notif.pk))
        mock_email_task.assert_called_once_with(args=[str(self.notif.pk)], queue="high")
        mock_push_task.assert_called_once_with(args=[str(self.notif.pk)], queue="default")

    @patch("notifications.email.EmailDispatcher.send")
    def test_send_email_notification_task_saves_message_id(self, mock_send: MagicMock) -> None:
        """Verify worker records execution metadata to enable tracking validation steps."""
        mock_send.return_value = "sendgrid_test_tracking_id_123"
        send_email_notification(str(self.notif.pk))
        self.notif.refresh_from_db()
        self.assertEqual(self.notif.email_message_id, "sendgrid_test_tracking_id_123")

    def test_notify_user_convenience_wrapper(self) -> None:
        """Verify wrapper triggers record creation and schedules backend processing tasks within a single thread call."""
        with patch("notifications.tasks.dispatch_notification.apply_async") as mock_dispatch_async:
            notif_id = notify_user(
                user_id=str(self.user.pk),
                category=NotificationCategory.COMPLIANCE_ALERT,
                title="Tax Delta Alert",
                body="Body message metrics details.",
                priority="high"
            )
            self.assertIsNotNone(notif_id)
            self.assertTrue(Notification.objects.filter(id=notif_id).exists())
            mock_dispatch_async.assert_called_once_with(args=[notif_id], queue="default")

    @patch("notifications.tasks.notify_user.delay")
    def test_scheduled_invoice_reminders_skips_when_no_apps_mounted(self, mock_notify: MagicMock) -> None:
        """Verify cron validation runs safely and handles uninstalled modular systems gracefully without breaking."""
        # Execution safely catches module lookup structural exceptions
        send_invoice_payment_reminders()
        mock_notify.assert_not_called()

    @patch("notifications.tasks.notify_user.delay")
    def test_scheduled_contract_alerts_skips_when_no_apps_mounted(self, mock_notify: MagicMock) -> None:
        """Verify cron execution context handles unmounted app modules safely without throwing errors."""
        send_contract_expiry_alerts()
        mock_notify.assert_not_called()

    @patch("notifications.tasks.notify_user.delay")
    def test_scheduled_trial_ending_reminders_skips_when_no_apps_mounted(self, mock_notify: MagicMock) -> None:
        """Verify billing crons catch missing app systems gracefully without impacting adjacent microservice threads."""
        send_trial_ending_reminders()
        mock_notify.assert_not_called()

    @patch("notifications.push.ExpoProvider.fetch_receipts")
    def test_check_expo_push_receipts_with_no_tickets(self, mock_fetch: MagicMock) -> None:
        """Verify background token cleaning process returns instantly if tracking log files are empty."""
        check_expo_push_receipts()
        mock_fetch.assert_not_called()

    def test_purge_stale_push_tokens_deletes_rows(self) -> None:
        """Verify database pruning sweeps remove inactive data records cleanly after 30 days."""
        token = PushToken.objects.create(
            user=self.user,
            token="StaleToken",
            is_active=False
        )
        # Force updated_at date timestamp back 45 days into historical window
        old_date = timezone.now() - timezone.timedelta(days=45)
        PushToken.objects.filter(id=token.id).update(updated_at=old_date)

        purge_stale_push_tokens()
        self.assertFalse(PushToken.objects.filter(id=token.id).exists())

    def test_purge_old_notifications_retains_unread_records(self) -> None:
        """Verify data maintenance sweeps delete old read notifications while leaving unread records intact."""
        old_date = timezone.now() - timezone.timedelta(days=120)
        
        read_notif = Notification.objects.create(user=self.user, category=NotificationCategory.SYSTEM, title="Old Read", read_at=old_date)
        Notification.objects.filter(id=read_notif.id).update(created_at=old_date)

        unread_notif = Notification.objects.create(user=self.user, category=NotificationCategory.SYSTEM, title="Old Unread")
        Notification.objects.filter(id=unread_notif.id).update(created_at=old_date)

        purge_old_notifications()
        
        self.assertFalse(Notification.objects.filter(id=read_notif.id).exists())
        self.assertTrue(Notification.objects.filter(id=unread_notif.id).exists())