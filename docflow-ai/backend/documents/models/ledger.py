from django.db import models
from django.conf import settings
import json


class LedgerEvent(models.Model):
    EVENT_TYPES = (
        ("INVOICE_CREATED", "INVOICE_CREATED"),
        ("INVOICE_VIEWED", "INVOICE_VIEWED"),
        ("INVOICE_PAID", "INVOICE_PAID"),
        ("INVOICE_DELETED_BLOCKED", "INVOICE_DELETED_BLOCKED"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )

    invoice_id = models.UUIDField(null=True, blank=True)
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)

    snapshot = models.JSONField()

    created_at = models.DateTimeField(auto_now_add=True)

    hash = models.CharField(max_length=256, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["invoice_id"]),
            models.Index(fields=["event_type"]),
        ]