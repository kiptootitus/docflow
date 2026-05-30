"""
DocFlow AI — documents/urls.py
================================
URL routing for all documents viewsets.

Mounted at /api/ by the root urls.py:

    path("api/", include("documents.urls")),

Generated URL map (DRF DefaultRouter + extras)
───────────────────────────────────────────────

  /api/invoices/                      GET list  | POST create
  /api/invoices/<pk>/                 GET       | PATCH | DELETE
  /api/invoices/<pk>/send/            POST
  /api/invoices/<pk>/void/            POST
  /api/invoices/<pk>/mark-paid/       POST
  /api/invoices/<pk>/mark-viewed/     POST  (portal / HasValidPortalToken)
  /api/invoices/<pk>/download-pdf/    GET
  /api/invoices/<pk>/download-docx/   GET
  /api/invoices/<pk>/preview/         POST  (live HTML preview)
  /api/invoices/<pk>/duplicate/       POST
  /api/invoices/<pk>/payments/        GET
  /api/invoices/<pk>/record-payment/  POST
  /api/invoices/<pk>/payments/<id>/reverse/  POST
  /api/invoices/<pk>/activity/        GET
  /api/invoices/<pk>/versions/        GET
  /api/invoices/<pk>/attachments/     GET | POST
  /api/invoices/<pk>/reorder-items/   POST
  /api/invoices/portal/               GET  (HasValidPortalToken)
  /api/invoices/stats/                GET  (dashboard aggregates)

  /api/quotations/                    GET | POST
  /api/quotations/<pk>/               GET | PATCH | DELETE
  /api/quotations/<pk>/send/          POST
  /api/quotations/<pk>/accept/        POST
  /api/quotations/<pk>/decline/       POST
  /api/quotations/<pk>/convert-to-invoice/  POST
  /api/quotations/<pk>/download-pdf/  GET
  /api/quotations/<pk>/download-docx/ GET
  /api/quotations/<pk>/activity/      GET
  /api/quotations/<pk>/attachments/   GET | POST

  /api/contracts/                     GET | POST
  /api/contracts/<pk>/                GET | PATCH | DELETE
  /api/contracts/<pk>/send/           POST
  /api/contracts/<pk>/sign/           POST
  /api/contracts/<pk>/download-pdf/   GET
  /api/contracts/<pk>/download-docx/  GET
  /api/contracts/<pk>/submit-ai-review/  POST
  /api/contracts/<pk>/ai-review/      GET
  /api/contracts/<pk>/activity/       GET
  /api/contracts/<pk>/attachments/    GET | POST

  /api/recurring-invoices/            GET | POST
  /api/recurring-invoices/<pk>/       GET | PATCH | DELETE
  /api/recurring-invoices/<pk>/pause/ POST
  /api/recurring-invoices/<pk>/resume/POST

  /api/attachments/                   GET | POST
  /api/attachments/<pk>/              GET | DELETE
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ContractViewSet,
    DocumentAttachmentViewSet,
    InvoiceViewSet,
    QuotationViewSet,
    RecurringInvoiceViewSet,
)

# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------

router = DefaultRouter(trailing_slash=True)

router.register(
    r"invoices",
    InvoiceViewSet,
    basename="invoice",
)
router.register(
    r"quotations",
    QuotationViewSet,
    basename="quotation",
)
router.register(
    r"contracts",
    ContractViewSet,
    basename="contract",
)
router.register(
    r"recurring-invoices",
    RecurringInvoiceViewSet,
    basename="recurring-invoice",
)
router.register(
    r"attachments",
    DocumentAttachmentViewSet,
    basename="attachment",
)

# ---------------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------------

urlpatterns = [
    path("", include(router.urls)),
]