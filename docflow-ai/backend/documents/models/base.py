import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings


class BaseDocument(models.Model):
    """Shared fields for all document types (Invoices, Quotations, etc.)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        VIEWED = "viewed", "Viewed"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="%(class)s_set",
    )
    client = models.ForeignKey(
        "companies.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_set",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    currency = models.CharField(max_length=3, default="KES")
    issue_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True)

    # Financials
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=16.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Files
    pdf_file = models.FileField(upload_to="documents/pdf/", null=True, blank=True)
    docx_file = models.FileField(upload_to="documents/docx/", null=True, blank=True)

    # Portal tracking
    portal_token = models.UUIDField(default=uuid.uuid4, unique=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    portal_used = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)  # Soft delete

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def calculate_totals(self):
        """
        Recalculate subtotal, tax, and total from current line items.

        FIX: Use Decimal arithmetic throughout to avoid float precision issues.
        FIX: total_amount is clamped to zero — it can never go negative even if
             discount_amount exceeds subtotal + tax_amount.
        """
        items = self.line_items.all()

        self.subtotal = sum(
            (item.amount for item in items),
            Decimal("0.00"),
        )

        # tax_rate is already a Decimal field — divide by 100 with Decimal
        self.tax_amount = (self.subtotal * self.tax_rate / Decimal("100")).quantize(
            Decimal("0.01")
        )

        raw_total = self.subtotal + self.tax_amount - self.discount_amount

        # Never let the total go negative
        self.total_amount = max(raw_total, Decimal("0.00"))

        self.save(update_fields=["subtotal", "tax_amount", "total_amount"])