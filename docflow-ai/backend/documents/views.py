
# Create your views here.
"""
DocFlow AI — documents/views.py

ModelViewSets for Invoice, Quotation, and Contract.

Permissions follow users/permissions.py:
  • IsCompanyMember — can read + create
  • IsOwner         — can update + delete
  • IsClientReadOnly — read own documents via portal
  • HasValidPortalToken — public portal endpoint

Extra actions:
  Invoice:   send, void, mark_paid, download_pdf, download_docx
  Quotation: send, accept, decline, convert_to_invoice, download_pdf
  Contract:  send, sign, download_pdf, ai_review
"""

from __future__ import annotations

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from users.permissions import (
    HasValidPortalToken,
    IsClientReadOnly,
    IsCompanyMember,
    IsOwner,
    IsVerifiedUser,
)

from .filters import ContractFilter, InvoiceFilter, QuotationFilter
from .models import Contract, Invoice, Quotation
from .serializers import (
    ContractListSerializer,
    ContractSerializer,
    InvoiceListSerializer,
    InvoicePortalSerializer,
    InvoiceSerializer,
    QuotationListSerializer,
    QuotationSerializer,
)
from .tasks import generate_docx_task, generate_pdf_task, send_document_email_task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _company_ids_for_user(user) -> list:
    """Return list of company PKs the user is an active member of."""
    from companies.models import CompanyMembership
    from users.models import UserRole
    if user.role == UserRole.SUPER_ADMIN:
        from companies.models import Company
        return list(Company.objects.filter(is_active=True).values_list("id", flat=True))
    return list(
        CompanyMembership.objects.filter(user=user, is_active=True)
        .values_list("company_id", flat=True)
    )


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class InvoiceViewSet(viewsets.ModelViewSet):
    """
    list    GET  /api/invoices/
    create  POST /api/invoices/
    retrieve GET /api/invoices/<pk>/
    update  PATCH /api/invoices/<pk>/
    destroy DELETE /api/invoices/<pk>/

    extra:
      POST /api/invoices/<pk>/send/
      POST /api/invoices/<pk>/void/
      POST /api/invoices/<pk>/mark_paid/
      GET  /api/invoices/<pk>/download_pdf/
      GET  /api/invoices/<pk>/download_docx/
      GET  /api/invoices/portal/  — HasValidPortalToken
    """

    filterset_class  = InvoiceFilter
    search_fields    = ["number", "client_name", "client_email", "subject"]
    ordering_fields  = ["created_at", "due_date", "total", "status"]
    ordering         = ["-created_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action == "portal":
            return [HasValidPortalToken()]
        if self.action in ("update", "partial_update", "destroy", "void"):
            return [IsVerifiedUser(), IsOwner()]
        if self.action in ("send", "mark_paid"):
            return [IsVerifiedUser(), IsCompanyMember()]
        return [IsVerifiedUser(), IsCompanyMember()]

    def get_serializer_class(self):
        if self.action == "portal":
            return InvoicePortalSerializer
        if self.action == "list":
            return InvoiceListSerializer
        return InvoiceSerializer

    def get_queryset(self):
        user = self.request.user
        company_ids = _company_ids_for_user(user)
        return (
            Invoice.objects
            .filter(company_id__in=company_ids, is_active=True)
            .select_related("company", "company__branding", "client", "created_by")
            .prefetch_related("line_items")
        )

    def perform_destroy(self, instance: Invoice) -> None:
        instance.soft_delete()

    # ------------------------------------------------------------------
    # Extra actions
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"])
    def send(self, request: Request, pk=None) -> Response:
        """POST /api/invoices/<pk>/send/ — queues email + marks sent."""
        invoice = self.get_object()
        if invoice.status not in ("draft", "viewed"):
            return Response(
                {"detail": _("Only draft invoices can be sent.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice.mark_sent()
        send_document_email_task.delay("invoice", str(invoice.pk))
        return Response({"detail": _("Invoice queued for delivery.")})

    @action(detail=True, methods=["post"])
    def void(self, request: Request, pk=None) -> Response:
        """POST /api/invoices/<pk>/void/"""
        invoice = self.get_object()
        if invoice.status == "paid":
            return Response(
                {"detail": _("A paid invoice cannot be voided.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice.status = "void"
        invoice.save(update_fields=["status", "updated_at"])
        return Response({"detail": _("Invoice voided.")})

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request: Request, pk=None) -> Response:
        """POST /api/invoices/<pk>/mark-paid/"""
        invoice = self.get_object()
        amount = request.data.get("amount")
        try:
            amount = float(amount) if amount is not None else None
        except (ValueError, TypeError):
            return Response(
                {"detail": _("Invalid amount.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from decimal import Decimal
        invoice.mark_paid(Decimal(str(amount)) if amount is not None else None)
        return Response({"detail": _("Invoice marked as paid.")})

    @action(detail=True, methods=["get"], url_path="download-pdf")
    def download_pdf(self, request: Request, pk=None) -> Response:
        """GET /api/invoices/<pk>/download-pdf/ — regenerate if needed, return URL."""
        invoice = self.get_object()
        if not invoice.pdf_file:
            generate_pdf_task.delay("invoice", str(invoice.pk))
            return Response(
                {"detail": _("PDF generation queued. Try again in a moment.")},
                status=status.HTTP_202_ACCEPTED,
            )
        return Response({"url": invoice.pdf_file.url})

    @action(detail=True, methods=["get"], url_path="download-docx")
    def download_docx(self, request: Request, pk=None) -> Response:
        invoice = self.get_object()
        if not invoice.docx_file:
            generate_docx_task.delay("invoice", str(invoice.pk))
            return Response(
                {"detail": _("DOCX generation queued. Try again in a moment.")},
                status=status.HTTP_202_ACCEPTED,
            )
        return Response({"url": invoice.docx_file.url})

    @action(detail=False, methods=["get"],
            permission_classes=[HasValidPortalToken])
    def portal(self, request: Request) -> Response:
        """GET /api/invoices/portal/?token=<jwt>"""
        payload = getattr(request, "_portal_token_payload", {})
        invoice_id = payload.get("invoice_id")
        if not invoice_id:
            return Response(
                {"detail": _("Invalid portal token.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice = get_object_or_404(Invoice, pk=invoice_id, is_active=True)
        return Response(InvoicePortalSerializer(invoice, context={"request": request}).data)


# ---------------------------------------------------------------------------
# Quotation
# ---------------------------------------------------------------------------

class QuotationViewSet(viewsets.ModelViewSet):
    filterset_class   = QuotationFilter
    search_fields     = ["number", "client_name", "client_email", "subject"]
    ordering_fields   = ["created_at", "valid_until", "total", "status"]
    ordering          = ["-created_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy"):
            return [IsVerifiedUser(), IsOwner()]
        return [IsVerifiedUser(), IsCompanyMember()]

    def get_serializer_class(self):
        return QuotationListSerializer if self.action == "list" else QuotationSerializer

    def get_queryset(self):
        company_ids = _company_ids_for_user(self.request.user)
        return (
            Quotation.objects
            .filter(company_id__in=company_ids, is_active=True)
            .select_related("company", "client", "created_by")
            .prefetch_related("line_items")
        )

    def perform_destroy(self, instance: Quotation) -> None:
        instance.soft_delete()

    @action(detail=True, methods=["post"])
    def send(self, request: Request, pk=None) -> Response:
        quotation = self.get_object()
        if quotation.status != "draft":
            return Response(
                {"detail": _("Only draft quotations can be sent.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from django.utils import timezone
        quotation.status  = "sent"
        quotation.sent_at = timezone.now()
        quotation.save(update_fields=["status", "sent_at", "updated_at"])
        send_document_email_task.delay("quotation", str(quotation.pk))
        return Response({"detail": _("Quotation queued for delivery.")})

    @action(detail=True, methods=["post"])
    def accept(self, request: Request, pk=None) -> Response:
        quotation = self.get_object()
        if quotation.status not in ("sent", "viewed"):
            return Response(
                {"detail": _("Only sent or viewed quotations can be accepted.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from django.utils import timezone
        quotation.status      = "accepted"
        quotation.accepted_at = timezone.now()
        quotation.save(update_fields=["status", "accepted_at", "updated_at"])
        return Response({"detail": _("Quotation accepted.")})

    @action(detail=True, methods=["post"])
    def decline(self, request: Request, pk=None) -> Response:
        quotation = self.get_object()
        quotation.status = "declined"
        quotation.save(update_fields=["status", "updated_at"])
        return Response({"detail": _("Quotation declined.")})

    @action(detail=True, methods=["post"], url_path="convert-to-invoice")
    def convert_to_invoice(self, request: Request, pk=None) -> Response:
        """POST /api/quotations/<pk>/convert-to-invoice/"""
        quotation = self.get_object()
        if quotation.status != "accepted":
            return Response(
                {"detail": _("Only accepted quotations can be converted to invoices.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice = quotation.convert_to_invoice()
        return Response(
            InvoiceSerializer(invoice, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="download-pdf")
    def download_pdf(self, request: Request, pk=None) -> Response:
        quotation = self.get_object()
        if not quotation.pdf_file:
            generate_pdf_task.delay("quotation", str(quotation.pk))
            return Response(
                {"detail": _("PDF generation queued.")},
                status=status.HTTP_202_ACCEPTED,
            )
        return Response({"url": quotation.pdf_file.url})


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

class ContractViewSet(viewsets.ModelViewSet):
    filterset_class   = ContractFilter
    search_fields     = ["number", "client_name", "client_email", "subject"]
    ordering_fields   = ["created_at", "end_date", "status"]
    ordering          = ["-created_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy"):
            return [IsVerifiedUser(), IsOwner()]
        return [IsVerifiedUser(), IsCompanyMember()]

    def get_serializer_class(self):
        return ContractListSerializer if self.action == "list" else ContractSerializer

    def get_queryset(self):
        company_ids = _company_ids_for_user(self.request.user)
        return (
            Contract.objects
            .filter(company_id__in=company_ids, is_active=True)
            .select_related("company", "client", "created_by")
        )

    def perform_destroy(self, instance: Contract) -> None:
        instance.soft_delete()

    @action(detail=True, methods=["post"])
    def send(self, request: Request, pk=None) -> Response:
        contract = self.get_object()
        if contract.status != "draft":
            return Response(
                {"detail": _("Only draft contracts can be sent.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from django.utils import timezone
        contract.status  = "sent"
        contract.sent_at = timezone.now()
        contract.save(update_fields=["status", "sent_at", "updated_at"])
        send_document_email_task.delay("contract", str(contract.pk))
        return Response({"detail": _("Contract queued for delivery.")})

    @action(detail=True, methods=["post"])
    def sign(self, request: Request, pk=None) -> Response:
        """POST /api/contracts/<pk>/sign/  — lightweight built-in signature."""
        from users.permissions import get_client_ip
        contract = self.get_object()
        signer_name = request.data.get("name", "").strip()
        if not signer_name:
            return Response(
                {"detail": _("Signer name is required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from django.utils import timezone
        contract.status        = "signed"
        contract.signed_at     = timezone.now()
        contract.signed_by_name = signer_name
        contract.signature_ip  = get_client_ip(request)
        contract.save(update_fields=[
            "status", "signed_at", "signed_by_name", "signature_ip", "updated_at"
        ])
        return Response({"detail": _("Contract signed.")})

    @action(detail=True, methods=["get"], url_path="download-pdf")
    def download_pdf(self, request: Request, pk=None) -> Response:
        contract = self.get_object()
        if not contract.pdf_file:
            generate_pdf_task.delay("contract", str(contract.pk))
            return Response(
                {"detail": _("PDF generation queued.")},
                status=status.HTTP_202_ACCEPTED,
            )
        return Response({"url": contract.pdf_file.url})

    @action(detail=True, methods=["get"], url_path="ai-review")
    def ai_review_result(self, request: Request, pk=None) -> Response:
        """GET /api/contracts/<pk>/ai-review/  — return stored AI analysis."""
        contract = self.get_object()
        return Response({"ai_review": contract.ai_review})