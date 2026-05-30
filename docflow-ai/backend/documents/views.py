"""
DocFlow AI — documents/views.py
================================
Enterprise-grade ModelViewSets for all document types.

ViewSet map
───────────
  InvoiceViewSet          /api/invoices/
    • Standard CRUD (list, create, retrieve, partial_update, destroy)
    • send              POST   /<pk>/send/
    • void              POST   /<pk>/void/
    • mark_paid         POST   /<pk>/mark-paid/
    • mark_viewed       POST   /<pk>/mark-viewed/           ← portal use
    • download_pdf      GET    /<pk>/download-pdf/
    • download_docx     GET    /<pk>/download-docx/
    • preview           POST   /<pk>/preview/               ← live HTML preview
    • duplicate         POST   /<pk>/duplicate/
    • payments          GET    /<pk>/payments/
    • record_payment    POST   /<pk>/record-payment/
    • reverse_payment   POST   /<pk>/payments/<payment_pk>/reverse/
    • activity          GET    /<pk>/activity/
    • versions          GET    /<pk>/versions/
    • attachments       GET    /<pk>/attachments/
    • reorder_items     POST   /<pk>/reorder-items/
    • portal            GET    /portal/?token=<jwt>
    • stats             GET    /stats/?company=<uuid>

  QuotationViewSet        /api/quotations/
    • Standard CRUD
    • send              POST   /<pk>/send/
    • accept            POST   /<pk>/accept/
    • decline           POST   /<pk>/decline/
    • convert           POST   /<pk>/convert-to-invoice/
    • download_pdf      GET    /<pk>/download-pdf/
    • download_docx     GET    /<pk>/download-docx/
    • activity          GET    /<pk>/activity/
    • attachments       GET    /<pk>/attachments/

  ContractViewSet         /api/contracts/
    • Standard CRUD
    • send              POST   /<pk>/send/
    • sign              POST   /<pk>/sign/
    • download_pdf      GET    /<pk>/download-pdf/
    • download_docx     GET    /<pk>/download-docx/
    • submit_ai_review  POST   /<pk>/submit-ai-review/
    • ai_review         GET    /<pk>/ai-review/
    • activity          GET    /<pk>/activity/
    • attachments       GET    /<pk>/attachments/

  RecurringInvoiceViewSet /api/recurring-invoices/
    • Standard CRUD
    • pause             POST   /<pk>/pause/
    • resume            POST   /<pk>/resume/

  DocumentAttachmentViewSet /api/attachments/
    • list, create, retrieve, destroy

Permissions
───────────
  IsVerifiedUser         → must be authenticated + email verified
  IsCompanyMember        → must be an active member of the document's company
  IsOwner                → owner / super-admin only (for destructive ops)
  HasValidPortalToken    → for the public portal endpoint (no login required)

All queryset methods enforce row-level tenant isolation — a user can
NEVER access documents from a company they are not a member of.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from .filters import ContractFilter, InvoiceFilter, QuotationFilter
from .models import (
    ActivityAction,
    Contract,
    ContractStatus,
    DocumentActivity,
    DocumentAttachment,
    DocumentVersion,
    Invoice,
    InvoiceStatus,
    LineItem,
    PaymentRecord,
    Quotation,
    QuotationStatus,
    RecurringInvoice,
)
from .serializers import (
    ContractListSerializer,
    ContractSerializer,
    DocumentActivitySerializer,
    DocumentAttachmentSerializer,
    DocumentVersionSerializer,
    InvoiceDetailSerializer,
    InvoiceDuplicateSerializer,
    InvoiceListSerializer,
    InvoicePortalSerializer,
    InvoiceSerializer,
    LineItemBulkUpdateSerializer,
    PaymentRecordListSerializer,
    PaymentRecordSerializer,
    QuotationListSerializer,
    QuotationSerializer,
    RecurringInvoiceSerializer,
)
from .tasks import (
    generate_docx_task,
    generate_pdf_task,
    send_document_email_task,
)

logger = logging.getLogger(__name__)


# ===========================================================================
# PERMISSIONS
# Import from users app — adjust path if your users app differs
# ===========================================================================

try:
    from users.permissions import (
        HasValidPortalToken,
        IsCompanyMember,
        IsOwner,
        IsVerifiedUser,
    )
except ImportError:
    # Fallback stubs so the file is importable before users app exists
    from rest_framework.permissions import IsAuthenticated as IsVerifiedUser
    from rest_framework.permissions import IsAuthenticated as IsCompanyMember
    from rest_framework.permissions import IsAuthenticated as IsOwner
    from rest_framework.permissions import IsAuthenticated as HasValidPortalToken


# ===========================================================================
# HELPERS
# ===========================================================================

def _company_ids_for_user(user) -> list:
    """
    Return list of Company PKs the user is an active member of.
    Super-admins can see all companies.
    """
    try:
        from users.models import UserRole
        if getattr(user, "role", None) == UserRole.SUPER_ADMIN:
            from companies.models import Company
            return list(Company.objects.filter(is_active=True).values_list("id", flat=True))
    except ImportError:
        pass

    try:
        from companies.models import CompanyMembership
        return list(
            CompanyMembership.objects.filter(user=user, is_active=True)
            .values_list("company_id", flat=True)
        )
    except ImportError:
        # Development fallback — no membership model yet
        return []


def _get_client_ip(request: Request) -> str | None:
    """Extract real client IP, respecting X-Forwarded-For in production."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _document_activity_response(doc, limit: int = 50):
    """Return a serialized activity list for any document."""
    doc_type = doc.__class__.__name__.lower()
    qs = DocumentActivity.objects.filter(
        doc_type=doc_type, doc_id=doc.pk
    ).select_related("actor").order_by("-created_at")[:limit]
    return DocumentActivitySerializer(qs, many=True).data


def _queue_or_return_file(instance, file_field: str, task_fn, doc_type: str, format_label: str):
    """
    If the file already exists, return its URL.
    Otherwise queue generation and return 202.
    """
    file = getattr(instance, file_field)
    if file:
        return Response({"url": file.url, "generated": False})
    task_fn.delay(doc_type, str(instance.pk))
    return Response(
        {"detail": _(f"{format_label} generation queued. Retry in a few seconds."),
         "generated": True},
        status=status.HTTP_202_ACCEPTED,
    )


# ===========================================================================
# INVOICE VIEWSET
# ===========================================================================

class InvoiceViewSet(viewsets.ModelViewSet):
    """
    list         GET  /api/invoices/
    create       POST /api/invoices/
    retrieve     GET  /api/invoices/<pk>/
    partial_update PATCH /api/invoices/<pk>/
    destroy      DELETE /api/invoices/<pk>/     — soft delete
    """

    filterset_class   = InvoiceFilter
    search_fields     = ["number", "client_name", "client_email", "subject"]
    ordering_fields   = ["created_at", "due_date", "total", "status", "issue_date"]
    ordering          = ["-created_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    # ── Permission routing ────────────────────────────────────────────────

    def get_permissions(self):
        if self.action == "portal":
            return [HasValidPortalToken()]
        if self.action in ("partial_update", "update", "destroy", "void"):
            return [IsVerifiedUser(), IsOwner()]
        return [IsVerifiedUser(), IsCompanyMember()]

    # ── Serializer routing ────────────────────────────────────────────────

    def get_serializer_class(self):
        if self.action == "portal":
            return InvoicePortalSerializer
        if self.action == "list":
            return InvoiceListSerializer
        if self.action == "retrieve":
            return InvoiceDetailSerializer
        if self.action == "duplicate":
            return InvoiceDuplicateSerializer
        if self.action == "record_payment":
            return PaymentRecordSerializer
        if self.action == "payments":
            return PaymentRecordListSerializer
        if self.action == "activity":
            return DocumentActivitySerializer
        if self.action == "versions":
            return DocumentVersionSerializer
        if self.action in ("attachments",):
            return DocumentAttachmentSerializer
        if self.action == "reorder_items":
            return LineItemBulkUpdateSerializer
        return InvoiceSerializer

    # ── Queryset ──────────────────────────────────────────────────────────

    def get_queryset(self):
        company_ids = _company_ids_for_user(self.request.user)
        qs = (
            Invoice.objects
            .filter(company_id__in=company_ids)
            .select_related("company", "company__branding", "client", "created_by")
            .prefetch_related("line_items")
        )
        # Optionally scope to a single company via ?company=<uuid>
        company_filter = self.request.query_params.get("company")
        if company_filter:
            qs = qs.filter(company_id=company_filter)
        return qs

    # ── Standard overrides ────────────────────────────────────────────────

    def perform_destroy(self, instance: Invoice) -> None:
        instance.soft_delete(deleted_by=self.request.user)

    # ── Action: send ──────────────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def send(self, request: Request, pk=None) -> Response:
        """POST /api/invoices/<pk>/send/ — mark sent and queue email."""
        invoice = self.get_object()

        if invoice.status not in (InvoiceStatus.DRAFT, InvoiceStatus.VIEWED):
            return Response(
                {"detail": _("Only draft or viewed invoices can be sent.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not invoice.client_email:
            return Response(
                {"detail": _("Invoice has no client email address.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice.mark_sent(actor=request.user)
        send_document_email_task.delay("invoice", str(invoice.pk))

        # Ensure portal token exists for payment link
        invoice.ensure_portal_token()

        return Response(
            {"detail": _("Invoice queued for delivery."),
             "portal_token": invoice.portal_token},
        )

    # ── Action: void ──────────────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def void(self, request: Request, pk=None) -> Response:
        """POST /api/invoices/<pk>/void/"""
        invoice = self.get_object()
        reason  = request.data.get("reason", "")

        try:
            invoice.void(actor=request.user, reason=reason)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": _("Invoice voided.")})

    # ── Action: mark_paid ─────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request: Request, pk=None) -> Response:
        """
        POST /api/invoices/<pk>/mark-paid/
        Body: { amount: 500.00, payment_method: "bank_transfer", reference: "TXN-001" }
        """
        invoice = self.get_object()

        if invoice.status == InvoiceStatus.VOID:
            return Response(
                {"detail": _("A voided invoice cannot be marked as paid.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_amount = request.data.get("amount")
        try:
            amount = Decimal(str(raw_amount)) if raw_amount is not None else invoice.balance_due
        except Exception:
            return Response(
                {"detail": _("Invalid amount — must be a number.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if amount <= 0:
            return Response(
                {"detail": _("Payment amount must be greater than zero.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment_method = request.data.get("payment_method", "bank_transfer")
        reference      = request.data.get("reference", "")

        record = PaymentRecord.objects.create(
            invoice        = invoice,
            amount         = amount,
            payment_method = payment_method,
            reference      = reference,
            recorded_by    = request.user,
        )
        invoice.sync_amount_paid()
        invoice.mark_paid(actor=request.user)

        return Response(
            PaymentRecordSerializer(record, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    # ── Action: mark_viewed ───────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="mark-viewed",
            permission_classes=[HasValidPortalToken])
    def mark_viewed(self, request: Request, pk=None) -> Response:
        """POST /api/invoices/<pk>/mark-viewed/ — called from client portal."""
        invoice = self.get_object()
        invoice.mark_viewed()
        return Response({"detail": _("Invoice marked as viewed.")})

    # ── Action: download_pdf ──────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="download-pdf")
    def download_pdf(self, request: Request, pk=None) -> Response:
        """GET /api/invoices/<pk>/download-pdf/ — returns URL or queues generation."""
        invoice = self.get_object()
        return _queue_or_return_file(invoice, "pdf_file", generate_pdf_task, "invoice", "PDF")

    # ── Action: download_docx ─────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="download-docx")
    def download_docx(self, request: Request, pk=None) -> Response:
        """GET /api/invoices/<pk>/download-docx/"""
        invoice = self.get_object()
        return _queue_or_return_file(invoice, "docx_file", generate_docx_task, "invoice", "DOCX")

    # ── Action: preview (live HTML preview for editor) ────────────────────

    @action(detail=True, methods=["post"])
    def preview(self, request: Request, pk=None) -> Response:
        """
        POST /api/invoices/<pk>/preview/
        Returns a rendered HTML string for the live preview panel.
        """
        invoice = self.get_object()
        try:
            from .pdf_generator import render_html
            html = render_html("invoice", invoice)
            return Response({"html": html})
        except Exception as exc:
            logger.exception("Preview render failed for invoice %s: %s", pk, exc)
            return Response(
                {"detail": _("Preview generation failed. Check server logs.")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ── Action: duplicate ─────────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def duplicate(self, request: Request, pk=None) -> Response:
        """
        POST /api/invoices/<pk>/duplicate/
        Clones the invoice as a new DRAFT, copies line items.
        """
        original = self.get_object()
        ser      = InvoiceDuplicateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        company = original.company
        new_inv = Invoice(
            company           = company,
            client            = original.client,
            client_salutation = original.client_salutation,
            client_name       = original.client_name,
            client_email      = original.client_email,
            client_phone      = original.client_phone,
            client_address    = original.client_address,
            client_vat_number = original.client_vat_number,
            currency          = original.currency,
            subject           = f"Copy of {original.subject}" if original.subject else "",
            notes             = original.notes,
            terms             = original.terms,
            status            = InvoiceStatus.DRAFT,
            issue_date        = timezone.localdate(),
            due_date          = original.due_date,
            created_by        = request.user,
        )
        new_inv.number = company.get_next_invoice_number()
        new_inv.save()

        for item in original.line_items.all():
            LineItem.objects.create(
                invoice          = new_inv,
                item_type        = item.item_type,
                description      = item.description,
                quantity         = item.quantity,
                unit_of_measure  = item.unit_of_measure,
                unit_label       = item.unit_label,
                unit_price       = item.unit_price,
                discount_percent = item.discount_percent,
                tax_rate         = item.tax_rate,
                sort_order       = item.sort_order,
            )

        new_inv.compute_totals(save=True)
        new_inv.log_activity(
            ActivityAction.CREATED,
            actor=request.user,
            metadata={"duplicated_from": str(original.pk)},
        )

        return Response(
            InvoiceSerializer(new_inv, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    # ── Action: payments (list) ───────────────────────────────────────────

    @action(detail=True, methods=["get"])
    def payments(self, request: Request, pk=None) -> Response:
        """GET /api/invoices/<pk>/payments/"""
        invoice = self.get_object()
        qs = invoice.payment_records.select_related("recorded_by", "reversed_by").order_by("-payment_date")
        return Response(PaymentRecordSerializer(qs, many=True, context={"request": request}).data)

    # ── Action: record_payment ────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="record-payment")
    def record_payment(self, request: Request, pk=None) -> Response:
        """POST /api/invoices/<pk>/record-payment/"""
        invoice = self.get_object()

        if invoice.status in (InvoiceStatus.VOID, InvoiceStatus.CANCELLED):
            return Response(
                {"detail": _("Cannot record payment for a voided or cancelled invoice.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = PaymentRecordSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        record = ser.save(invoice=invoice)

        return Response(
            PaymentRecordSerializer(record, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    # ── Action: reverse a specific payment ───────────────────────────────

    @action(
        detail=True, methods=["post"],
        url_path=r"payments/(?P<payment_pk>[0-9a-f-]+)/reverse",
        permission_classes=[IsVerifiedUser, IsOwner],
    )
    def reverse_payment(self, request: Request, pk=None, payment_pk=None) -> Response:
        """POST /api/invoices/<pk>/payments/<payment_pk>/reverse/"""
        invoice = self.get_object()
        try:
            record = invoice.payment_records.get(pk=payment_pk)
        except PaymentRecord.DoesNotExist:
            return Response({"detail": _("Payment not found.")}, status=status.HTTP_404_NOT_FOUND)

        if record.is_reversed:
            return Response(
                {"detail": _("This payment has already been reversed.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        record.reverse(reversed_by=request.user)
        invoice.log_activity(
            ActivityAction.UPDATED,
            actor=request.user,
            note=f"Payment {record.pk} reversed",
        )
        return Response({"detail": _("Payment reversed.")})

    # ── Action: activity (audit log) ──────────────────────────────────────

    @action(detail=True, methods=["get"])
    def activity(self, request: Request, pk=None) -> Response:
        """GET /api/invoices/<pk>/activity/"""
        invoice = self.get_object()
        return Response(_document_activity_response(invoice))

    # ── Action: versions ──────────────────────────────────────────────────

    @action(detail=True, methods=["get"])
    def versions(self, request: Request, pk=None) -> Response:
        """GET /api/invoices/<pk>/versions/"""
        invoice = self.get_object()
        qs = DocumentVersion.objects.filter(
            doc_type="invoice", doc_id=invoice.pk
        ).order_by("-version")
        return Response(DocumentVersionSerializer(qs, many=True).data)

    # ── Action: attachments ───────────────────────────────────────────────

    @action(detail=True, methods=["get", "post"])
    def attachments(self, request: Request, pk=None) -> Response:
        """GET/POST /api/invoices/<pk>/attachments/"""
        invoice = self.get_object()

        if request.method == "GET":
            qs  = invoice.attachments.select_related("uploaded_by").order_by("-created_at")
            ser = DocumentAttachmentSerializer(qs, many=True, context={"request": request})
            return Response(ser.data)

        # POST — upload
        ser = DocumentAttachmentSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save(invoice=invoice)
        return Response(ser.data, status=status.HTTP_201_CREATED)

    # ── Action: reorder_items ─────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="reorder-items")
    def reorder_items(self, request: Request, pk=None) -> Response:
        """
        POST /api/invoices/<pk>/reorder-items/
        Body: {"items": [{"id": "uuid", "sort_order": 0}, …]}
        """
        invoice = self.get_object()
        ser = LineItemBulkUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        item_map = {str(li.pk): li for li in invoice.line_items.all()}
        for entry in ser.validated_data["items"]:
            li = item_map.get(str(entry["id"]))
            if li:
                li.sort_order = entry["sort_order"]
                li.save(update_fields=["sort_order"])

        return Response({"detail": _("Line items reordered.")})

    # ── Action: portal ────────────────────────────────────────────────────

    @action(
        detail=False, methods=["get"],
        permission_classes=[HasValidPortalToken],
    )
    def portal(self, request: Request) -> Response:
        """GET /api/invoices/portal/?token=<jwt> — public client portal."""
        payload    = getattr(request, "_portal_token_payload", {})
        invoice_id = payload.get("invoice_id")

        if not invoice_id:
            return Response(
                {"detail": _("Invalid or expired portal token.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            invoice = Invoice.all_objects.get(pk=invoice_id, is_active=True)
        except Invoice.DoesNotExist:
            return Response({"detail": _("Invoice not found.")}, status=status.HTTP_404_NOT_FOUND)

        # Track view
        invoice.mark_viewed()

        ser = InvoicePortalSerializer(invoice, context={"request": request})
        return Response(ser.data)

    # ── Action: stats (dashboard) ─────────────────────────────────────────

    @action(detail=False, methods=["get"])
    def stats(self, request: Request) -> Response:
        """
        GET /api/invoices/stats/?company=<uuid>
        Returns aggregated counts and totals for the dashboard.
        """
        company_ids   = _company_ids_for_user(request.user)
        company_filter = request.query_params.get("company")
        if company_filter:
            company_ids = [cid for cid in company_ids if str(cid) == company_filter]

        qs = Invoice.objects.filter(company_id__in=company_ids)

        agg = qs.aggregate(
            total_revenue   = Sum("amount_paid"),
            total_outstanding = Sum("balance_due", filter=Q(status__in=[
                "sent", "viewed", "partial", "overdue"
            ])),
            count_total    = Count("id"),
            count_draft    = Count("id", filter=Q(status="draft")),
            count_sent     = Count("id", filter=Q(status__in=["sent", "viewed"])),
            count_paid     = Count("id", filter=Q(status="paid")),
            count_overdue  = Count("id", filter=Q(status="overdue")),
            count_partial  = Count("id", filter=Q(status="partial")),
        )

        # Clean up None → 0
        for k, v in agg.items():
            if v is None:
                agg[k] = Decimal("0.00") if "total" in k else 0

        return Response(agg)


# ===========================================================================
# QUOTATION VIEWSET
# ===========================================================================

class QuotationViewSet(viewsets.ModelViewSet):

    filterset_class   = QuotationFilter
    search_fields     = ["number", "client_name", "client_email", "subject"]
    ordering_fields   = ["created_at", "valid_until", "total", "status"]
    ordering          = ["-created_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("partial_update", "update", "destroy"):
            return [IsVerifiedUser(), IsOwner()]
        return [IsVerifiedUser(), IsCompanyMember()]

    def get_serializer_class(self):
        if self.action == "list":
            return QuotationListSerializer
        if self.action == "activity":
            return DocumentActivitySerializer
        if self.action == "attachments":
            return DocumentAttachmentSerializer
        return QuotationSerializer

    def get_queryset(self):
        company_ids = _company_ids_for_user(self.request.user)
        return (
            Quotation.objects
            .filter(company_id__in=company_ids)
            .select_related("company", "client", "created_by")
            .prefetch_related("line_items")
        )

    def perform_destroy(self, instance: Quotation) -> None:
        instance.soft_delete(deleted_by=self.request.user)

    # ── Action: send ──────────────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def send(self, request: Request, pk=None) -> Response:
        quotation = self.get_object()

        if quotation.status != QuotationStatus.DRAFT:
            return Response(
                {"detail": _("Only draft quotations can be sent.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not quotation.client_email:
            return Response(
                {"detail": _("Quotation has no client email address.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        quotation.mark_sent(actor=request.user)
        send_document_email_task.delay("quotation", str(quotation.pk))
        return Response({"detail": _("Quotation queued for delivery.")})

    # ── Action: accept ────────────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def accept(self, request: Request, pk=None) -> Response:
        quotation = self.get_object()
        try:
            quotation.accept(actor=request.user)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": _("Quotation accepted.")})

    # ── Action: decline ───────────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def decline(self, request: Request, pk=None) -> Response:
        quotation = self.get_object()
        reason    = request.data.get("reason", "")
        quotation.decline(actor=request.user, reason=reason)
        return Response({"detail": _("Quotation declined.")})

    # ── Action: convert_to_invoice ────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="convert-to-invoice")
    def convert_to_invoice(self, request: Request, pk=None) -> Response:
        """POST /api/quotations/<pk>/convert-to-invoice/"""
        quotation = self.get_object()
        try:
            invoice = quotation.convert_to_invoice(actor=request.user)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            InvoiceSerializer(invoice, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    # ── Action: download_pdf ──────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="download-pdf")
    def download_pdf(self, request: Request, pk=None) -> Response:
        quotation = self.get_object()
        return _queue_or_return_file(quotation, "pdf_file", generate_pdf_task, "quotation", "PDF")

    # ── Action: download_docx ─────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="download-docx")
    def download_docx(self, request: Request, pk=None) -> Response:
        quotation = self.get_object()
        return _queue_or_return_file(quotation, "docx_file", generate_docx_task, "quotation", "DOCX")

    # ── Action: activity ──────────────────────────────────────────────────

    @action(detail=True, methods=["get"])
    def activity(self, request: Request, pk=None) -> Response:
        return Response(_document_activity_response(self.get_object()))

    # ── Action: attachments ───────────────────────────────────────────────

    @action(detail=True, methods=["get", "post"])
    def attachments(self, request: Request, pk=None) -> Response:
        quotation = self.get_object()
        if request.method == "GET":
            qs  = quotation.attachments.select_related("uploaded_by").order_by("-created_at")
            ser = DocumentAttachmentSerializer(qs, many=True, context={"request": request})
            return Response(ser.data)
        ser = DocumentAttachmentSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save(quotation=quotation)
        return Response(ser.data, status=status.HTTP_201_CREATED)


# ===========================================================================
# CONTRACT VIEWSET
# ===========================================================================

class ContractViewSet(viewsets.ModelViewSet):

    filterset_class   = ContractFilter
    search_fields     = ["number", "client_name", "client_email", "subject"]
    ordering_fields   = ["created_at", "end_date", "status", "signed_at"]
    ordering          = ["-created_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("partial_update", "update", "destroy"):
            return [IsVerifiedUser(), IsOwner()]
        return [IsVerifiedUser(), IsCompanyMember()]

    def get_serializer_class(self):
        if self.action == "list":
            return ContractListSerializer
        if self.action == "activity":
            return DocumentActivitySerializer
        if self.action == "attachments":
            return DocumentAttachmentSerializer
        return ContractSerializer

    def get_queryset(self):
        company_ids = _company_ids_for_user(self.request.user)
        return (
            Contract.objects
            .filter(company_id__in=company_ids)
            .select_related("company", "client", "created_by")
        )

    def perform_destroy(self, instance: Contract) -> None:
        instance.soft_delete(deleted_by=self.request.user)

    # ── Action: send ──────────────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def send(self, request: Request, pk=None) -> Response:
        contract = self.get_object()

        if contract.status != ContractStatus.DRAFT:
            return Response(
                {"detail": _("Only draft contracts can be sent.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not contract.client_email:
            return Response(
                {"detail": _("Contract has no client email address.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        contract.mark_sent(actor=request.user)
        send_document_email_task.delay("contract", str(contract.pk))
        return Response({"detail": _("Contract queued for delivery.")})

    # ── Action: sign ──────────────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def sign(self, request: Request, pk=None) -> Response:
        """
        POST /api/contracts/<pk>/sign/
        Body: { name: "John Doe" }
        """
        contract    = self.get_object()
        signer_name = request.data.get("name", "").strip()

        if not signer_name:
            return Response(
                {"detail": _("Signer name is required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            contract.mark_signed(
                signer_name = signer_name,
                ip_address  = _get_client_ip(request),
                actor       = request.user,
            )
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Trigger a notification to the company owner
        try:
            from notifications.tasks import notify_contract_signed
            notify_contract_signed.delay(str(contract.pk))
        except (ImportError, Exception) as exc:
            logger.warning("Could not send contract-signed notification: %s", exc)

        return Response(
            {"detail": _("Contract signed."),
             "signed_at": contract.signed_at,
             "signed_by": contract.signed_by_name},
        )

    # ── Action: download_pdf ──────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="download-pdf")
    def download_pdf(self, request: Request, pk=None) -> Response:
        contract = self.get_object()
        return _queue_or_return_file(contract, "pdf_file", generate_pdf_task, "contract", "PDF")

    # ── Action: download_docx ─────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="download-docx")
    def download_docx(self, request: Request, pk=None) -> Response:
        contract = self.get_object()
        return _queue_or_return_file(contract, "docx_file", generate_docx_task, "contract", "DOCX")

    # ── Action: submit_ai_review ──────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="submit-ai-review")
    def submit_ai_review(self, request: Request, pk=None) -> Response:
        """
        POST /api/contracts/<pk>/submit-ai-review/
        Queues the contract for AI analysis via the ai/ app.
        """
        contract = self.get_object()
        try:
            from ai.tasks import run_contract_ai_review
            run_contract_ai_review.delay(str(contract.pk))
            return Response(
                {"detail": _("Contract submitted for AI review. Results will appear shortly.")},
                status=status.HTTP_202_ACCEPTED,
            )
        except ImportError:
            return Response(
                {"detail": _("AI review feature is not yet enabled.")},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.exception("AI review submission failed for contract %s: %s", pk, exc)
            return Response(
                {"detail": _("Failed to submit for AI review.")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ── Action: ai_review (read result) ──────────────────────────────────

    @action(detail=True, methods=["get"], url_path="ai-review")
    def ai_review(self, request: Request, pk=None) -> Response:
        """GET /api/contracts/<pk>/ai-review/ — return stored AI analysis."""
        contract = self.get_object()
        return Response(
            {
                "ai_review":      contract.ai_review,
                "ai_reviewed_at": contract.ai_reviewed_at,
                "has_review":     bool(contract.ai_review),
            }
        )

    # ── Action: activity ──────────────────────────────────────────────────

    @action(detail=True, methods=["get"])
    def activity(self, request: Request, pk=None) -> Response:
        return Response(_document_activity_response(self.get_object()))

    # ── Action: attachments ───────────────────────────────────────────────

    @action(detail=True, methods=["get", "post"])
    def attachments(self, request: Request, pk=None) -> Response:
        contract = self.get_object()
        if request.method == "GET":
            qs  = contract.attachments.select_related("uploaded_by").order_by("-created_at")
            return Response(
                DocumentAttachmentSerializer(qs, many=True, context={"request": request}).data
            )
        ser = DocumentAttachmentSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save(contract=contract)
        return Response(ser.data, status=status.HTTP_201_CREATED)


# ===========================================================================
# RECURRING INVOICE VIEWSET
# ===========================================================================

class RecurringInvoiceViewSet(viewsets.ModelViewSet):
    """
    CRUD for recurring invoice schedules.
    Extra actions: pause, resume.
    """

    serializer_class  = RecurringInvoiceSerializer
    ordering_fields   = ["next_invoice_date", "created_at"]
    ordering          = ["next_invoice_date"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("partial_update", "update", "destroy", "pause", "resume"):
            return [IsVerifiedUser(), IsOwner()]
        return [IsVerifiedUser(), IsCompanyMember()]

    def get_queryset(self):
        company_ids = _company_ids_for_user(self.request.user)
        return (
            RecurringInvoice.objects.filter(company_id__in=company_ids)
            .select_related("company", "template", "created_by")
        )

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=["post"])
    def pause(self, request: Request, pk=None) -> Response:
        """POST /api/recurring-invoices/<pk>/pause/"""
        recurring = self.get_object()
        if not recurring.is_active:
            return Response(
                {"detail": _("Schedule is already paused.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        recurring.is_active = False
        recurring.save(update_fields=["is_active", "updated_at"])
        return Response({"detail": _("Recurring schedule paused.")})

    @action(detail=True, methods=["post"])
    def resume(self, request: Request, pk=None) -> Response:
        """POST /api/recurring-invoices/<pk>/resume/"""
        recurring = self.get_object()
        if recurring.is_active:
            return Response(
                {"detail": _("Schedule is already active.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        recurring.is_active = True
        recurring.save(update_fields=["is_active", "updated_at"])
        return Response({"detail": _("Recurring schedule resumed.")})


# ===========================================================================
# DOCUMENT ATTACHMENT VIEWSET
# (standalone — also accessed via nested invoice/quotation/contract actions)
# ===========================================================================

class DocumentAttachmentViewSet(viewsets.GenericViewSet,
                                 viewsets.mixins.ListModelMixin,
                                 viewsets.mixins.CreateModelMixin,
                                 viewsets.mixins.RetrieveModelMixin,
                                 viewsets.mixins.DestroyModelMixin):
    """
    list     GET  /api/attachments/?invoice=<uuid>|quotation=<uuid>|contract=<uuid>
    create   POST /api/attachments/
    retrieve GET  /api/attachments/<pk>/
    destroy  DELETE /api/attachments/<pk>/
    """

    serializer_class  = DocumentAttachmentSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_permissions(self):
        if self.action == "destroy":
            return [IsVerifiedUser(), IsOwner()]
        return [IsVerifiedUser(), IsCompanyMember()]

    def get_queryset(self):
        company_ids = _company_ids_for_user(self.request.user)

        # Build a union filter across all three FK types
        qs = DocumentAttachment.objects.select_related("uploaded_by")
        invoice_ids   = Invoice.objects.filter(company_id__in=company_ids).values_list("id", flat=True)
        quotation_ids = Quotation.objects.filter(company_id__in=company_ids).values_list("id", flat=True)
        contract_ids  = Contract.objects.filter(company_id__in=company_ids).values_list("id", flat=True)

        qs = qs.filter(
            Q(invoice_id__in=invoice_ids)
            | Q(quotation_id__in=quotation_ids)
            | Q(contract_id__in=contract_ids)
        )

        # Optional filters
        params = self.request.query_params
        if params.get("invoice"):
            qs = qs.filter(invoice_id=params["invoice"])
        if params.get("quotation"):
            qs = qs.filter(quotation_id=params["quotation"])
        if params.get("contract"):
            qs = qs.filter(contract_id=params["contract"])

        return qs.order_by("-created_at")