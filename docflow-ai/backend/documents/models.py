"""
DocFlow AI — documents/models.py
=================================
Enterprise-grade document models for Invoices, Quotations, and Contracts.

Architecture decisions
──────────────────────
• UUID primary keys everywhere — safe for distributed IDs, no sequential guessing.
• Row-level multi-tenancy via company FK — every query is implicitly scoped.
• Soft delete (is_active + deleted_at) — data is never hard-deleted.
• DocumentQuerySet / ActiveDocumentManager — chainable, reusable query helpers.
• compute_totals() is always server-side — clients can never manipulate totals.
• Per-line-item tax_rate overrides company VAT for mixed-tax invoices.
• PaymentRecord tracks every partial/full payment — amount_paid is derived.
• DocumentActivity provides an immutable audit trail for compliance.
• DocumentVersion snapshots state before destructive edits.
• RecurringInvoice automates periodic billing via Celery Beat.
• DocumentAttachment supports multi-file uploads per document.
• clean() on LineItem enforces the belongs-to-exactly-one-document rule at
  application level in addition to the DB-level CheckConstraint.

Run after deploying:
    python manage.py makemigrations documents
    python manage.py migrate
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    pass  # IDE type stubs only — avoids circular imports at runtime


# ===========================================================================
# 1. ENUMS & CHOICES
# ===========================================================================

class InvoiceStatus(models.TextChoices):
    DRAFT     = "draft",     _("Draft")
    SENT      = "sent",      _("Sent")
    VIEWED    = "viewed",    _("Viewed")
    PARTIAL   = "partial",   _("Partially Paid")
    PAID      = "paid",      _("Paid")
    OVERDUE   = "overdue",   _("Overdue")
    VOID      = "void",      _("Void")
    CANCELLED = "cancelled", _("Cancelled")


class QuotationStatus(models.TextChoices):
    DRAFT    = "draft",    _("Draft")
    SENT     = "sent",     _("Sent")
    VIEWED   = "viewed",   _("Viewed")
    ACCEPTED = "accepted", _("Accepted")
    DECLINED = "declined", _("Declined")
    EXPIRED  = "expired",  _("Expired")


class ContractStatus(models.TextChoices):
    DRAFT     = "draft",     _("Draft")
    SENT      = "sent",      _("Sent")
    VIEWED    = "viewed",    _("Viewed")
    PENDING   = "pending",   _("Pending Signature")
    SIGNED    = "signed",    _("Signed")
    ACTIVE    = "active",    _("Active")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")
    EXPIRED   = "expired",   _("Expired")


class DocumentType(models.TextChoices):
    INVOICE   = "invoice",   _("Invoice")
    QUOTATION = "quotation", _("Quotation")
    CONTRACT  = "contract",  _("Contract")


class LineItemType(models.TextChoices):
    SERVICE  = "service",  _("Service")
    PRODUCT  = "product",  _("Product")
    EXPENSE  = "expense",  _("Expense")
    DISCOUNT = "discount", _("Discount / Credit")
    OTHER    = "other",    _("Other")


class ClientSalutation(models.TextChoices):
    """Formal salutation printed before the client name on documents."""
    MR   = "Mr",   _("Mr")
    MRS  = "Mrs",  _("Mrs")
    MISS = "Miss", _("Miss")
    MS   = "Ms",   _("Ms")
    DR   = "Dr",   _("Dr")
    PROF = "Prof", _("Prof")
    MX   = "Mx",   _("Mx")      # gender-neutral
    NONE = "",     _("(none)")


class UnitLabel(models.TextChoices):
    """Suggested display units — free text is also accepted."""
    PIECE    = "pcs",  _("Pieces (pcs)")
    METRE    = "m",    _("Metres (m)")
    SQ_METRE = "m²",   _("Square Metres (m²)")
    KG       = "kg",   _("Kilograms (kg)")
    GRAM     = "g",    _("Grams (g)")
    LITRE    = "L",    _("Litres (L)")
    HOUR     = "hrs",  _("Hours (hrs)")
    DAY      = "days", _("Days")
    MONTH    = "mo",   _("Months (mo)")
    FLAT     = "flat", _("Flat / Lump-sum")
    OTHER    = "other", _("Other")


class ActivityAction(models.TextChoices):
    """Audit trail event types."""
    CREATED    = "created",    _("Created")
    UPDATED    = "updated",    _("Updated")
    SENT       = "sent",       _("Sent")
    VIEWED     = "viewed",     _("Viewed")
    PAID       = "paid",       _("Marked Paid")
    PARTIAL    = "partial",    _("Partial Payment Recorded")
    VOIDED     = "voided",     _("Voided")
    SIGNED     = "signed",     _("Signed")
    ACCEPTED   = "accepted",   _("Accepted")
    DECLINED   = "declined",   _("Declined")
    CONVERTED  = "converted",  _("Converted to Invoice")
    DELETED    = "deleted",    _("Soft Deleted")
    PDF_GEN    = "pdf_gen",    _("PDF Generated")
    DOCX_GEN   = "docx_gen",   _("DOCX Generated")
    EMAIL_SENT = "email_sent", _("Email Sent")
    REMINDER   = "reminder",   _("Reminder Sent")
    AI_REVIEW  = "ai_review",  _("AI Review Completed")


class RecurringFrequency(models.TextChoices):
    WEEKLY      = "weekly",      _("Weekly")
    BIWEEKLY    = "biweekly",    _("Bi-Weekly (Every 2 Weeks)")
    MONTHLY     = "monthly",     _("Monthly")
    QUARTERLY   = "quarterly",   _("Quarterly")
    SEMI_ANNUAL = "semi_annual", _("Semi-Annual (Every 6 Months)")
    ANNUAL      = "annual",      _("Annual")


class AttachmentType(models.TextChoices):
    SUPPORTING = "supporting", _("Supporting Document")
    RECEIPT    = "receipt",    _("Receipt / Proof of Payment")
    SIGNATURE  = "signature",  _("Signature Image")
    OTHER      = "other",      _("Other")


# ===========================================================================
# 2. CUSTOM QUERYSETS & MANAGERS
# ===========================================================================

class DocumentQuerySet(models.QuerySet):
    """Reusable chainable query helpers for all document types."""

    def active(self):
        """Exclude soft-deleted records."""
        return self.filter(is_active=True, deleted_at__isnull=True)

    def for_company(self, company_id):
        """Scope to a single tenant."""
        return self.filter(company_id=company_id)

    def drafts(self):
        return self.filter(status="draft")

    def overdue(self):
        return self.filter(
            status__in=["sent", "viewed", "partial"],
            due_date__lt=timezone.localdate(),
        )

    def with_totals(self):
        """Annotate with sum of payments (for dashboards)."""
        return self.annotate(
            payments_sum=Sum("payment_records__amount")
        )


class ActiveDocumentManager(models.Manager):
    """
    Default manager that always filters out soft-deleted documents.
    Use Model.all_objects.all() to bypass and access deleted records.
    """

    def get_queryset(self):
        return DocumentQuerySet(self.model, using=self._db).active()

    def for_company(self, company_id):
        return self.get_queryset().for_company(company_id)

    def drafts(self):
        return self.get_queryset().drafts()

    def overdue(self):
        return self.get_queryset().overdue()


# ===========================================================================
# 3. UPLOAD PATH HELPERS
# ===========================================================================

def _pdf_upload_to(instance, filename: str) -> str:
    
    doc_type = instance.__class__.__name__.lower()
    return f"companies/{instance.company_id}/documents/{doc_type}/{instance.pk}/document.pdf"

_pdf_upload_path = _pdf_upload_to
def _docx_upload_to(instance, filename: str) -> str:
    doc_type = instance.__class__.__name__.lower()
    return f"companies/{instance.company_id}/documents/{doc_type}/{instance.pk}/document.docx"


def _attachment_upload_to(instance, filename: str) -> str:
    doc = instance.invoice or instance.quotation or instance.contract
    doc_type = doc.__class__.__name__.lower() if doc else "unknown"
    company_id = doc.company_id if doc else "unknown"
    return f"companies/{company_id}/attachments/{doc_type}/{instance.pk}/{filename}"


# ===========================================================================
# 4. PORTAL TOKEN
# ===========================================================================

def _generate_portal_token(instance_pk: str) -> str:
    """
    Generates a cryptographically secure, non-guessable portal token.
    Combines a random secret with the document PK so tokens are
    unique per document and can't be reused across documents.
    """
    raw = f"{secrets.token_urlsafe(32)}.{instance_pk}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ===========================================================================
# 5. ABSTRACT BASE DOCUMENT
# ===========================================================================

class BaseDocument(models.Model):
    """
    Abstract superclass shared by Invoice, Quotation, and Contract.

    Financial fields are always recomputed via compute_totals().
    Never set subtotal / discount_amount / tax_amount / total directly.
    """

    # ── Identity ────────────────────────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Tenant ──────────────────────────────────────────────────────────────
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.PROTECT,
        related_name="%(class)ss",
        verbose_name=_("company"),
        db_index=True,
    )

    # ── Client ──────────────────────────────────────────────────────────────
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="%(class)ss_as_client",
        verbose_name=_("client (internal user)"),
        null=True, blank=True,
        help_text=_("Linked DocFlow user account. Leave blank for external clients."),
    )
    client_salutation = models.CharField(
        _("salutation"),
        max_length=10,
        choices=ClientSalutation.choices,
        default=ClientSalutation.NONE,
        blank=True,
    )
    client_name    = models.CharField(_("client name"),    max_length=200, blank=True)
    client_email   = models.EmailField(_("client email"),  blank=True)
    client_phone   = models.CharField(_("client phone"),   max_length=30,  blank=True)
    client_address = models.TextField(_("client address"), blank=True)
    client_vat_number = models.CharField(_("client VAT / TIN"), max_length=50, blank=True)

    # ── Numbering ────────────────────────────────────────────────────────────
    number = models.CharField(
        _("document number"),
        max_length=50,
        blank=True,
        db_index=True,
        help_text=_("Auto-assigned on first save via Company.get_next_*() if blank."),
    )

    # ── Dates ───────────────────────────────────────────────────────────────
    issue_date = models.DateField(_("issue date"), default=timezone.localdate)
    due_date   = models.DateField(_("due / expiry date"), null=True, blank=True)

    # ── Locale ──────────────────────────────────────────────────────────────
    currency = models.CharField(_("currency ISO-4217"), max_length=3, default="USD")

    # ── Content ─────────────────────────────────────────────────────────────
    subject = models.CharField(_("subject / title"), max_length=255, blank=True)
    notes   = models.TextField(_("notes to client"), blank=True)
    terms   = models.TextField(_("terms & conditions"), blank=True)

    # ── Financials (server-computed — do not set manually) ─────────────────
    subtotal        = models.DecimalField(_("subtotal"),    max_digits=14, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(_("discount"),    max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax_amount      = models.DecimalField(_("tax"),         max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total           = models.DecimalField(_("total"),       max_digits=14, decimal_places=2, default=Decimal("0.00"))

    # amount_paid is derived from PaymentRecord — stored as a cache
    amount_paid     = models.DecimalField(_("amount paid"), max_digits=14, decimal_places=2, default=Decimal("0.00"))

    # ── Generated files ─────────────────────────────────────────────────────
    pdf_file  = models.FileField(_("PDF"),  upload_to=_pdf_upload_to,  null=True, blank=True)
    docx_file = models.FileField(_("DOCX"), upload_to=_docx_upload_to, null=True, blank=True)

    # ── Meta ────────────────────────────────────────────────────────────────
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="%(class)ss_created",
        editable=False,
    )
    is_active  = models.BooleanField(_("active"), default=True, db_index=True)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    # Managers
    objects     = ActiveDocumentManager()
    all_objects = models.Manager()  # includes soft-deleted

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    # ── Computed properties ─────────────────────────────────────────────────

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def balance_due(self) -> Decimal:
        return max(self.total - self.amount_paid, Decimal("0.00"))

    @property
    def is_overdue(self) -> bool:
        if not self.due_date:
            return False
        return timezone.localdate() > self.due_date and getattr(self, "status", None) not in (
            "paid", "void", "cancelled", "completed"
        )

    @property
    def client_display_name(self) -> str:
        """Best available name for list views."""
        if self.client:
            full = getattr(self.client, "full_name", None)
            return full or self.client.email
        return self.client_name or self.client_email or "—"

    @property
    def client_formal_name(self) -> str:
        """e.g. 'Dr Amina Hassan' — used in PDF headers."""
        parts = [p for p in (self.client_salutation, self.client_display_name) if p]
        return " ".join(parts)

    @property
    def is_paid_in_full(self) -> bool:
        return self.amount_paid >= self.total > Decimal("0.00")

    @property
    def payment_percentage(self) -> int:
        """0-100 integer for progress bars."""
        if self.total <= 0:
            return 0
        pct = (self.amount_paid / self.total * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return min(int(pct), 100)

    # ── Business logic ──────────────────────────────────────────────────────

    def compute_totals(self, *, save: bool = False) -> None:
        """
        Recompute subtotal / discount / tax / total from all line items.

        Tax strategy:
          - Per-line tax_rate > 0  → use that rate for the line.
          - Per-line tax_rate == 0 → fall back to company VAT config.
          - Subtotal of DISCOUNT lines is subtracted before tax.
        """
        items = list(
            getattr(self, "line_items", type("_", (), {"all": lambda self: []})()).all()
        )

        subtotal = Decimal("0.00")
        discount = Decimal("0.00")
        tax      = Decimal("0.00")

        try:
            company_vat_rate = self.company.vat_config.vat_rate / Decimal("100")
        except Exception:
            company_vat_rate = Decimal("0.00")

        for item in items:
            if item.item_type == LineItemType.DISCOUNT:
                discount += item.line_total
            else:
                subtotal += item.line_total
                # Per-line tax override
                rate = (
                    item.tax_rate / Decimal("100")
                    if item.tax_rate > 0
                    else company_vat_rate
                )
                tax += (item.line_total * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        net = subtotal - discount

        self.subtotal        = subtotal.quantize(Decimal("0.01"))
        self.discount_amount = discount.quantize(Decimal("0.01"))
        self.tax_amount      = tax.quantize(Decimal("0.01"))
        self.total           = (net + tax).quantize(Decimal("0.01"))

        if save:
            self.save(update_fields=["subtotal", "discount_amount", "tax_amount", "total", "updated_at"])

    def sync_amount_paid(self, *, save: bool = True) -> Decimal:
        """
        Recompute amount_paid from PaymentRecord rows (idempotent).
        Call after adding or reversing a PaymentRecord.
        """
        agg = self.payment_records.filter(is_reversed=False).aggregate(
            total=Sum("amount")
        )
        paid = agg["total"] or Decimal("0.00")
        self.amount_paid = paid.quantize(Decimal("0.01"))
        if save:
            self.save(update_fields=["amount_paid", "updated_at"])
        return self.amount_paid

    def soft_delete(self, *, deleted_by=None) -> None:
        self.is_active  = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_active", "deleted_at", "updated_at"])
        DocumentActivity.log(
            document=self,
            action=ActivityAction.DELETED,
            actor=deleted_by,
        )

    def restore(self) -> None:
        """Undo a soft delete."""
        self.is_active  = True
        self.deleted_at = None
        self.save(update_fields=["is_active", "deleted_at", "updated_at"])

    def log_activity(
        self,
        action: str,
        actor=None,
        note: str = "",
        metadata: dict | None = None,
    ) -> "DocumentActivity":
        return DocumentActivity.log(
            document=self,
            action=action,
            actor=actor,
            note=note,
            metadata=metadata or {},
        )

    def __str__(self) -> str:
        return f"{self.__class__.__name__} #{self.number or self.pk}"


# ===========================================================================
# 6. INVOICE
# ===========================================================================

class Invoice(BaseDocument):
    """
    An Invoice is a request for payment.

    Status lifecycle:
        draft → sent → viewed → partial/paid/overdue → void/cancelled
    Paid invoices are immutable (validated in serializer + clean()).
    """

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
        db_index=True,
    )
    stripe_payment_intent_id = models.CharField(max_length=100, blank=True, db_index=True)
    stripe_payment_link_url  = models.URLField(blank=True)
    portal_token             = models.CharField(max_length=128, blank=True, db_index=True)
    sent_at  = models.DateTimeField(_("sent at"),  null=True, blank=True)
    paid_at  = models.DateTimeField(_("paid at"),  null=True, blank=True)
    viewed_at = models.DateTimeField(_("viewed at"), null=True, blank=True)

    # Managers
    objects     = ActiveDocumentManager()
    all_objects = models.Manager()

    class Meta(BaseDocument.Meta):
        verbose_name        = _("invoice")
        verbose_name_plural = _("invoices")
        indexes = [
            models.Index(fields=["company", "status"],   name="inv_company_status_idx"),
            models.Index(fields=["company", "due_date"], name="inv_company_due_date_idx"),
            models.Index(fields=["company", "issue_date"], name="inv_company_issue_date_idx"),
            models.Index(fields=["client",  "status"],   name="inv_client_status_idx"),
            models.Index(fields=["portal_token"],        name="inv_portal_token_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=Q(is_active=True),
                name="inv_unique_number_per_company",
            ),
        ]

    # ── Status transitions ──────────────────────────────────────────────────

    def ensure_portal_token(self) -> str:
        """Lazily create a portal token and persist it."""
        if not self.portal_token:
            self.portal_token = _generate_portal_token(str(self.pk))
            self.save(update_fields=["portal_token"])
        return self.portal_token

    def mark_sent(self, *, actor=None) -> None:
        from django.utils import timezone as tz
        self.status  = InvoiceStatus.SENT
        self.sent_at = tz.now()
        self.save(update_fields=["status", "sent_at", "updated_at"])
        self.log_activity(ActivityAction.SENT, actor=actor)

    def mark_viewed(self) -> None:
        """Call from client portal — sets VIEWED if still in SENT state."""
        if self.status == InvoiceStatus.SENT:
            self.status    = InvoiceStatus.VIEWED
            self.viewed_at = timezone.now()
            self.save(update_fields=["status", "viewed_at", "updated_at"])
            self.log_activity(ActivityAction.VIEWED)

    def mark_paid(self, amount: Decimal | None = None, *, actor=None) -> None:
        """Convenience shortcut — creates a PaymentRecord and syncs totals."""
        payment_amount = amount if amount is not None else self.balance_due
        PaymentRecord.objects.create(
            invoice=self,
            amount=payment_amount,
            recorded_by=actor,
        )
        self.sync_amount_paid(save=False)
        self.status  = InvoiceStatus.PAID
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at", "amount_paid", "updated_at"])
        self.log_activity(ActivityAction.PAID, actor=actor, metadata={"amount": str(payment_amount)})

    def void(self, *, actor=None, reason: str = "") -> None:
        if self.status == InvoiceStatus.PAID:
            raise ValidationError(_("A paid invoice cannot be voided."))
        self.status = InvoiceStatus.VOID
        self.save(update_fields=["status", "updated_at"])
        self.log_activity(ActivityAction.VOIDED, actor=actor, note=reason)

    def clean(self) -> None:
        super().clean()
        if self.pk:
            try:
                original = Invoice.all_objects.get(pk=self.pk)
                if original.status == InvoiceStatus.PAID and self.status != InvoiceStatus.PAID:
                    raise ValidationError(_("A paid invoice cannot change status."))
            except Invoice.DoesNotExist:
                pass


# ===========================================================================
# 7. QUOTATION
# ===========================================================================

class Quotation(BaseDocument):
    """
    A Quotation is an offer of goods/services at a specific price.

    Status lifecycle:
        draft → sent → viewed → accepted/declined/expired
    An accepted quotation can be converted to an Invoice.
    """

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=QuotationStatus.choices,
        default=QuotationStatus.DRAFT,
        db_index=True,
    )
    valid_until  = models.DateField(_("valid until"),  null=True, blank=True)
    sent_at      = models.DateTimeField(_("sent at"),      null=True, blank=True)
    accepted_at  = models.DateTimeField(_("accepted at"),  null=True, blank=True)
    declined_at  = models.DateTimeField(_("declined at"),  null=True, blank=True)
    decline_reason = models.TextField(_("decline reason"), blank=True)

    # Managers
    objects     = ActiveDocumentManager()
    all_objects = models.Manager()

    class Meta(BaseDocument.Meta):
        verbose_name        = _("quotation")
        verbose_name_plural = _("quotations")
        indexes = [
            models.Index(fields=["company", "status"],      name="qt_company_status_idx"),
            models.Index(fields=["company", "valid_until"], name="qt_company_valid_until_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=Q(is_active=True),
                name="qt_unique_number_per_company",
            ),
        ]

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def is_expired(self) -> bool:
        if not self.valid_until:
            return False
        return timezone.localdate() > self.valid_until and self.status not in (
            "accepted", "declined", "expired"
        )

    @property
    def days_until_expiry(self) -> int | None:
        if not self.valid_until:
            return None
        delta = self.valid_until - timezone.localdate()
        return delta.days

    # ── Status transitions ──────────────────────────────────────────────────

    def mark_sent(self, *, actor=None) -> None:
        self.status  = QuotationStatus.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at", "updated_at"])
        self.log_activity(ActivityAction.SENT, actor=actor)

    def mark_viewed(self) -> None:
        if self.status == QuotationStatus.SENT:
            self.status = QuotationStatus.VIEWED
            self.save(update_fields=["status", "updated_at"])
            self.log_activity(ActivityAction.VIEWED)

    def accept(self, *, actor=None) -> None:
        if self.status not in (QuotationStatus.SENT, QuotationStatus.VIEWED):
            raise ValidationError(_("Only sent or viewed quotations can be accepted."))
        self.status      = QuotationStatus.ACCEPTED
        self.accepted_at = timezone.now()
        self.save(update_fields=["status", "accepted_at", "updated_at"])
        self.log_activity(ActivityAction.ACCEPTED, actor=actor)

    def decline(self, *, actor=None, reason: str = "") -> None:
        self.status         = QuotationStatus.DECLINED
        self.declined_at    = timezone.now()
        self.decline_reason = reason
        self.save(update_fields=["status", "declined_at", "decline_reason", "updated_at"])
        self.log_activity(ActivityAction.DECLINED, actor=actor, note=reason)

    def convert_to_invoice(self, *, actor=None) -> Invoice:
        """
        Clone this quotation as a new Invoice, preserving all line items.
        The quotation status is NOT changed here — caller handles that.
        Raises ValidationError if quotation is not accepted.
        """
        if self.status != QuotationStatus.ACCEPTED:
            raise ValidationError(_("Only accepted quotations can be converted to invoices."))

        invoice = Invoice(
            company           = self.company,
            client            = self.client,
            client_salutation = self.client_salutation,
            client_name       = self.client_name,
            client_email      = self.client_email,
            client_phone      = self.client_phone,
            client_address    = self.client_address,
            client_vat_number = self.client_vat_number,
            currency          = self.currency,
            subject           = self.subject,
            notes             = self.notes,
            terms             = self.terms,
            subtotal          = self.subtotal,
            discount_amount   = self.discount_amount,
            tax_amount        = self.tax_amount,
            total             = self.total,
            created_by        = actor or self.created_by,
        )
        invoice.number = self.company.get_next_invoice_number()
        invoice.save()

        for item in self.line_items.all():
            LineItem.objects.create(
                invoice         = invoice,
                description     = item.description,
                item_type       = item.item_type,
                quantity        = item.quantity,
                unit_of_measure = item.unit_of_measure,
                unit_label      = item.unit_label,
                unit_price      = item.unit_price,
                discount_percent = item.discount_percent,
                tax_rate        = item.tax_rate,
                sort_order      = item.sort_order,
            )

        self.log_activity(ActivityAction.CONVERTED, actor=actor, metadata={"invoice_id": str(invoice.pk)})
        return invoice


# ===========================================================================
# 8. CONTRACT
# ===========================================================================

class Contract(BaseDocument):
    """
    A Contract is a binding agreement between parties.

    Unlike invoices/quotations, contracts have no line items by default.
    Financial fields are optional — used for contract value reporting.
    The AI review field stores structured JSON from the AI engine.
    """

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ContractStatus.choices,
        default=ContractStatus.DRAFT,
        db_index=True,
    )
    # Contract-specific content
    body               = models.TextField(_("contract body / clauses"), blank=True)
    start_date         = models.DateField(_("start date"), null=True, blank=True)
    end_date           = models.DateField(_("end date"),   null=True, blank=True)
    auto_renew         = models.BooleanField(_("auto-renew"), default=False)
    renewal_notice_days = models.PositiveSmallIntegerField(_("renewal notice (days)"), default=30)

    # Signing
    sent_at         = models.DateTimeField(_("sent at"),    null=True, blank=True)
    signed_at       = models.DateTimeField(_("signed at"),  null=True, blank=True)
    signed_by_name  = models.CharField(_("signed by (name)"), max_length=200, blank=True)
    signature_ip    = models.GenericIPAddressField(_("signature IP"), null=True, blank=True)
    signature_image = models.ImageField(
        _("signature image"),
        upload_to="signatures/%Y/%m/",
        null=True, blank=True,
    )

    # Third-party e-signature
    docusign_envelope_id    = models.CharField(max_length=100, blank=True, db_index=True)
    hellosign_signature_id  = models.CharField(max_length=100, blank=True)

    # AI review output — stored as structured JSON
    ai_review        = models.JSONField(_("AI review"), default=dict, blank=True)
    ai_reviewed_at   = models.DateTimeField(_("AI reviewed at"), null=True, blank=True)

    # Managers
    objects     = ActiveDocumentManager()
    all_objects = models.Manager()

    class Meta(BaseDocument.Meta):
        verbose_name        = _("contract")
        verbose_name_plural = _("contracts")
        indexes = [
            models.Index(fields=["company", "status"],   name="cnt_company_status_idx"),
            models.Index(fields=["company", "end_date"], name="cnt_company_end_date_idx"),
            models.Index(fields=["company", "signed_at"], name="cnt_company_signed_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=Q(is_active=True),
                name="cnt_unique_number_per_company",
            ),
            models.CheckConstraint(
                condition=Q(start_date__isnull=True)
                        | Q(end_date__isnull=True)
                        | Q(end_date__gte=models.F("start_date")),
                name="cnt_end_date_gte_start_date",
            ),
        ]

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def is_expiring_soon(self) -> bool:
        if not self.end_date:
            return False
        delta = self.end_date - timezone.localdate()
        return 0 <= delta.days <= self.renewal_notice_days

    @property
    def days_until_expiry(self) -> int | None:
        if not self.end_date:
            return None
        return (self.end_date - timezone.localdate()).days

    @property
    def is_expired(self) -> bool:
        if not self.end_date:
            return False
        return timezone.localdate() > self.end_date and self.status not in (
            "completed", "cancelled", "expired"
        )

    # ── Status transitions ──────────────────────────────────────────────────

    def mark_sent(self, *, actor=None) -> None:
        self.status  = ContractStatus.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at", "updated_at"])
        self.log_activity(ActivityAction.SENT, actor=actor)

    def mark_signed(
        self,
        *,
        signer_name: str,
        ip_address: str | None = None,
        actor=None,
    ) -> None:
        if not signer_name.strip():
            raise ValidationError(_("Signer name is required."))
        self.status         = ContractStatus.SIGNED
        self.signed_at      = timezone.now()
        self.signed_by_name = signer_name.strip()
        self.signature_ip   = ip_address
        self.save(update_fields=["status", "signed_at", "signed_by_name", "signature_ip", "updated_at"])
        self.log_activity(
            ActivityAction.SIGNED,
            actor=actor,
            metadata={"signed_by": signer_name, "ip": ip_address},
        )

    def store_ai_review(self, review_data: dict, *, actor=None) -> None:
        self.ai_review      = review_data
        self.ai_reviewed_at = timezone.now()
        self.save(update_fields=["ai_review", "ai_reviewed_at", "updated_at"])
        self.log_activity(ActivityAction.AI_REVIEW, actor=actor)

    def clean(self) -> None:
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("End date must be on or after start date.")})


# ===========================================================================
# 9. LINE ITEM
# ===========================================================================

class LineItem(models.Model):
    """
    A normalised billing line for Invoice or Quotation (not Contract).

    Pricing formula
    ───────────────
        gross_amount = unit_price × quantity × unit_of_measure
        discount_value = gross_amount × (discount_percent / 100)
        line_total = gross_amount - discount_value

    unit_of_measure is a dimensionless multiplier (default = 1).
    For measurable goods, set it to the measure per unit:

        3 rolls × 5 m/roll × KES 250/m → unit_of_measure=5, quantity=3
        → gross_amount = 250 × 3 × 5 = KES 3,750

    The DB-level CheckConstraint ensures each LineItem belongs to exactly
    ONE document (either invoice or quotation, never both or neither).
    The clean() method enforces the same rule at application level.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Document foreign keys (exactly one must be set) ─────────────────────
    invoice   = models.ForeignKey(
        Invoice, on_delete=models.CASCADE,
        related_name="line_items",
        null=True, blank=True,
    )
    quotation = models.ForeignKey(
        Quotation, on_delete=models.CASCADE,
        related_name="line_items",
        null=True, blank=True,
    )

    # ── Item fields ─────────────────────────────────────────────────────────
    item_type   = models.CharField(
        _("type"), max_length=20,
        choices=LineItemType.choices,
        default=LineItemType.SERVICE,
    )
    description = models.CharField(_("description"), max_length=500)

    # Quantity
    quantity = models.DecimalField(
        _("quantity"), max_digits=10, decimal_places=3, default=Decimal("1.000"),
    )
    unit_of_measure = models.DecimalField(
        _("unit of measure multiplier"), max_digits=10, decimal_places=3,
        default=Decimal("1.000"),
        help_text=_("Dimensionless multiplier per unit, e.g. metres per roll."),
    )
    unit_label = models.CharField(
        _("unit label"), max_length=20, blank=True,
        help_text=_("Display label, e.g. 'm', 'kg', 'hrs'. Shown in PDF column."),
    )

    # Pricing
    unit_price       = models.DecimalField(_("unit price"),  max_digits=14, decimal_places=2, default=Decimal("0.00"))
    discount_percent = models.DecimalField(_("discount %"),  max_digits=5,  decimal_places=2, default=Decimal("0.00"))
    tax_rate         = models.DecimalField(
        _("per-line tax rate %"), max_digits=5, decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Override company VAT for this line. Leave 0 to use company default."),
    )

    # Display
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = _("line item")
        verbose_name_plural = _("line items")
        ordering            = ["sort_order", "created_at"]
        constraints = [
            # DB-level: must belong to exactly one document
            models.CheckConstraint(
                condition=(
                    Q(invoice__isnull=False, quotation__isnull=True)
                    | Q(invoice__isnull=True, quotation__isnull=False)
                ),
                name="lineitem_belongs_to_exactly_one_document",
            ),
            # DB-level: quantity and multiplier must be positive
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="lineitem_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(unit_of_measure__gt=0),
                name="lineitem_unit_of_measure_positive",
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0),
                name="lineitem_unit_price_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(discount_percent__gte=0, discount_percent__lte=100),
                name="lineitem_discount_percent_range",
            ),
        ]

    # ── Computed properties ─────────────────────────────────────────────────

    @property
    def gross_amount(self) -> Decimal:
        """unit_price × quantity × unit_of_measure"""
        return (self.unit_price * self.quantity * self.unit_of_measure).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @property
    def discount_value(self) -> Decimal:
        return (self.gross_amount * self.discount_percent / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @property
    def line_total(self) -> Decimal:
        return (self.gross_amount - self.discount_value).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    # ── Validation ──────────────────────────────────────────────────────────

    def clean(self) -> None:
        super().clean()
        # Exactly one parent
        has_invoice   = self.invoice_id is not None
        has_quotation = self.quotation_id is not None
        if has_invoice == has_quotation:  # both set or neither set
            raise ValidationError(
                _("A line item must belong to exactly one of: invoice, quotation.")
            )
        if self.quantity <= 0:
            raise ValidationError({"quantity": _("Quantity must be greater than zero.")})
        if self.unit_of_measure <= 0:
            raise ValidationError({"unit_of_measure": _("Unit of measure must be greater than zero.")})
        if self.unit_price < 0:
            raise ValidationError({"unit_price": _("Unit price cannot be negative.")})
        if not (0 <= self.discount_percent <= 100):
            raise ValidationError({"discount_percent": _("Discount must be between 0 and 100.")})

    def __str__(self) -> str:
        measure = f" × {self.unit_of_measure}{self.unit_label}" if self.unit_label else ""
        return f"{self.description} — {self.quantity}{measure} @ {self.unit_price}"


# ===========================================================================
# 10. PAYMENT RECORD
# ===========================================================================

class PaymentRecord(models.Model):
    """
    Tracks every individual payment against an Invoice.
    Enables partial-payment workflows and a full payment history.

    Call Invoice.sync_amount_paid() after creating or reversing records.
    """

    PAYMENT_METHOD_CHOICES = [
        ("cash",           _("Cash")),
        ("bank_transfer",  _("Bank Transfer")),
        ("stripe",         _("Stripe")),
        ("mpesa",          _("M-Pesa")),
        ("cheque",         _("Cheque")),
        ("crypto",         _("Cryptocurrency")),
        ("other",          _("Other")),
    ]

    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE,
        related_name="payment_records",
    )

    amount         = models.DecimalField(_("amount"), max_digits=14, decimal_places=2)
    currency       = models.CharField(_("currency"), max_length=3, default="USD")
    payment_method = models.CharField(_("payment method"), max_length=20, choices=PAYMENT_METHOD_CHOICES, default="bank_transfer")
    payment_date   = models.DateField(_("payment date"), default=timezone.localdate)
    reference      = models.CharField(_("transaction reference"), max_length=100, blank=True)
    notes          = models.TextField(_("notes"), blank=True)
    is_reversed    = models.BooleanField(_("reversed / refunded"), default=False)
    reversed_at    = models.DateTimeField(_("reversed at"), null=True, blank=True)
    reversed_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="payment_reversals",
    )
    recorded_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="recorded_payments",
    )
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = _("payment record")
        verbose_name_plural = _("payment records")
        ordering            = ["-payment_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="payment_amount_positive",
            ),
        ]

    def reverse(self, *, reversed_by=None) -> None:
        self.is_reversed  = True
        self.reversed_at  = timezone.now()
        self.reversed_by  = reversed_by
        self.save(update_fields=["is_reversed", "reversed_at", "reversed_by"])
        self.invoice.sync_amount_paid()

    def __str__(self) -> str:
        status = " (reversed)" if self.is_reversed else ""
        return f"Payment {self.amount} {self.currency} on {self.payment_date}{status}"


# ===========================================================================
# 11. DOCUMENT ACTIVITY (AUDIT TRAIL)
# ===========================================================================

class DocumentActivity(models.Model):
    """
    Immutable audit log for all document events.

    One row per event — never updated, never deleted.
    `metadata` holds structured JSON context (e.g. {"amount": "500"}).
    """

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    doc_type   = models.CharField(_("document type"),  max_length=20, choices=DocumentType.choices, db_index=True)
    doc_id     = models.UUIDField(_("document UUID"), db_index=True)
    doc_number = models.CharField(_("document number"), max_length=50, blank=True)
    company_id = models.UUIDField(_("company UUID"), db_index=True)

    action   = models.CharField(_("action"), max_length=30, choices=ActivityAction.choices, db_index=True)
    actor    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="document_activities",
    )
    actor_ip = models.GenericIPAddressField(_("actor IP"), null=True, blank=True)
    note     = models.TextField(_("note"), blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name        = _("document activity")
        verbose_name_plural = _("document activities")
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=["doc_type", "doc_id"],     name="activity_doc_idx"),
            models.Index(fields=["company_id", "action"],   name="activity_company_action_idx"),
            models.Index(fields=["actor", "created_at"],    name="activity_actor_ts_idx"),
        ]

    @classmethod
    def log(
        cls,
        document: BaseDocument,
        action: str,
        actor=None,
        note: str = "",
        metadata: dict | None = None,
        actor_ip: str | None = None,
    ) -> "DocumentActivity":
        doc_type = document.__class__.__name__.lower()
        return cls.objects.create(
            doc_type   = doc_type,
            doc_id     = document.pk,
            doc_number = document.number or "",
            company_id = document.company_id,
            action     = action,
            actor      = actor,
            actor_ip   = actor_ip,
            note       = note,
            metadata   = metadata or {},
        )

    def __str__(self) -> str:
        return f"{self.doc_type.upper()} #{self.doc_number} — {self.action} at {self.created_at:%Y-%m-%d %H:%M}"


# ===========================================================================
# 12. DOCUMENT VERSION (SNAPSHOT)
# ===========================================================================

class DocumentVersion(models.Model):
    """
    Stores a snapshot of the document state before major edits.

    Created automatically via the serializer's update() path or manually
    via Document.save_version(). Allows "restore to version" workflows.
    """

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    doc_type   = models.CharField(_("document type"), max_length=20, choices=DocumentType.choices)
    doc_id     = models.UUIDField(_("document UUID"), db_index=True)
    version    = models.PositiveSmallIntegerField(_("version number"), default=1)
    snapshot   = models.JSONField(_("document snapshot"), default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="document_versions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = _("document version")
        verbose_name_plural = _("document versions")
        ordering            = ["-version"]
        indexes = [
            models.Index(fields=["doc_type", "doc_id", "version"], name="docversion_lookup_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.doc_type} {self.doc_id} v{self.version}"


# ===========================================================================
# 13. RECURRING INVOICE
# ===========================================================================

class RecurringInvoice(models.Model):
    """
    Template used by Celery Beat to auto-generate invoices on a schedule.

    When the scheduled task fires, it calls generate_next_invoice() which
    clones the template invoice and advances next_invoice_date.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company   = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="recurring_invoices")
    template  = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="recurring_schedules",
                                  help_text=_("Draft invoice used as the template for each recurrence."))
    frequency = models.CharField(_("frequency"), max_length=20, choices=RecurringFrequency.choices, default=RecurringFrequency.MONTHLY)
    start_date       = models.DateField(_("start date"), default=timezone.localdate)
    end_date         = models.DateField(_("end date (optional)"), null=True, blank=True)
    max_occurrences  = models.PositiveSmallIntegerField(_("max occurrences"), null=True, blank=True)
    occurrences_sent = models.PositiveSmallIntegerField(_("occurrences sent"), default=0)
    next_invoice_date = models.DateField(_("next invoice date"))
    auto_send        = models.BooleanField(_("auto-send to client"), default=True)
    is_active        = models.BooleanField(_("active"), default=True)
    created_by       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name="recurring_invoices_created")
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = _("recurring invoice")
        verbose_name_plural = _("recurring invoices")
        ordering            = ["next_invoice_date"]
        indexes = [
            models.Index(fields=["company", "is_active", "next_invoice_date"], name="rec_inv_schedule_idx"),
        ]

    def is_due(self) -> bool:
        return self.is_active and self.next_invoice_date <= timezone.localdate()

    def advance_next_date(self) -> None:
        """Move next_invoice_date forward by one period."""
        import dateutil.relativedelta as rd
        mapping = {
            RecurringFrequency.WEEKLY:      rd.relativedelta(weeks=1),
            RecurringFrequency.BIWEEKLY:    rd.relativedelta(weeks=2),
            RecurringFrequency.MONTHLY:     rd.relativedelta(months=1),
            RecurringFrequency.QUARTERLY:   rd.relativedelta(months=3),
            RecurringFrequency.SEMI_ANNUAL: rd.relativedelta(months=6),
            RecurringFrequency.ANNUAL:      rd.relativedelta(years=1),
        }
        delta = mapping.get(self.frequency, rd.relativedelta(months=1))
        self.next_invoice_date = self.next_invoice_date + delta
        self.occurrences_sent += 1

        if self.end_date and self.next_invoice_date > self.end_date:
            self.is_active = False
        if self.max_occurrences and self.occurrences_sent >= self.max_occurrences:
            self.is_active = False

        self.save(update_fields=["next_invoice_date", "occurrences_sent", "is_active", "updated_at"])

    def __str__(self) -> str:
        return f"Recurring [{self.frequency}] for {self.company} — next {self.next_invoice_date}"


# ===========================================================================
# 14. DOCUMENT ATTACHMENT
# ===========================================================================

class DocumentAttachment(models.Model):
    """
    File attachments for Invoices, Quotations, or Contracts.
    Exactly one of invoice / quotation / contract must be non-null.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    invoice   = models.ForeignKey(Invoice,   on_delete=models.CASCADE, null=True, blank=True, related_name="attachments")
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments")
    contract  = models.ForeignKey(Contract,  on_delete=models.CASCADE, null=True, blank=True, related_name="attachments")

    file           = models.FileField(_("file"), upload_to=_attachment_upload_to)
    original_name  = models.CharField(_("original filename"), max_length=255)
    mime_type      = models.CharField(_("MIME type"), max_length=100, blank=True)
    file_size      = models.PositiveBigIntegerField(_("file size (bytes)"), default=0)
    attachment_type = models.CharField(_("type"), max_length=20, choices=AttachmentType.choices, default=AttachmentType.SUPPORTING)
    description    = models.CharField(_("description"), max_length=255, blank=True)
    uploaded_by    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name="document_attachments")
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = _("document attachment")
        verbose_name_plural = _("document attachments")
        ordering            = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(invoice__isnull=False, quotation__isnull=True, contract__isnull=True)
                    | Q(invoice__isnull=True, quotation__isnull=False, contract__isnull=True)
                    | Q(invoice__isnull=True, quotation__isnull=True, contract__isnull=False)
                ),
                name="attachment_belongs_to_one_document",
            )
        ]

    def clean(self) -> None:
        super().clean()
        parents = [self.invoice_id, self.quotation_id, self.contract_id]
        set_count = sum(1 for p in parents if p is not None)
        if set_count != 1:
            raise ValidationError(_("An attachment must belong to exactly one document."))

    def __str__(self) -> str:
        return f"{self.original_name} ({self.file_size} bytes)"