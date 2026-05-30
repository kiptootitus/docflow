"""
DocFlow AI — documents/tests/conftest.py
==========================================
Shared pytest fixtures for all test modules.

No database required for the majority of fixtures — they return
lightweight MagicMock objects that mirror the shape of the real models.
Tests that genuinely need the ORM are decorated with
@pytest.mark.django_db and import from factories.py.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock

import pytest
from django.utils import timezone


# ===========================================================================
# COMPANY / USER STUBS
# ===========================================================================

@pytest.fixture
def mock_vat():
    vat = MagicMock()
    vat.vat_rate   = Decimal("16.00")
    vat.vat_label  = "VAT"
    vat.vat_number = "VAT123456"
    return vat


@pytest.fixture
def mock_branding():
    b = MagicMock()
    b.primary_color          = "#1A56DB"
    b.secondary_color        = "#6B7280"
    b.font_family            = "Inter"
    b.font_size_body         = 10
    b.stamp                  = None
    b.signature              = None
    b.invoice_footer_text    = "Thank you for your business."
    b.quotation_footer_text  = "This quotation is valid for 14 days."
    b.contract_footer_text   = "Confidential."
    return b


@pytest.fixture
def mock_company(mock_vat, mock_branding):
    c = MagicMock()
    c.pk   = c.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    c.name = "DocFlow Corp"
    c.slug = "docflow-corp"
    c.email         = "info@docflow.com"
    c.phone         = "+1-555-0000"
    c.full_address  = "123 Business Ave, Nairobi, KE"
    c.logo          = None
    c.vat_config    = mock_vat
    c.branding      = mock_branding
    c.is_active     = True
    c.get_next_invoice_number   = MagicMock(return_value="INV-0001")
    c.get_next_quotation_number = MagicMock(return_value="QT-0001")
    c.get_next_contract_number  = MagicMock(return_value="CNT-0001")
    owner = MagicMock()
    owner.email    = "owner@docflow.com"
    owner.full_name = "Jane Owner"
    c.owner = owner
    return c


@pytest.fixture
def mock_user():
    u = MagicMock()
    u.pk   = u.id = uuid.UUID("11111111-0000-0000-0000-000000000001")
    u.email      = "alex@docflow.com"
    u.full_name  = "Alex Dev"
    u.is_active  = True
    u.is_authenticated = True
    return u


@pytest.fixture
def mock_client_user():
    u = MagicMock()
    u.pk        = uuid.UUID("22222222-0000-0000-0000-000000000001")
    u.email     = "client@acme.com"
    u.full_name = "Client Contact"
    u.is_active = True
    return u


# ===========================================================================
# DOCUMENT STUBS
# ===========================================================================

@pytest.fixture
def mock_invoice(mock_company, mock_user):
    from documents.models import Invoice, InvoiceStatus

    inv = Invoice.__new__(Invoice)
    inv.pk          = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    inv.id          = inv.pk
    inv.company     = mock_company
    inv.company_id  = mock_company.pk
    inv.client      = None
    inv.client_salutation = ""
    inv.client_name  = "Acme Ltd"
    inv.client_email = "billing@acme.com"
    inv.client_phone = "+1-555-1111"
    inv.client_address    = "456 Client Road"
    inv.client_vat_number = ""
    inv.number       = "INV-0001"
    inv.status       = InvoiceStatus.DRAFT
    inv.issue_date   = timezone.localdate()
    inv.due_date     = timezone.localdate() + datetime.timedelta(days=30)
    inv.currency     = "USD"
    inv.subject      = "Web Development Services"
    inv.notes        = "Please pay within 30 days."
    inv.terms        = "Net 30"
    inv.subtotal          = Decimal("500.00")
    inv.discount_amount   = Decimal("0.00")
    inv.tax_amount        = Decimal("80.00")
    inv.total             = Decimal("580.00")
    inv.amount_paid       = Decimal("0.00")
    inv.stripe_payment_link_url  = ""
    inv.stripe_payment_intent_id = ""
    inv.portal_token = ""
    inv.pdf_file     = None
    inv.docx_file    = None
    inv.sent_at      = None
    inv.viewed_at    = None
    inv.paid_at      = None
    inv.is_active    = True
    inv.deleted_at   = None
    inv.created_by   = mock_user
    inv.created_at   = timezone.now()
    inv.updated_at   = timezone.now()

    # Line items manager stub
    mock_li_mgr = MagicMock()
    mock_li_mgr.all.return_value = []
    inv.line_items = mock_li_mgr

    # Payment records manager stub
    mock_pr_mgr = MagicMock()
    mock_pr_mgr.filter.return_value.aggregate.return_value = {"total": Decimal("0.00")}
    inv.payment_records = mock_pr_mgr

    return inv


@pytest.fixture
def mock_quotation(mock_company, mock_user):
    from documents.models import Quotation, QuotationStatus

    qt = Quotation.__new__(Quotation)
    qt.pk          = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
    qt.id          = qt.pk
    qt.company     = mock_company
    qt.company_id  = mock_company.pk
    qt.client      = None
    qt.client_salutation = ""
    qt.client_name   = "Beta Corp"
    qt.client_email  = "accounts@beta.com"
    qt.client_phone  = ""
    qt.client_address     = ""
    qt.client_vat_number  = ""
    qt.number        = "QT-0001"
    qt.status        = QuotationStatus.DRAFT
    qt.issue_date    = timezone.localdate()
    qt.due_date      = None
    qt.valid_until   = timezone.localdate() + datetime.timedelta(days=14)
    qt.currency      = "USD"
    qt.subject       = "Project Quotation"
    qt.notes         = ""
    qt.terms         = ""
    qt.subtotal          = Decimal("1000.00")
    qt.discount_amount   = Decimal("0.00")
    qt.tax_amount        = Decimal("160.00")
    qt.total             = Decimal("1160.00")
    qt.amount_paid       = Decimal("0.00")
    qt.sent_at           = None
    qt.accepted_at       = None
    qt.declined_at       = None
    qt.decline_reason    = ""
    qt.pdf_file          = None
    qt.docx_file         = None
    qt.is_active         = True
    qt.deleted_at        = None
    qt.created_by        = mock_user
    qt.created_at        = timezone.now()
    qt.updated_at        = timezone.now()

    mock_li_mgr = MagicMock()
    mock_li_mgr.all.return_value = []
    qt.line_items = mock_li_mgr

    return qt


@pytest.fixture
def mock_contract(mock_company, mock_user):
    from documents.models import Contract, ContractStatus

    cnt = Contract.__new__(Contract)
    cnt.pk           = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
    cnt.id           = cnt.pk
    cnt.company      = mock_company
    cnt.company_id   = mock_company.pk
    cnt.client       = None
    cnt.client_salutation = ""
    cnt.client_name   = "Gamma Inc"
    cnt.client_email  = "legal@gamma.com"
    cnt.client_phone  = ""
    cnt.client_address = ""
    cnt.number        = "CNT-0001"
    cnt.status        = ContractStatus.DRAFT
    cnt.issue_date    = timezone.localdate()
    cnt.due_date      = None
    cnt.start_date    = timezone.localdate()
    cnt.end_date      = timezone.localdate() + datetime.timedelta(days=365)
    cnt.auto_renew    = False
    cnt.renewal_notice_days = 30
    cnt.currency      = "USD"
    cnt.subject       = "Service Agreement"
    cnt.body          = "1. Scope\nThe company shall provide services.\n2. Payment\nNet 30."
    cnt.notes         = ""
    cnt.terms         = ""
    cnt.subtotal          = Decimal("5000.00")
    cnt.discount_amount   = Decimal("0.00")
    cnt.tax_amount        = Decimal("800.00")
    cnt.total             = Decimal("5800.00")
    cnt.amount_paid       = Decimal("0.00")
    cnt.sent_at           = None
    cnt.signed_at         = None
    cnt.signed_by_name    = ""
    cnt.signature_ip      = None
    cnt.docusign_envelope_id   = ""
    cnt.hellosign_signature_id = ""
    cnt.ai_review         = {}
    cnt.ai_reviewed_at    = None
    cnt.pdf_file          = None
    cnt.docx_file         = None
    cnt.is_active         = True
    cnt.deleted_at        = None
    cnt.created_by        = mock_user
    cnt.created_at        = timezone.now()
    cnt.updated_at        = timezone.now()
    return cnt


@pytest.fixture
def mock_line_item(mock_invoice):
    from documents.models import LineItem, LineItemType

    item = LineItem.__new__(LineItem)
    item.pk              = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
    item.invoice         = mock_invoice
    item.invoice_id      = mock_invoice.pk
    item.quotation       = None
    item.quotation_id    = None
    item.item_type       = LineItemType.SERVICE
    item.description     = "Web Design"
    item.quantity        = Decimal("1.000")
    item.unit_of_measure = Decimal("1.000")
    item.unit_label      = ""
    item.unit_price      = Decimal("500.00")
    item.discount_percent = Decimal("0.00")
    item.tax_rate        = Decimal("0.00")
    item.sort_order      = 0
    return item


@pytest.fixture
def mock_payment_record(mock_invoice, mock_user):
    from documents.models import PaymentRecord

    rec = PaymentRecord.__new__(PaymentRecord)
    rec.pk             = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")
    rec.invoice        = mock_invoice
    rec.invoice_id     = mock_invoice.pk
    rec.amount         = Decimal("290.00")
    rec.currency       = "USD"
    rec.payment_method = "bank_transfer"
    rec.payment_date   = timezone.localdate()
    rec.reference      = "TXN-001"
    rec.notes          = ""
    rec.is_reversed    = False
    rec.reversed_at    = None
    rec.reversed_by    = None
    rec.recorded_by    = mock_user
    rec.created_at     = timezone.now()
    return rec


@pytest.fixture
def mock_recurring(mock_company, mock_invoice, mock_user):
    from documents.models import RecurringInvoice, RecurringFrequency

    r = RecurringInvoice.__new__(RecurringInvoice)
    r.pk                = uuid.UUID("ffffffff-0000-0000-0000-000000000001")
    r.company           = mock_company
    r.company_id        = mock_company.pk
    r.template          = mock_invoice
    r.template_id       = mock_invoice.pk
    r.frequency         = RecurringFrequency.MONTHLY
    r.start_date        = timezone.localdate()
    r.end_date          = None
    r.max_occurrences   = None
    r.occurrences_sent  = 0
    r.next_invoice_date = timezone.localdate()
    r.auto_send         = True
    r.is_active         = True
    r.created_by        = mock_user
    r.created_at        = timezone.now()
    r.updated_at        = timezone.now()
    return r


# ===========================================================================
# MOCK REQUEST
# ===========================================================================

@pytest.fixture
def mock_request(mock_user):
    req = MagicMock()
    req.user = mock_user
    req.META = {"REMOTE_ADDR": "127.0.0.1"}
    req.data = {}
    req.query_params = {}
    return req


# ===========================================================================
# QUERYSET HELPERS
# ===========================================================================

def make_qs(*objects):
    """Return a minimal mock queryset containing the given objects."""
    qs = MagicMock()
    qs.__iter__ = MagicMock(return_value=iter(objects))
    qs.filter   = MagicMock(return_value=qs)
    qs.exclude  = MagicMock(return_value=qs)
    qs.update   = MagicMock(return_value=len(objects))
    qs.count    = MagicMock(return_value=len(objects))
    qs.first    = MagicMock(return_value=objects[0] if objects else None)
    qs.exists   = MagicMock(return_value=bool(objects))
    qs.__len__  = MagicMock(return_value=len(objects))
    return qs