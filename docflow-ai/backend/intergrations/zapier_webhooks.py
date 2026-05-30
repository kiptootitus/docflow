"""
Zapier webhook integration for custom automation workflows.
Send events to Zapier webhooks for integration with 5000+ apps.
"""

import logging
import hashlib
import hmac
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum

from django.conf import settings
from django.core.cache import cache

from .base import IntegrationBase, IntegrationType, IntegrationCredentials

logger = logging.getLogger(__name__)


class ZapierEventType(Enum):
    """Events that can be sent to Zapier."""
    INVOICE_CREATED = "invoice.created"
    INVOICE_UPDATED = "invoice.updated"
    INVOICE_PAID = "invoice.paid"
    INVOICE_OVERDUE = "invoice.overdue"
    CONTRACT_CREATED = "contract.created"
    CONTRACT_SIGNED = "contract.signed"
    CONTRACT_EXPIRING = "contract.expiring"
    PAYMENT_RECEIVED = "payment.received"
    USER_SIGNED_UP = "user.signed_up"
    USER_SUBSCRIBED = "user.subscribed"
    AI_REVIEW_COMPLETE = "ai.review.complete"
    DOCUMENT_GENERATED = "document.generated"


class ZapierWebhookIntegration(IntegrationBase):
    """
    Zapier webhook integration for sending events to external workflows.
    """
    
    def __init__(self, company_id: int, credentials: Optional[IntegrationCredentials] = None):
        super().__init__(company_id, credentials)
        self.webhook_urls = {}
        
        if credentials:
            self.webhook_urls = credentials.additional_data.get("webhook_urls", {})
    
    def get_integration_type(self) -> IntegrationType:
        return IntegrationType.ZAPIER
    
    def get_rate_limit(self) -> int:
        return 100  # Reasonable limit per minute
    
    def get_rate_limit_window(self) -> int:
        return 60
    
    async def authenticate(self) -> bool:
        """Validate webhook URLs by sending test payload."""
        if not self.webhook_urls:
            return False
        
        # Test each webhook URL
        for event_type, url in self.webhook_urls.items():
            try:
                test_payload = {
                    "test": True,
                    "event": event_type,
                    "timestamp": datetime.now().isoformat()
                }
                
                await self._send_webhook(url, test_payload)
            except Exception as e:
                logger.warning(f"Failed to test webhook for {event_type}: {e}")
        
        return True
    
    async def refresh_token(self) -> bool:
        """Zapier doesn't use tokens, but implement for interface."""
        return await self.authenticate()
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test connection by sending a test webhook."""
        results = {}
        
        for event_type, url in self.webhook_urls.items():
            try:
                await self._send_webhook(url, {"test": True, "event": event_type})
                results[event_type] = {"status": "ok", "message": "Webhook responded"}
            except Exception as e:
                results[event_type] = {"status": "error", "message": str(e)}
        
        return {"webhooks_tested": len(self.webhook_urls), "results": results}
    
    async def trigger_event(
        self,
        event_type: ZapierEventType,
        payload: Dict[str, Any],
        retry: bool = True
    ) -> Dict[str, Any]:
        """
        Trigger a Zapier webhook event.
        
        Args:
            event_type: Type of event
            payload: Event payload data
            retry: Whether to retry on failure
        
        Returns:
            Webhook response
        """
        event_key = event_type.value
        
        if event_key not in self.webhook_urls:
            logger.debug(f"No webhook configured for event: {event_key}")
            return {"skipped": True, "reason": "No webhook configured"}
        
        webhook_url = self.webhook_urls[event_key]
        
        # Format payload
        formatted_payload = self._format_payload(event_type, payload)
        
        # Send with retry logic
        max_retries = 3 if retry else 1
        last_error = None
        
        for attempt in range(max_retries):
            try:
                response = await self._send_webhook(webhook_url, formatted_payload)
                logger.info(f"Webhook triggered: {event_key} - Success")
                return {"success": True, "response": response}
            except Exception as e:
                last_error = e
                logger.warning(f"Webhook attempt {attempt + 1} failed for {event_key}: {e}")
                
                if retry and attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        logger.error(f"Failed to trigger webhook {event_key}: {last_error}")
        return {"success": False, "error": str(last_error)}
    
    async def trigger_invoice_event(
        self,
        event: ZapierEventType,
        invoice: Dict[str, Any],
        company: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Trigger invoice-related event."""
        
        payload = {
            "invoice": {
                "id": invoice.get("id"),
                "number": invoice.get("invoice_number"),
                "amount": float(invoice.get("total_amount", 0)),
                "currency": invoice.get("currency", "USD"),
                "status": invoice.get("status"),
                "due_date": invoice.get("due_date"),
                "created_at": invoice.get("created_at"),
                "customer": {
                    "name": invoice.get("customer_name"),
                    "email": invoice.get("customer_email"),
                    "id": invoice.get("customer_id")
                },
                "url": invoice.get("invoice_url")
            }
        }
        
        if company:
            payload["company"] = {
                "id": company.get("id"),
                "name": company.get("name"),
                "email": company.get("email")
            }
        
        return await self.trigger_event(event, payload)
    
    async def trigger_contract_event(
        self,
        event: ZapierEventType,
        contract: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Trigger contract-related event."""
        
        payload = {
            "contract": {
                "id": contract.get("id"),
                "name": contract.get("name"),
                "type": contract.get("contract_type"),
                "status": contract.get("status"),
                "value": float(contract.get("value", 0)),
                "currency": contract.get("currency", "USD"),
                "start_date": contract.get("start_date"),
                "end_date": contract.get("end_date"),
                "signing_status": contract.get("signing_status"),
                "client": {
                    "name": contract.get("client_name"),
                    "email": contract.get("client_email"),
                    "id": contract.get("client_id")
                },
                "url": contract.get("contract_url")
            }
        }
        
        return await self.trigger_event(event, payload)
    
    async def trigger_payment_event(
        self,
        event: ZapierEventType,
        payment: Dict[str, Any],
        invoice: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Trigger payment-related event."""
        
        payload = {
            "payment": {
                "id": payment.get("id"),
                "amount": float(payment.get("amount", 0)),
                "currency": payment.get("currency", "USD"),
                "status": payment.get("status"),
                "method": payment.get("payment_method"),
                "transaction_id": payment.get("transaction_id"),
                "paid_at": payment.get("paid_at"),
                "customer": {
                    "name": payment.get("customer_name"),
                    "email": payment.get("customer_email")
                }
            }
        }
        
        if invoice:
            payload["invoice"] = {
                "id": invoice.get("id"),
                "number": invoice.get("invoice_number"),
                "amount": float(invoice.get("total_amount", 0))
            }
        
        return await self.trigger_event(event, payload)
    
    async def trigger_user_event(
        self,
        event: ZapierEventType,
        user: Dict[str, Any],
        subscription: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Trigger user-related event."""
        
        payload = {
            "user": {
                "id": user.get("id"),
                "email": user.get("email"),
                "name": user.get("full_name"),
                "company": user.get("company_name"),
                "role": user.get("role"),
                "created_at": user.get("date_joined")
            }
        }
        
        if subscription:
            payload["subscription"] = {
                "plan": subscription.get("plan_name"),
                "status": subscription.get("status"),
                "price": float(subscription.get("price", 0)),
                "currency": subscription.get("currency", "USD"),
                "start_date": subscription.get("start_date"),
                "end_date": subscription.get("end_date")
            }
        
        return await self.trigger_event(event, payload)
    
    async def register_webhook(
        self,
        event_type: ZapierEventType,
        webhook_url: str
    ) -> bool:
        """Register a new webhook for an event type."""
        
        # Test the webhook
        test_payload = {
            "test": True,
            "event": event_type.value,
            "timestamp": datetime.now().isoformat(),
            "message": "Webhook registration test"
        }
        
        try:
            await self._send_webhook(webhook_url, test_payload)
            
            # Store webhook URL
            self.webhook_urls[event_type.value] = webhook_url
            
            # Update stored credentials
            await self._store_credentials()
            
            logger.info(f"Webhook registered for {event_type.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register webhook for {event_type.value}: {e}")
            return False
    
    async def unregister_webhook(self, event_type: ZapierEventType) -> bool:
        """Unregister a webhook for an event type."""
        
        event_key = event_type.value
        
        if event_key in self.webhook_urls:
            del self.webhook_urls[event_key]
            await self._store_credentials()
            logger.info(f"Webhook unregistered for {event_key}")
            return True
        
        return False
    
    def _format_payload(
        self,
        event_type: ZapierEventType,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Format payload for Zapier webhook."""
        
        return {
            "event": event_type.value,
            "timestamp": datetime.now().isoformat(),
            "data": payload,
            "source": "docflow_ai",
            "version": getattr(settings, "VERSION", "1.0.0")
        }
    
    async def _send_webhook(
        self,
        webhook_url: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send webhook request."""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "DocFlowAI-Webhook/1.0"
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status in (200, 201, 202):
                    try:
                        return await response.json()
                    except:
                        return {"status": "success", "status_code": response.status}
                else:
                    response_text = await response.text()
                    raise IntegrationAPIError(
                        f"Webhook responded with {response.status}: {response_text}"
                    )
    
    async def _store_credentials(self):
        """Store webhook configuration."""
        from .models import IntegrationConfig
        
        IntegrationConfig.objects.update_or_create(
            company_id=self.company_id,
            integration_type=self.get_integration_type().value,
            defaults={
                "credentials": {
                    "webhook_urls": self.webhook_urls
                },
                "is_active": True,
                "last_sync_at": datetime.now()
            }
        )