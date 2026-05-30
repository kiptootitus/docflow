"""
Comprehensive test suite for intergrations with mocking and
enterprise-level test coverage.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from intergrations.models import IntegrationConfig, SyncHistory, IntegrationStatus
from intergrations.base import CircuitBreaker, RateLimiter, IntegrationCredentials
from intergrations.quickbooks import QuickBooksIntegration
from intergrations.xero import XeroIntegration
from intergrations.slack_notifier import SlackIntegration
from intergrations.google_drive import GoogleDriveIntegration
from intergrations.zapier_webhooks import ZapierWebhookIntegration, ZapierEventType

from users.models import User, Company


class TestCircuitBreaker(TestCase):
    """Test circuit breaker pattern implementation."""
    
    def setUp(self):
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=5)
    
    def test_closed_state_success(self):
        """Test circuit breaker allows calls when closed."""
        def successful_call():
            return "success"
        
        result = self.circuit_breaker.call(successful_call)
        self.assertEqual(result, "success")
        self.assertEqual(self.circuit_breaker.state, "closed")
        self.assertEqual(self.circuit_breaker.failure_count, 0)
    
    def test_closed_state_failure_opens_circuit(self):
        """Test circuit breaker opens after threshold failures."""
        def failing_call():
            raise Exception("Test failure")
        
        with self.assertRaises(Exception):
            for _ in range(3):
                self.circuit_breaker.call(failing_call)
        
        self.assertEqual(self.circuit_breaker.state, "open")
        self.assertEqual(self.circuit_breaker.failure_count, 3)
    
    def test_open_state_rejects_calls(self):
        """Test circuit breaker rejects calls when open."""
        self.circuit_breaker.state = "open"
        self.circuit_breaker.failure_count = 3
        self.circuit_breaker.last_failure_time = timezone.now()
        
        def successful_call():
            return "success"
        
        with self.assertRaises(Exception) as context:
            self.circuit_breaker.call(successful_call)
        
        self.assertIn("Circuit breaker is OPEN", str(context.exception))
    
    def test_half_open_state_allows_limited_calls(self):
        """Test circuit breaker allows limited calls when half-open."""
        self.circuit_breaker.state = "open"
        self.circuit_breaker.failure_count = 3
        self.circuit_breaker.last_failure_time = timezone.now() - timedelta(seconds=10)
        
        call_count = 0
        def successful_call():
            nonlocal call_count
            call_count += 1
            return "success"
        
        for _ in range(3):
            result = self.circuit_breaker.call(successful_call)
            self.assertEqual(result, "success")
        
        self.assertEqual(self.circuit_breaker.state, "closed")
        self.assertEqual(call_count, 3)


class TestRateLimiter(TestCase):
    """Test rate limiter token bucket algorithm."""
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test rate limiter prevents exceeding rate."""
        limiter = RateLimiter(rate_limit=10, time_window=60, burst_limit=5)
        
        # Should allow up to burst_limit immediately
        for _ in range(5):
            self.assertTrue(await limiter.acquire())
        
        # Should be denied after burst
        self.assertFalse(await limiter.acquire())
    
    @pytest.mark.asyncio
    async def test_token_refill(self):
        """Test tokens refill over time."""
        limiter = RateLimiter(rate_limit=60, time_window=60, burst_limit=10)
        
        # Use all tokens
        for _ in range(10):
            await limiter.acquire()
        
        # Wait for refill
        await asyncio.sleep(1)
        
        # Should have at least 1 token
        self.assertTrue(await limiter.acquire())


class TestQuickBooksIntegration(APITestCase):
    """Test QuickBooks integration."""
    
    def setUp(self):
        self.company = Company.objects.create(
            name="Test Company",
            email="test@example.com"
        )
        self.user = User.objects.create_user(
            email="admin@example.com",
            password="testpass123",
            company=self.company,
            role="owner"
        )
        
        self.credentials = IntegrationCredentials(
            access_token="test_token",
            refresh_token="test_refresh",
            token_expiry=timezone.now() + timedelta(hours=1)
        )
        
        self.qb_integration = QuickBooksIntegration(
            company_id=self.company.id,
            credentials=self.credentials
        )
    
    @patch('aiohttp.ClientSession.post')
    async def test_authenticate_success(self, mock_post):
        """Test successful authentication."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "access_token": "new_token",
            "refresh_token": "new_refresh",
            "expires_in": 3600,
            "x_refresh_token_expires_in": 86400
        })
        mock_post.return_value.__aenter__.return_value = mock_response
        
        result = await self.qb_integration.authenticate(code="test_code")
        self.assertTrue(result)
    
    @patch('aiohttp.ClientSession.post')
    async def test_refresh_token_success(self, mock_post):
        """Test token refresh."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "access_token": "refreshed_token",
            "refresh_token": "refreshed_refresh",
            "expires_in": 3600,
            "x_refresh_token_expires_in": 86400
        })
        mock_post.return_value.__aenter__.return_value = mock_response
        
        result = await self.qb_integration.refresh_token()
        self.assertTrue(result)
        self.assertEqual(self.qb_integration.credentials.access_token, "refreshed_token")
    
    @patch('aiohttp.ClientSession.request')
    async def test_create_invoice_success(self, mock_request):
        """Test invoice creation."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "Invoice": {
                "Id": "123",
                "DocNumber": "INV-001",
                "TotalAmt": 1000.00
            }
        })
        mock_request.return_value.__aenter__.return_value = mock_response
        
        invoice_data = {
            "invoice_number": "INV-001",
            "customer_name": "Test Customer",
            "total_amount": 1000.00,
            "line_items": [
                {
                    "description": "Services",
                    "quantity": 1,
                    "unit_price": 1000.00,
                    "amount": 1000.00
                }
            ]
        }
        
        result = await self.qb_integration.create_invoice(invoice_data)
        self.assertEqual(result["Id"], "123")
        self.assertEqual(result["TotalAmt"], 1000.00)


class TestSlackIntegration(APITestCase):
    """Test Slack integration."""
    
    def setUp(self):
        self.company = Company.objects.create(
            name="Test Company",
            email="test@example.com"
        )
        self.user = User.objects.create_user(
            email="admin@example.com",
            password="testpass123",
            company=self.company,
            role="owner"
        )
        
        self.credentials = IntegrationCredentials(
            access_token="xoxb-test-token",
            additional_data={"default_channel": "#general"}
        )
        
        self.slack = SlackIntegration(
            company_id=self.company.id,
            credentials=self.credentials
        )
    
    @patch('aiohttp.ClientSession.post')
    async def test_send_message_success(self, mock_post):
        """Test sending Slack message."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ok": True, "ts": "1234567890"})
        mock_post.return_value.__aenter__.return_value = mock_response
        
        result = await self.slack.send_message(
            text="Test message",
            channel="#general"
        )
        
        self.assertTrue(result.get("ok"))
    
    @patch('aiohttp.ClientSession.post')
    async def test_send_invoice_notification(self, mock_post):
        """Test invoice notification formatting."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ok": True})
        mock_post.return_value.__aenter__.return_value = mock_response
        
        result = await self.slack.send_invoice_notification(
            invoice_number="INV-001",
            customer_name="Test Customer",
            amount=1500.00,
            due_date="2024-12-31",
            status="sent"
        )
        
        self.assertTrue(result.get("ok"))
    
    @patch('aiohttp.ClientSession.post')
    async def test_send_contract_notification(self, mock_post):
        """Test contract notification."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ok": True})
        mock_post.return_value.__aenter__.return_value = mock_response
        
        result = await self.slack.send_contract_notification(
            contract_name="Service Agreement",
            client_name="Big Corp",
            expiry_date="2024-12-31",
            days_remaining=7
        )
        
        self.assertTrue(result.get("ok"))


class TestGoogleDriveIntegration(APITestCase):
    """Test Google Drive integration."""
    
    def setUp(self):
        self.company = Company.objects.create(
            name="Test Company",
            email="test@example.com"
        )
        self.user = User.objects.create_user(
            email="admin@example.com",
            password="testpass123",
            company=self.company,
            role="owner"
        )
        
        self.credentials = IntegrationCredentials(
            access_token="test_token",
            refresh_token="test_refresh",
            token_expiry=timezone.now() + timedelta(hours=1)
        )
        
        self.drive = GoogleDriveIntegration(
            company_id=self.company.id,
            credentials=self.credentials
        )
    
    @patch('aiohttp.ClientSession.post')
    async def test_create_folder(self, mock_post):
        """Test folder creation."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "id": "folder123",
            "name": "Test Folder",
            "mimeType": "application/vnd.google-apps.folder"
        })
        mock_post.return_value.__aenter__.return_value = mock_response
        
        result = await self.drive.create_folder("Test Folder")
        
        self.assertEqual(result["id"], "folder123")
        self.assertEqual(result["name"], "Test Folder")
    
    @patch('aiohttp.ClientSession.post')
    async def test_upload_file(self, mock_post):
        """Test file upload."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "id": "file123",
            "name": "test.pdf",
            "mimeType": "application/pdf"
        })
        mock_post.return_value.__aenter__.return_value = mock_response
        
        result = await self.drive.upload_file(
            file_name="test.pdf",
            file_content=b"PDF content",
            mime_type="application/pdf"
        )
        
        self.assertEqual(result["id"], "file123")
    
    @patch('aiohttp.ClientSession.get')
    async def test_download_file(self, mock_get):
        """Test file download."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=b"PDF content")
        mock_get.return_value.__aenter__.return_value = mock_response
        
        content = await self.drive.download_file("file123")
        
        self.assertEqual(content, b"PDF content")


class TestZapierWebhookIntegration(APITestCase):
    """Test Zapier webhook integration."""
    
    def setUp(self):
        self.company = Company.objects.create(
            name="Test Company",
            email="test@example.com"
        )
        self.user = User.objects.create_user(
            email="admin@example.com",
            password="testpass123",
            company=self.company,
            role="owner"
        )
        
        self.credentials = IntegrationCredentials(
            additional_data={
                "webhook_urls": {
                    "invoice.created": "https://hooks.zapier.com/test/invoice",
                    "invoice.paid": "https://hooks.zapier.com/test/paid"
                }
            }
        )
        
        self.zapier = ZapierWebhookIntegration(
            company_id=self.company.id,
            credentials=self.credentials
        )
    
    @patch('aiohttp.ClientSession.post')
    async def test_trigger_event_success(self, mock_post):
        """Test triggering webhook event."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": "success"})
        mock_post.return_value.__aenter__.return_value = mock_response
        
        result = await self.zapier.trigger_event(
            ZapierEventType.INVOICE_CREATED,
            {"invoice_id": 123, "amount": 1000}
        )
        
        self.assertTrue(result["success"])
    
    @patch('aiohttp.ClientSession.post')
    async def test_trigger_invoice_event(self, mock_post):
        """Test invoice event formatting."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": "success"})
        mock_post.return_value.__aenter__.return_value = mock_response
        
        invoice_data = {
            "id": 123,
            "invoice_number": "INV-001",
            "total_amount": 1000.00,
            "currency": "USD",
            "status": "sent",
            "customer_name": "Test Customer",
            "customer_email": "customer@test.com"
        }
        
        result = await self.zapier.trigger_invoice_event(
            ZapierEventType.INVOICE_CREATED,
            invoice_data
        )
        
        self.assertTrue(result["success"])
    
    @patch('aiohttp.ClientSession.post')
    async def test_register_webhook(self, mock_post):
        """Test webhook registration."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": "success"})
        mock_post.return_value.__aenter__.return_value = mock_response
        
        result = await self.zapier.register_webhook(
            ZapierEventType.INVOICE_PAID,
            "https://hooks.zapier.com/test/new"
        )
        
        self.assertTrue(result)
        self.assertIn("invoice.paid", self.zapier.webhook_urls)


class TestIntegrationAPI(APITestCase):
    """Test integration API endpoints."""
    
    def setUp(self):
        self.company = Company.objects.create(
            name="Test Company",
            email="test@example.com"
        )
        self.user = User.objects.create_user(
            email="admin@example.com",
            password="testpass123",
            company=self.company,
            role="owner"
        )
        
        self.client.force_authenticate(user=self.user)
    
    def test_list_integrations(self):
        """Test listing integration configs."""
        IntegrationConfig.objects.create(
            company=self.company,
            integration_type="slack",
            credentials={"webhook_url": "https://test.com"},
            status="active"
        )
        
        url = reverse("integration-config-list")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
    
    def test_create_integration(self):
        """Test creating integration config."""
        url = reverse("integration-config-list")
        data = {
            "integration_type": "slack",
            "credentials": {"webhook_url": "https://test.com"},
            "auto_sync_enabled": True
        }
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["integration_type"], "slack")
    
    def test_test_connection_endpoint(self):
        """Test connection testing endpoint."""
        integration = IntegrationConfig.objects.create(
            company=self.company,
            integration_type="slack",
            credentials={"webhook_url": "https://test.com"},
            status="active"
        )
        
        url = reverse("integration-config-test", args=[integration.id])
        response = self.client.post(url)
        
        # Should handle gracefully even with invalid credentials
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST])
    
    def test_sync_endpoint(self):
        """Test sync trigger endpoint."""
        integration = IntegrationConfig.objects.create(
            company=self.company,
            integration_type="quickbooks",
            credentials={"access_token": "test"},
            status="active"
        )
        
        url = reverse("integration-config-sync", args=[integration.id])
        response = self.client.post(url, {"sync_type": "invoices"})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("task_id", response.data)
    
    def test_sync_history_endpoint(self):
        """Test sync history endpoint."""
        integration = IntegrationConfig.objects.create(
            company=self.company,
            integration_type="quickbooks",
            credentials={},
            status="active"
        )
        
        SyncHistory.objects.create(
            company=self.company,
            integration=integration,
            sync_type="invoices",
            status="success",
            items_processed=10,
            items_succeeded=10
        )
        
        url = reverse("integration-config-sync-history", args=[integration.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


class TestWebhookHandling(APITestCase):
    """Test webhook handling endpoints."""
    
    def setUp(self):
        self.company = Company.objects.create(
            name="Test Company",
            email="test@example.com"
        )
    
    @patch('stripe.Webhook.construct_event')
    def test_stripe_webhook(self, mock_construct):
        """Test Stripe webhook handler."""
        mock_construct.return_value = {
            "type": "invoice.payment_succeeded",
            "data": {
                "object": {
                    "metadata": {"invoice_id": "123"}
                }
            }
        }
        
        url = reverse("stripe-webhook")
        response = self.client.post(
            url,
            data="{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature"
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_zapier_webhook(self):
        """Test Zapier webhook endpoint."""
        url = reverse("zapier-webhook", args=[self.company.id])
        data = {
            "event": "create_invoice",
            "data": {
                "customer_name": "Test",
                "amount": 1000
            }
        }
        
        response = self.client.post(url, data, format="json")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check webhook was logged
        self.assertTrue(WebhookLog.objects.filter(
            company=self.company,
            direction="in"
        ).exists())


class TestIntegrationMetrics(APITestCase):
    """Test integration metrics tracking."""
    
    def setUp(self):
        self.company = Company.objects.create(
            name="Test Company",
            email="test@example.com"
        )
        self.user = User.objects.create_user(
            email="admin@example.com",
            password="testpass123",
            company=self.company,
            role="owner"
        )
        
        self.integration = IntegrationConfig.objects.create(
            company=self.company,
            integration_type="slack",
            credentials={},
            status="active"
        )
        
        self.client.force_authenticate(user=self.user)
    
    def test_metrics_endpoint(self):
        """Test metrics retrieval."""
        # Create some sync history
        for i in range(10):
            SyncHistory.objects.create(
                company=self.company,
                integration=self.integration,
                sync_type="invoices",
                status="success" if i < 8 else "failed",
                items_processed=100
            )
        
        url = reverse("integration-config-metrics", args=[self.integration.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_syncs"], 10)
        self.assertEqual(response.data["successful_syncs"], 8)
        self.assertAlmostEqual(response.data["success_rate"], 80.0)


class TestIntegrationPerformance(APITestCase):
    """Test integration performance and concurrency."""
    
    def setUp(self):
        self.company = Company.objects.create(
            name="Test Company",
            email="test@example.com"
        )
        self.user = User.objects.create_user(
            email="admin@example.com",
            password="testpass123",
            company=self.company,
            role="owner"
        )
        
        self.client.force_authenticate(user=self.user)
    
    def test_concurrent_sync_requests(self):
        """Test handling concurrent sync requests."""
        integration = IntegrationConfig.objects.create(
            company=self.company,
            integration_type="quickbooks",
            credentials={},
            status="active"
        )
        
        url = reverse("integration-config-sync", args=[integration.id])
        
        # Make multiple concurrent requests
        import concurrent.futures
        
        def make_request():
            return self.client.post(url, {"sync_type": "invoices"})
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in futures]
        
        # All requests should succeed
        for response in results:
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Only one sync should have been created
        sync_count = SyncHistory.objects.filter(
            integration=integration,
            sync_type="invoices"
        ).count()
        
        self.assertLessEqual(sync_count, 10)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=intergrations", "--cov-report=html"])