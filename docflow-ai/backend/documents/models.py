"""
DocFlow AI — documents/models.py  (patched)

Changes vs previous version:
  1. BaseDocument  — added client_salutation (Mr / Mrs / Miss / Dr / Prof / Mx)
  2. LineItem       — added unit_of_measure  (metres, kg, hrs, pcs, …)
                    — added unit_label       (display string, e.g. "m", "kg")
                    — line_total now factors in quantity × unit_of_measure
                      when unit_of_measure is set (price-per-unit × measure × qty)

Run after deploying:
    python manage.py makemigrations documents
    python manage.py migrate
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Enums / choices
# ---------------------------------------------------------------------------

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
    DISCOUNT = "discount", _("Discount")
    OTHER    = "other",    _("Other")


# NEW ─────────────────────────────────────────────────────────────────────────
class ClientSalutation(models.TextChoices):
    """Formal salutation printed before the client name on documents."""
    MR   = "Mr",   _("Mr")
    MRS  = "Mrs",  _("Mrs")
    MISS = "Miss", _("Miss")
    MS   = "Ms",   _("Ms")
    DR   = "Dr",   _("Dr")
    PROF = "Prof", _("Prof")
    MX   = "Mx",   _("Mx")     # gender-neutral
    NONE = "",     _("(none)")


# Common units of measure — used as suggestions; free text is also allowed.
class UnitOfMeasure(models.TextChoices):
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
    OTHER    = "other",_("Other")
# ─────────────────────────────────────────────────────────────────────────────


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pdf_upload_path(instance, filename: str) -> str:
    doc_type = instance.__class__.__name__.lower()
    return f"companies/{instance.company_id}/documents/{doc_type}/{instance.pk}/document.pdf"


def _docx_upload_path(instance, filename: str) -> str:
    doc_type = instance.__class__.__name__.lower()
    return f"companies/{instance.company_id}/documents/{doc_type}/{instance.pk}/document.docx"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseDocument(models.Model):
    """Shared fields for Invoice, Quotation, and Contract."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Tenant isolation
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.PROTECT,
        related_name="%(class)ss",
        verbose_name=_("company"),
    )

    # Parties
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="%(class)ss_as_client",
        verbose_name=_("client"),
        null=True, blank=True,
        help_text=_("Linked DocFlow user. Use client_name/email for external clients."),
    )

    # NEW — salutation printed before client name on the document
    client_salutation = models.CharField(
        _("client salutation"),
        max_length=10,
        choices=ClientSalutation.choices,
        default=ClientSalutation.NONE,
        blank=True,
        help_text=_("e.g. Mr, Mrs, Miss, Dr — printed as 'Dear Mr Smith' on the document."),
    )

    client_name       = models.CharField(_("client name"),    max_length=200, blank=True)
    client_email      = models.EmailField(_("client email"),  blank=True)
    client_phone      = models.CharField(_("client phone"),   max_length=30,  blank=True)
    client_address    = models.TextField(_("client address"), blank=True)
    client_vat_number = models.CharField(_("client VAT/TIN"), max_length=50,  blank=True)

    # Document numbering
    number = models.CharField(
        _("document number"), max_length=30, blank=True,
        help_text=_("Auto-assigned on first save if blank."),
    )

    # Dates
    issue_date = models.DateField(_("issue date"), default=timezone.localdate)
    due_date   = models.DateField(_("due / expiry date"), null=True, blank=True)

    # Currency & locale
    currency = models.CharField(_("currency"), max_length=3, default="USD")

    # Content
    subject = models.CharField(_("subject / title"), max_length=255, blank=True)
    notes   = models.TextField(_("notes to client"), blank=True)
    terms   = models.TextField(_("terms & conditions"), blank=True)

    # Financial totals — always recomputed server-side
    subtotal        = models.DecimalField(_("subtotal"),    max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_amount = models.DecimalField(_("discount"),    max_digits=12, decimal_places=2, default=Decimal("0"))
    tax_amount      = models.DecimalField(_("tax"),         max_digits=12, decimal_places=2, default=Decimal("0"))
    total           = models.DecimalField(_("total"),       max_digits=12, decimal_places=2, default=Decimal("0"))
    amount_paid     = models.DecimalField(_("amount paid"), max_digits=12, decimal_places=2, default=Decimal("0"))

    # Generated files
    pdf_file  = models.FileField(_("PDF file"),  upload_to=_pdf_upload_path,  null=True, blank=True)
    docx_file = models.FileField(_("DOCX file"), upload_to=_docx_upload_path, null=True, blank=True)

    # Meta
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="%(class)ss_created",
    )
    is_active  = models.BooleanField(_("active"), default=True)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def balance_due(self) -> Decimal:
        return max(self.total - self.amount_paid, Decimal("0"))

    @property
    def is_overdue(self) -> bool:
        if not self.due_date:
            return False
        return timezone.localdate() > self.due_date

    @property
    def client_display_name(self) -> str:
        if self.client:
            return self.client.full_name or self.client.email
        return self.client_name or self.client_email or "—"

    @property
    def client_formal_name(self) -> str:
        """Returns e.g. 'Mr John Smith' or 'Dr Amina Hassan' for use in document headers."""
        parts = [p for p in [self.client_salutation, self.client_display_name] if p]
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def compute_totals(self) -> None:
        """Recompute subtotal / discount / tax / total from line items."""
        items    = self.line_items.all()  # type: ignore[attr-defined]
        subtotal = Decimal("0")
        discount = Decimal("0")

        for item in items:
            if item.item_type == LineItemType.DISCOUNT:
                discount += item.line_total
            else:
                subtotal += item.line_total

        net = subtotal - discount

        try:
            vat_config = self.company.vat_config
            vat_rate   = vat_config.vat_rate / Decimal("100")
        except Exception:
            vat_rate = Decimal("0")

        tax = (net * vat_rate).quantize(Decimal("0.01"))

        self.subtotal        = subtotal
        self.discount_amount = discount
        self.tax_amount      = tax
        self.total           = net + tax

    def soft_delete(self) -> None:
        self.is_active  = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_active", "deleted_at", "updated_at"])

    def __str__(self) -> str:
        return f"{self.__class__.__name__} {self.number or self.pk}"


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class Invoice(BaseDocument):

    status = models.CharField(
        _("status"), max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
        db_index=True,
    )
    stripe_payment_intent_id = models.CharField(max_length=100, blank=True)
    stripe_payment_link_url  = models.URLField(blank=True)
    portal_token             = models.CharField(max_length=512, blank=True)
    sent_at                  = models.DateTimeField(_("sent at"), null=True, blank=True)
    paid_at                  = models.DateTimeField(_("paid at"), null=True, blank=True)

    class Meta(BaseDocument.Meta):
        verbose_name        = _("invoice")
        verbose_name_plural = _("invoices")
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["company", "due_date"]),
            models.Index(fields=["client",  "status"]),
        ]

    def mark_sent(self) -> None:
        self.status  = InvoiceStatus.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at", "updated_at"])

    def mark_paid(self, amount: Decimal | None = None) -> None:
        self.amount_paid = amount if amount is not None else self.total
        self.status      = InvoiceStatus.PAID
        self.paid_at     = timezone.now()
        self.save(update_fields=["status", "amount_paid", "paid_at", "updated_at"])


# ---------------------------------------------------------------------------
# Quotation
# ---------------------------------------------------------------------------

class Quotation(BaseDocument):

    status = models.CharField(
        _("status"), max_length=20,
        choices=QuotationStatus.choices,
        default=QuotationStatus.DRAFT,
        db_index=True,
    )
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    sent_at     = models.DateTimeField(_("sent at"),     null=True, blank=True)
    accepted_at = models.DateTimeField(_("accepted at"), null=True, blank=True)

    class Meta(BaseDocument.Meta):
        verbose_name        = _("quotation")
        verbose_name_plural = _("quotations")
        indexes = [models.Index(fields=["company", "status"])]

    def convert_to_invoice(self) -> "Invoice":
        invoice = Invoice(
            company=self.company,
            client=self.client,
            client_salutation=self.client_salutation,
            client_name=self.client_name,
            client_email=self.client_email,
            client_address=self.client_address,
            client_vat_number=self.client_vat_number,
            currency=self.currency,
            subject=self.subject,
            notes=self.notes,
            terms=self.terms,
            subtotal=self.subtotal,
            discount_amount=self.discount_amount,
            tax_amount=self.tax_amount,
            total=self.total,
            created_by=self.created_by,
        )
        invoice.number = self.company.get_next_invoice_number()
        invoice.save()

        for item in self.line_items.all():
            LineItem.objects.create(
                invoice=invoice,
                description=item.description,
                item_type=item.item_type,
                quantity=item.quantity,
                unit_of_measure=item.unit_of_measure,
                unit_label=item.unit_label,
                unit_price=item.unit_price,
                discount_percent=item.discount_percent,
                tax_rate=item.tax_rate,
                sort_order=item.sort_order,
            )
        return invoice


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

class Contract(BaseDocument):

    status = models.CharField(
        _("status"), max_length=20,
        choices=ContractStatus.choices,
        default=ContractStatus.DRAFT,
        db_index=True,
    )
    body               = models.TextField(_("contract body"), blank=True)
    start_date         = models.DateField(_("start date"), null=True, blank=True)
    end_date           = models.DateField(_("end date"),   null=True, blank=True)
    auto_renew         = models.BooleanField(_("auto-renew"), default=False)
    renewal_notice_days = models.PositiveSmallIntegerField(_("renewal notice (days)"), default=30)
    signed_at          = models.DateTimeField(_("signed at"),    null=True, blank=True)
    signed_by_name     = models.CharField(_("signed by (name)"), max_length=200, blank=True)
    signature_ip       = models.GenericIPAddressField(_("signature IP"), null=True, blank=True)
    docusign_envelope_id = models.CharField(max_length=100, blank=True)
    ai_review          = models.JSONField(_("AI review"), default=dict, blank=True)
    sent_at            = models.DateTimeField(_("sent at"), null=True, blank=True)

    class Meta(BaseDocument.Meta):
        verbose_name        = _("contract")
        verbose_name_plural = _("contracts")
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["company", "end_date"]),
        ]

    @property
    def is_expiring_soon(self, days: int = 30) -> bool:
        if not self.end_date:
            return False
        delta = self.end_date - timezone.localdate()
        return 0 <= delta.days <= days


# ---------------------------------------------------------------------------
# LineItem
# ---------------------------------------------------------------------------

class LineItem(models.Model):
    """
    Normalised line item for Invoice and Quotation.

    Pricing model:
        gross_amount = unit_price × quantity × unit_of_measure
        line_total   = gross_amount × (1 − discount_percent / 100)

    unit_of_measure is a dimensionless multiplier.  For most items it is 1.
    For measured goods (fabric, timber, wire …) set it to the number of
    metres / kg / litres purchased and unit_price to the per-unit rate.

    Example: 3 rolls of fabric at KES 250/m, each roll 5 m long
        quantity        = 3
        unit_of_measure = 5
        unit_label      = "m"
        unit_price      = 250
        → gross_amount  = 250 × 3 × 5 = KES 3,750
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    invoice   = models.ForeignKey(Invoice,   on_delete=models.CASCADE, related_name="line_items", null=True, blank=True)
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="line_items", null=True, blank=True)

    item_type   = models.CharField(_("type"), max_length=20, choices=LineItemType.choices, default=LineItemType.SERVICE)
    description = models.CharField(_("description"), max_length=500)

    quantity    = models.DecimalField(_("quantity"),   max_digits=10, decimal_places=3, default=Decimal("1"))

    # NEW — measurement fields
    unit_of_measure = models.DecimalField(
        _("unit of measure"),
        max_digits=10, decimal_places=3,
        default=Decimal("1"),
        help_text=_("Multiplier per unit, e.g. metres per roll. Leave 1 for simple qty × price items."),
    )
    unit_label = models.CharField(
        _("unit label"),
        max_length=20, blank=True,
        help_text=_("Display label for the measure, e.g. 'm', 'kg', 'L'. Shown in invoice column header."),
    )
    # END NEW

    unit_price       = models.DecimalField(_("unit price"),  max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_percent = models.DecimalField(_("discount %"),  max_digits=5,  decimal_places=2, default=Decimal("0"))
    tax_rate         = models.DecimalField(_("tax rate %"),  max_digits=5,  decimal_places=2, default=Decimal("0"),
                                           help_text=_("Per-line override; 0 = use company VAT config."))
    sort_order       = models.PositiveSmallIntegerField(_("sort order"), default=0)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = _("line item")
        verbose_name_plural = _("line items")
        ordering            = ["sort_order", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(invoice__isnull=False, quotation__isnull=True)
                    | models.Q(invoice__isnull=True, quotation__isnull=False)
                ),
                name="lineitem_belongs_to_one_document",
            )
        ]

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def gross_amount(self) -> Decimal:
        """unit_price × quantity × unit_of_measure"""
        return (self.unit_price * self.quantity * self.unit_of_measure).quantize(Decimal("0.01"))

    @property
    def discount_value(self) -> Decimal:
        return (self.gross_amount * self.discount_percent / 100).quantize(Decimal("0.01"))

    @property
    def line_total(self) -> Decimal:
        return (self.gross_amount - self.discount_value).quantize(Decimal("0.01"))

    def __str__(self) -> str:
        measure = f" × {self.unit_of_measure}{self.unit_label}" if self.unit_label else ""
        return f"{self.description} — {self.quantity}{measure} @ {self.unit_price}"