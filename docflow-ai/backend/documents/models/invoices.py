import uuid
from django.db import models
from .base import BaseDocument


class Invoice(BaseDocument):
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    stripe_payment_link = models.URLField(blank=True)

    class Meta:
        db_table = "invoices"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invoice {self.number}"

    def delete(self, *args, **kwargs):
        """Soft delete implementation that writes directly into our app's ledger architecture."""
        from ..services.ledger import create_ledger_event  # Safe relative reference import

        create_ledger_event(
            user=self.created_by,
            event_type="INVOICE_DELETED_BLOCKED",
            snapshot={
                "id": str(self.id),
                "number": self.number,
                "total": str(self.total_amount),
            },
            invoice_id=self.id,
        )
        self.is_deleted = True
        self.save(update_fields=["is_deleted"])


class InvoiceLineItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="line_items")
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "invoice_line_items"
        ordering = ["order"]

    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)