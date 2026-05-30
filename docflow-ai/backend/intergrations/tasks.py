"""
Celery tasks for integration operations.
Location: integrations/tasks.py
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from celery import shared_task
from celery.exceptions import Retry
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import IntegrationConfig, SyncHistory
from .base import IntegrationAPIError

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    queue="high"
)
def sync_integration_data(self, integration_id: int, sync_type: str, user_id: int = None):
    """
    Sync data with external integration.
    
    Args:
        integration_id: Integration configuration ID
        sync_type: 'invoices', 'contacts', 'all'
        user_id: Optional user ID who triggered the sync
    """
    from .views import get_integration_instance
    
    try:
        integration = IntegrationConfig.objects.select_related("company").get(id=integration_id)
    except IntegrationConfig.DoesNotExist as e:
        logger.error(f"Integration {integration_id} not found")
        return {"error": f"Integration not found: {e}"}
    
    # Check if sync is already running
    lock_key = f"sync_lock:{integration_id}:{sync_type}"
    if not cache.add(lock_key, "locked", timeout=3600):
        logger.warning(f"Sync already running for integration {integration_id}, type {sync_type}")
        return {"status": "skipped", "reason": "Sync already in progress"}
    
    # Create sync history record
    sync_history = SyncHistory.objects.create(
        company=integration.company,
        integration=integration,
        sync_type=sync_type,
        status="running",
        started_at=timezone.now()
    )
    
    try:
        # Get integration instance
        integration_instance = get_integration_instance(integration)
        
        if not integration_instance:
            raise ValueError(f"Unsupported integration type: {integration.integration_type}")
        
        # Test connection before syncing
        integration_instance.authenticate()
        
        items_processed = 0
        items_succeeded = 0
        
        # Perform sync based on type
        if sync_type in ["invoices", "all"]:
            invoices = sync_invoices_task(integration_instance, integration.company)
            items_processed += len(invoices)
            items_succeeded += len(invoices)
            logger.info(f"Synced {len(invoices)} invoices for integration {integration_id}")
        
        if sync_type in ["contacts", "all"]:
            contacts = sync_contacts_task(integration_instance, integration.company)
            items_processed += len(contacts)
            items_succeeded += len(contacts)
            logger.info(f"Synced {len(contacts)} contacts for integration {integration_id}")
        
        # Update sync history
        sync_history.status = "success"
        sync_history.items_processed = items_processed
        sync_history.items_succeeded = items_succeeded
        sync_history.completed_at = timezone.now()
        sync_history.save()
        
        # Update integration config
        integration.last_sync_at = timezone.now()
        integration.last_sync_status = "success"
        integration.save(update_fields=["last_sync_at", "last_sync_status"])
        
        result = {
            "status": "success",
            "sync_id": sync_history.id,
            "items_processed": items_processed,
            "items_succeeded": items_succeeded
        }
        
        logger.info(f"Sync completed for integration {integration_id}: {result}")
        return result
        
    except IntegrationAPIError as e:
        # API error - retry with backoff
        sync_history.status = "failed"
        sync_history.error_log = str(e)
        sync_history.completed_at = timezone.now()
        sync_history.save()
        
        integration.last_sync_status = "failed"
        integration.last_error = str(e)
        integration.save(update_fields=["last_sync_status", "last_error"])
        
        logger.error(f"API error syncing integration {integration_id}: {e}")
        
        # Retry with exponential backoff
        try:
            raise self.retry(
                exc=e,
                countdown=60 * (2 ** self.request.retries),
                max_retries=5
            )
        except Retry:
            return {"status": "retrying", "retry_count": self.request.retries}
        
    except Exception as e:
        # Other error - don't retry
        sync_history.status = "failed"
        sync_history.error_log = str(e)
        sync_history.completed_at = timezone.now()
        sync_history.save()
        
        integration.last_sync_status = "failed"
        integration.last_error = str(e)
        integration.save(update_fields=["last_sync_status", "last_error"])
        
        logger.exception(f"Unexpected error syncing integration {integration_id}: {e}")
        return {"status": "failed", "error": str(e)}
        
    finally:
        # Release lock
        cache.delete(lock_key)


@shared_task(queue="high")
def sync_quickbooks_invoice(quickbooks_invoice_id: str, operation: str):
    """
    Sync QuickBooks invoice changes to DocFlow.
    """
    from billing.services import sync_quickbooks_invoice as sync_service
    
    try:
        result = sync_service(quickbooks_invoice_id, operation)
        logger.info(f"Synced QuickBooks invoice {quickbooks_invoice_id}: {operation}")
        return result
    except Exception as e:
        logger.error(f"Failed to sync QuickBooks invoice {quickbooks_invoice_id}: {e}")
        raise


@shared_task(queue="high")
def sync_xero_invoice(xero_invoice_id: str, tenant_id: str):
    """
    Sync Xero invoice changes to DocFlow.
    """
    from billing.services import sync_xero_invoice as sync_service
    
    try:
        result = sync_service(xero_invoice_id, tenant_id)
        logger.info(f"Synced Xero invoice {xero_invoice_id}")
        return result
    except Exception as e:
        logger.error(f"Failed to sync Xero invoice {xero_invoice_id}: {e}")
        raise


@shared_task(queue="high")
def process_webhook_event(integration_id: int, event_data: Dict[str, Any]):
    """
    Process incoming webhook event.
    """
    try:
        integration = IntegrationConfig.objects.get(id=integration_id)
        
        # Process based on integration type
        if integration.integration_type == "quickbooks":
            from .quickbooks import process_quickbooks_webhook
            result = process_quickbooks_webhook(integration, event_data)
        elif integration.integration_type == "xero":
            from .xero import process_xero_webhook
            result = process_xero_webhook(integration, event_data)
        else:
            logger.warning(f"Unsupported webhook type: {integration.integration_type}")
            return {"status": "ignored", "reason": "Unsupported integration type"}
        
        logger.info(f"Processed webhook for integration {integration_id}")
        return result
        
    except IntegrationConfig.DoesNotExist:
        logger.error(f"Integration {integration_id} not found for webhook")
        return {"status": "error", "reason": "Integration not found"}
    except Exception as e:
        logger.exception(f"Error processing webhook: {e}")
        raise


@shared_task(queue="default")
def send_slack_notification_task(
    company_id: int,
    channel: str,
    text: str,
    blocks: list = None,
    message_type: str = "info"
):
    """
    Send Slack notification asynchronously.
    """
    try:
        integration = IntegrationConfig.objects.get(
            company_id=company_id,
            integration_type="slack",
            is_active=True
        )
        
        from .slack_notifier import SlackIntegration
        slack = SlackIntegration(company_id, integration.credentials)
        
        # Run async in sync context
        import asyncio
        result = asyncio.run(
            slack.send_message(
                text=text,
                channel=channel,
                blocks=blocks,
                message_type=message_type
            )
        )
        
        logger.info(f"Slack notification sent to company {company_id}")
        return result
        
    except IntegrationConfig.DoesNotExist:
        logger.warning(f"No Slack integration found for company {company_id}")
        return {"status": "skipped", "reason": "No Slack integration"}
    except Exception as e:
        logger.error(f"Failed to send Slack notification: {e}")
        raise


@shared_task(queue="default")
def upload_to_google_drive_task(
    company_id: int,
    file_name: str,
    file_content_b64: str,
    mime_type: str,
    folder_name: str = None
):
    """
    Upload file to Google Drive asynchronously.
    """
    import base64
    
    try:
        integration = IntegrationConfig.objects.get(
            company_id=company_id,
            integration_type="google_drive",
            is_active=True
        )
        
        from .google_drive import GoogleDriveIntegration
        drive = GoogleDriveIntegration(company_id, integration.credentials)
        
        file_content = base64.b64decode(file_content_b64)
        
        # Run async in sync context
        import asyncio
        result = asyncio.run(
            drive.upload_file(
                file_name=file_name,
                file_content=file_content,
                mime_type=mime_type,
                folder_id=folder_name
            )
        )
        
        logger.info(f"Uploaded {file_name} to Google Drive for company {company_id}")
        return result
        
    except IntegrationConfig.DoesNotExist:
        logger.warning(f"No Google Drive integration found for company {company_id}")
        return {"status": "skipped", "reason": "No Google Drive integration"}
    except Exception as e:
        logger.error(f"Failed to upload to Google Drive: {e}")
        raise


@shared_task(queue="high")
def trigger_zapier_webhook_task(
    company_id: int,
    event_type: str,
    payload: dict
):
    """
    Trigger Zapier webhook asynchronously.
    """
    try:
        integration = IntegrationConfig.objects.get(
            company_id=company_id,
            integration_type="zapier",
            is_active=True
        )
        
        from .zapier_webhooks import ZapierWebhookIntegration, ZapierEventType
        zapier = ZapierWebhookIntegration(company_id, integration.credentials)
        
        # Convert string to enum
        event_enum = ZapierEventType(event_type)
        
        # Run async in sync context
        import asyncio
        result = asyncio.run(
            zapier.trigger_event(event_enum, payload)
        )
        
        logger.info(f"Triggered Zapier webhook {event_type} for company {company_id}")
        return result
        
    except IntegrationConfig.DoesNotExist:
        logger.warning(f"No Zapier integration found for company {company_id}")
        return {"status": "skipped", "reason": "No Zapier integration"}
    except Exception as e:
        logger.error(f"Failed to trigger Zapier webhook: {e}")
        raise


@shared_task(queue="low")
def schedule_integration_syncs():
    """
    Schedule automatic syncs for all integrations with auto_sync_enabled.
    """
    integrations = IntegrationConfig.objects.filter(
        is_active=True,
        auto_sync_enabled=True,
        sync_frequency__in=["hourly", "daily"]
    )
    
    triggered = 0
    for integration in integrations:
        should_sync = False
        
        if integration.sync_frequency == "hourly":
            if not integration.last_sync_at or \
               integration.last_sync_at < timezone.now() - timedelta(hours=1):
                should_sync = True
        elif integration.sync_frequency == "daily":
            if not integration.last_sync_at or \
               integration.last_sync_at < timezone.now() - timedelta(days=1):
                should_sync = True
        
        if should_sync:
            sync_integration_data.delay(
                integration.id,
                "all",
                None
            )
            triggered += 1
    
    logger.info(f"Scheduled {triggered} integration syncs")
    return {"triggered": triggered}


# Helper functions
async def sync_invoices_task(integration_instance, company):
    """Sync invoices with integration."""
    # Implementation depends on integration type
    # This is a placeholder - implement based on your needs
    return []


async def sync_contacts_task(integration_instance, company):
    """Sync contacts with integration."""
    # Implementation depends on integration type
    # This is a placeholder - implement based on your needs
    return []