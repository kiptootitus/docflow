"""
Database models for integrations tracking, sync history,
and configuration management.
"""

from django.db import models
from django.db.models import JSONField
from django.utils import timezone
from django.core.validators import MinLengthValidator, MaxLengthValidator

from users.models import User
from companies.models import Company


class IntegrationType(models.TextChoices):
    """Integration types."""
    QUICKBOOKS = "quickbooks", "QuickBooks"
    XERO = "xero", "Xero"
    SLACK = "slack", "Slack"
    GOOGLE_DRIVE = "google_drive", "Google Drive"
    ZAPIER = "zapier", "Zapier"


class IntegrationStatus(models.TextChoices):
    """Integration connection status."""
    ACTIVE = "active", "Active"
    DEGRADED = "degraded", "Degraded"
    INACTIVE = "inactive", "Inactive"
    ERROR = "error", "Error"
    PENDING = "pending", "Pending Authentication"


class IntegrationConfig(models.Model):
    """
    Store integration configuration and credentials securely.
    """
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="integrations"
    )
    integration_type = models.CharField(
        max_length=50,
        choices=IntegrationType.choices
    )
    
    # Encrypted credentials storage
    credentials = JSONField(
        default=dict,
        help_text="Encrypted OAuth tokens and configuration"
    )
    
    status = models.CharField(
        max_length=20,
        choices=IntegrationStatus.choices,
        default=IntegrationStatus.PENDING
    )
    
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text="Set as default integration for this type"
    )
    
    # Sync settings
    auto_sync_enabled = models.BooleanField(default=False)
    sync_frequency = models.CharField(
        max_length=20,
        choices=[
            ("manual", "Manual"),
            ("hourly", "Hourly"),
            ("daily", "Daily"),
            ("realtime", "Real-time")
        ],
        default="manual"
    )
    
    # Last sync information
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=50, blank=True)
    last_error = models.TextField(blank=True)
    
    # Metrics
    total_syncs = models.IntegerField(default=0)
    successful_syncs = models.IntegerField(default=0)
    failed_syncs = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [["company", "integration_type"]]
        indexes = [
            models.Index(fields=["company", "integration_type", "status"]),
            models.Index(fields=["last_sync_at"]),
        ]
    
    def __str__(self):
        return f"{self.company.name} - {self.get_integration_type_display()}"
    
    def update_metrics(self, success: bool):
        """Update sync metrics."""
        self.total_syncs += 1
        if success:
            self.successful_syncs += 1
        else:
            self.failed_syncs += 1
        self.save(update_fields=["total_syncs", "successful_syncs", "failed_syncs"])
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_syncs == 0:
            return 0.0
        return (self.successful_syncs / self.total_syncs) * 100


class SyncHistory(models.Model):
    """
    Track sync operations between DocFlow and external integrations.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    integration = models.ForeignKey(
        IntegrationConfig,
        on_delete=models.CASCADE,
        related_name="sync_history"
    )
    
    sync_type = models.CharField(
        max_length=50,
        choices=[
            ("invoices", "Invoices"),
            ("contacts", "Contacts"),
            ("payments", "Payments"),
            ("all", "All Data")
        ]
    )
    
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("running", "Running"),
            ("success", "Success"),
            ("failed", "Failed"),
            ("partial", "Partial Success")
        ],
        default="pending"
    )
    
    items_processed = models.IntegerField(default=0)
    items_succeeded = models.IntegerField(default=0)
    items_failed = models.IntegerField(default=0)
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    error_log = models.TextField(blank=True)
    sync_metadata = JSONField(default=dict)
    
    class Meta:
        indexes = [
            models.Index(fields=["company", "integration", "-started_at"]),
            models.Index(fields=["status", "started_at"]),
        ]
        ordering = ["-started_at"]
    
    def __str__(self):
        return f"Sync {self.id} - {self.company.name} - {self.sync_type}"
    
    def complete(self, success: bool = True):
        """Mark sync as complete."""
        self.status = "success" if success else "failed"
        self.completed_at = timezone.now()
        self.save()
        
        # Update integration metrics
        self.integration.update_metrics(success)


class WebhookLog(models.Model):
    """
    Log incoming/outgoing webhook events.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True)
    integration = models.ForeignKey(
        IntegrationConfig,
        on_delete=models.CASCADE,
        null=True,
        related_name="webhook_logs"
    )
    
    direction = models.CharField(
        max_length=10,
        choices=[("in", "Incoming"), ("out", "Outgoing")]
    )
    
    event_type = models.CharField(max_length=100)
    url = models.URLField(max_length=500, blank=True)
    
    request_payload = JSONField(default=dict)
    response_status = models.IntegerField(null=True, blank=True)
    response_payload = JSONField(default=dict, null=True, blank=True)
    
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=["company", "direction", "-created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"Webhook {self.id} - {self.event_type} - {'Success' if self.success else 'Failed'}"