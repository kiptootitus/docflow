"""
API endpoints for integration management, OAuth flows, and webhook handling.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser
from django.shortcuts import redirect
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema, extend_schema_view

from .models import IntegrationConfig, SyncHistory, WebhookLog, IntegrationStatus
from .serializers import (
    IntegrationConfigSerializer,
    SyncHistorySerializer,
    WebhookLogSerializer,
    InvoiceSyncSerializer,
    ContactSyncSerializer
)
from .quickbooks import QuickBooksIntegration
from .xero import XeroIntegration
from .slack_notifier import SlackIntegration
from .google_drive import GoogleDriveIntegration
from .zapier_webhooks import ZapierWebhookIntegration, ZapierEventType

from users.permissions import IsCompanyOwner, IsCompanyStaff
from core.pagination import StandardPagination
from core.throttling import IntegrationRateThrottle


@extend_schema_view(
    list=extend_schema(summary="List integrations", tags=["Integrations"]),
    create=extend_schema(summary="Create integration", tags=["Integrations"]),
    retrieve=extend_schema(summary="Get integration details", tags=["Integrations"]),
    update=extend_schema(summary="Update integration", tags=["Integrations"]),
    destroy=extend_schema(summary="Delete integration", tags=["Integrations"]),
)
class IntegrationConfigViewSet(viewsets.ModelViewSet):
    """
    Manage integration configurations for a company.
    """
    serializer_class = IntegrationConfigSerializer
    permission_classes = [permissions.IsAuthenticated, IsCompanyStaff]
    pagination_class = StandardPagination
    throttle_classes = [IntegrationRateThrottle]
    
    def get_queryset(self):
        return IntegrationConfig.objects.filter(
            company=self.request.user.company
        ).select_related("company")
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)
    
    @extend_schema(summary="Test integration connection")
    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Test the integration connection."""
        integration = self.get_object()
        
        # Get integration instance
        integration_instance = self._get_integration_instance(integration)
        
        if not integration_instance:
            return Response(
                {"error": "Unsupported integration type"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            result = integration_instance.test_connection()
            return Response({
                "success": True,
                "result": result,
                "metrics": integration_instance.get_metrics()
            })
        except Exception as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(summary="Sync data with integration")
    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        """Trigger a sync with the integration."""
        integration = self.get_object()
        sync_type = request.data.get("sync_type", "all")
        
        # Trigger async sync task
        from .tasks import sync_integration_data
        task = sync_integration_data.delay(
            integration.id,
            sync_type,
            request.user.id
        )
        
        return Response({
            "success": True,
            "task_id": task.id,
            "message": f"Sync started for {sync_type}"
        })
    
    @extend_schema(summary="Get OAuth URL")
    @action(detail=True, methods=["get"])
    def oauth_url(self, request, pk=None):
        """Get OAuth authorization URL for integration."""
        integration = self.get_object()
        
        integration_instance = self._get_integration_instance(integration)
        
        if not integration_instance or not hasattr(integration_instance, "get_authorization_url"):
            return Response(
                {"error": "OAuth not supported for this integration"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        oauth_url = integration_instance.get_authorization_url(
            state=f"{integration.id}:{request.user.id}"
        )
        
        return Response({"oauth_url": oauth_url})
    
    @extend_schema(summary="Get sync history")
    @action(detail=True, methods=["get"])
    def sync_history(self, request, pk=None):
        """Get sync history for integration."""
        integration = self.get_object()
        
        history = SyncHistory.objects.filter(
            integration=integration
        ).order_by("-started_at")[:50]
        
        serializer = SyncHistorySerializer(history, many=True)
        return Response(serializer.data)
    
    def _get_integration_instance(self, integration):
        """Get integration instance from config."""
        from .base import IntegrationCredentials
        
        credentials = IntegrationCredentials(**integration.credentials)
        
        if integration.integration_type == "quickbooks":
            return QuickBooksIntegration(integration.company.id, credentials)
        elif integration.integration_type == "xero":
            return XeroIntegration(integration.company.id, credentials)
        elif integration.integration_type == "slack":
            return SlackIntegration(integration.company.id, credentials)
        elif integration.integration_type == "google_drive":
            return GoogleDriveIntegration(integration.company.id, credentials)
        elif integration.integration_type == "zapier":
            return ZapierWebhookIntegration(integration.company.id, credentials)
        
        return None


@extend_schema_view(
    list=extend_schema(summary="List sync history", tags=["Integrations"]),
)
class SyncHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View sync history for integrations.
    """
    serializer_class = SyncHistorySerializer
    permission_classes = [permissions.IsAuthenticated, IsCompanyStaff]
    pagination_class = StandardPagination
    
    def get_queryset(self):
        return SyncHistory.objects.filter(
            company=self.request.user.company
        ).select_related("integration").order_by("-started_at")


@extend_schema_view(
    list=extend_schema(summary="List webhook logs", tags=["Integrations"]),
)
class WebhookLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View webhook logs for integrations.
    """
    serializer_class = WebhookLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsCompanyStaff]
    pagination_class = StandardPagination
    
    def get_queryset(self):
        return WebhookLog.objects.filter(
            company=self.request.user.company
        ).order_by("-created_at")


class IntegrationWebhookView:
    """
    Handle incoming webhooks from third-party services.
    """
    
    @staticmethod
    @method_decorator(csrf_exempt)
    async def handle_stripe_webhook(request):
        """Handle Stripe webhook."""
        payload = request.body
        sig_header = request.headers.get("Stripe-Signature")
        
        # Verify webhook signature
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            return HttpResponse(status=400)
        except stripe.error.SignatureVerificationError:
            return HttpResponse(status=400)
        
        # Process event
        if event["type"] == "invoice.payment_succeeded":
            # Update invoice status
            invoice_id = event["data"]["object"]["metadata"].get("invoice_id")
            if invoice_id:
                from billing.models import Invoice
                invoice = await Invoice.objects.aget(id=invoice_id)
                invoice.status = "paid"
                await invoice.asave()
                
                # Trigger Zapier webhook
                await trigger_zapier_event(
                    invoice.company_id,
                    ZapierEventType.INVOICE_PAID,
                    {"invoice_id": invoice_id}
                )
        
        return HttpResponse(status=200)
    
    @staticmethod
    @method_decorator(csrf_exempt)
    async def handle_quickbooks_webhook(request):
        """Handle QuickBooks webhook notifications."""
        # Verify signature
        signature = request.headers.get("Intuit-Signature")
        
        if not verify_quickbooks_signature(request.body, signature):
            return HttpResponse(status=401)
        
        payload = await request.json()
        
        for notification in payload.get("eventNotifications", []):
            entity = notification.get("dataChangeEvent", {}).get("entities", [])[0]
            
            if entity.get("name") == "Invoice":
                # Queue sync for updated invoice
                from .tasks import sync_quickbooks_invoice
                await sync_quickbooks_invoice.delay(
                    entity["id"],
                    entity.get("operation", "update")
                )
        
        return HttpResponse(status=200)
    
    @staticmethod
    @method_decorator(csrf_exempt)
    async def handle_zapier_webhook(request, company_id):
        """Handle incoming webhook from Zapier."""
        payload = await request.json()
        
        # Log incoming webhook
        await WebhookLog.objects.acreate(
            company_id=company_id,
            direction="in",
            event_type=payload.get("event", "unknown"),
            request_payload=payload,
            success=True
        )
        
        # Process based on event type
        event = payload.get("event")
        
        if event == "create_invoice":
            # Create invoice from Zapier data
            from billing.services import create_invoice_from_data
            await create_invoice_from_data(company_id, payload.get("data", {}))
        
        return Response({"status": "received"})


async def trigger_zapier_event(company_id: int, event_type: ZapierEventType, data: dict):
    """Helper function to trigger Zapier webhook."""
    try:
        integration = await IntegrationConfig.objects.aget(
            company_id=company_id,
            integration_type="zapier",
            is_active=True
        )
        
        zapier = ZapierWebhookIntegration(company_id, integration.credentials)
        await zapier.trigger_event(event_type, data)
        
    except IntegrationConfig.DoesNotExist:
        pass