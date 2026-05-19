import uuid
from datetime import timedelta
from django.db import models
from django.utils import timezone
from .base import BaseDocument
from .invoices import Invoice

class Quotation(BaseDocument):
    """Quotation model - inherits structural elements directly from BaseDocument"""
    valid_until = models.DateField(null=True, blank=True)
    converted_to_invoice = models.ForeignKey(
        Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name="source_quotation"
    )

    class Meta:
        db_table = "quotations"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Quotation {self.number}"

    def save(self, *args, **kwargs):
        if not self.valid_until and self.due_date:
            self.valid_until = self.due_date
        elif not self.valid_until:
            self.valid_until = timezone.now().date() + timedelta(days=30)
        super().save(*args, **kwargs)


class QuotationLineItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="line_items")
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "quotation_line_items"
        ordering = ["order"]

    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)