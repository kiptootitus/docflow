"""
URL configuration for integrations module.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.views.decorators.csrf import csrf_exempt

from .views import (
    IntegrationConfigViewSet,
    SyncHistoryViewSet,
    WebhookLogViewSet,
    IntegrationWebhookView
)

router = DefaultRouter()
router.register("configs", IntegrationConfigViewSet, basename="integration-config")
router.register("sync-history", SyncHistoryViewSet, basename="sync-history")
router.register("webhook-logs", WebhookLogViewSet, basename="webhook-logs")

urlpatterns = [
    path("", include(router.urls)),
    
    # Webhook endpoints for third-party services
    path("webhooks/stripe/", 
         csrf_exempt(IntegrationWebhookView.handle_stripe_webhook),
         name="stripe-webhook"),
    
    path("webhooks/quickbooks/",
         csrf_exempt(IntegrationWebhookView.handle_quickbooks_webhook),
         name="quickbooks-webhook"),
    
    path("webhooks/zapier/<int:company_id>/",
         csrf_exempt(IntegrationWebhookView.handle_zapier_webhook),
         name="zapier-webhook"),
    
    # OAuth callback endpoints
    path("oauth/quickbooks/callback/",
         IntegrationOAuthView.quickbooks_callback,
         name="quickbooks-oauth-callback"),
    
    path("oauth/xero/callback/",
         IntegrationOAuthView.xero_callback,
         name="xero-oauth-callback"),
    
    path("oauth/google-drive/callback/",
         IntegrationOAuthView.google_drive_callback,
         name="google-drive-oauth-callback"),
]