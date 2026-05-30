"""
DocFlow AI — documents/tests/factories.py
==========================================
Factory Boy factories for all document models.

Usage in tests:
    from documents.tests.factories import InvoiceFactory, LineItemFactory

    invoice = InvoiceFactory(status="sent")
    item    = LineItemFactory(invoice=invoice, unit_price=Decimal("100"))
"""

from __future__ import annotations

import factory
import factory.fuzzy
from decimal import Decimal
from django.utils import timezone


# ---------------------------------------------------------------------------
# Helpers — these assume Company and User factories exist in their own apps.
# Adjust the paths to match your project structure.
# ---------------------------------------------------------------------------

class CompanyFactory(factory.django.DjangoModelFactory):
    """Minimal stub — replace with your real companies/tests/factories.py."""

    class Meta:
        model = "companies.Company"
        django_get_or_create = ["slug"]

    name  = factory.Sequence(lambda n: f"Company {n}")
    slug  = factory.Sequence(lambda n: f"company-{n}")
    email = factory.LazyAttribute(lambda o: f"info@{o.slug}.com")


class UserFactory(factory.django.DjangoModelFactory):
    """Minimal stub — replace with your real users/tests/factories.py."""

    class Meta:
        model  = "users.User"          # adjust to AUTH_USER_MODEL
        django_get_or_create = ["email"]

    email      = factory.Sequence(lambda n: f"user{n}@docflowai.com")
    first_name = factory.Faker("first_name")
    last_name  = factory.Faker("last_name")
    is_active  = True


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class InvoiceFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = "documents.Invoice"

    company    = factory.SubFactory(CompanyFactory)
    created_by = factory.SubFactory(UserFactory)

    client_name    = factory.Faker("company")
    client_email   = factory.Faker("company_email")
    client_address = factory.Faker("address")

    number     = factory.Sequence(lambda n: f"INV-{n:04d}")
    status     = "draft"
    issue_date = factory.LazyFunction(timezone.localdate)
    due_date   = factory.LazyFunction(lambda: timezone.localdate() + __import__("datetime").timedelta(days=30))
    currency   = "USD"
    subject    = factory.Faker("sentence", nb_words=5)
    notes      = factory.Faker("paragraph")

    subtotal        = Decimal("0.00")
    discount_amount = Decimal("0.00")
    tax_amount      = Decimal("0.00")
    total           = Decimal("0.00")
    amount_paid     = Decimal("0.00")


class SentInvoiceFactory(InvoiceFactory):
    status  = "sent"
    sent_at = factory.LazyFunction(timezone.now)


class PaidInvoiceFactory(InvoiceFactory):
    status      = "paid"
    sent_at     = factory.LazyFunction(timezone.now)
    paid_at     = factory.LazyFunction(timezone.now)
    amount_paid = factory.LazyAttribute(lambda o: o.total)


# ---------------------------------------------------------------------------
# Quotation
# ---------------------------------------------------------------------------

class QuotationFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = "documents.Quotation"

    company    = factory.SubFactory(CompanyFactory)
    created_by = factory.SubFactory(UserFactory)

    client_name  = factory.Faker("company")
    client_email = factory.Faker("company_email")

    number      = factory.Sequence(lambda n: f"QT-{n:04d}")
    status      = "draft"
    issue_date  = factory.LazyFunction(timezone.localdate)
    valid_until = factory.LazyFunction(lambda: timezone.localdate() + __import__("datetime").timedelta(days=14))
    currency    = "USD"
    subject     = factory.Faker("sentence", nb_words=5)

    subtotal        = Decimal("0.00")
    discount_amount = Decimal("0.00")
    tax_amount      = Decimal("0.00")
    total           = Decimal("0.00")
    amount_paid     = Decimal("0.00")


class AcceptedQuotationFactory(QuotationFactory):
    status      = "accepted"
    sent_at     = factory.LazyFunction(timezone.now)
    accepted_at = factory.LazyFunction(timezone.now)


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

class ContractFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = "documents.Contract"

    company    = factory.SubFactory(CompanyFactory)
    created_by = factory.SubFactory(UserFactory)

    client_name  = factory.Faker("company")
    client_email = factory.Faker("company_email")

    number     = factory.Sequence(lambda n: f"CNT-{n:04d}")
    status     = "draft"
    issue_date = factory.LazyFunction(timezone.localdate)
    start_date = factory.LazyFunction(timezone.localdate)
    end_date   = factory.LazyFunction(lambda: timezone.localdate() + __import__("datetime").timedelta(days=365))
    currency   = "USD"
    subject    = factory.Faker("sentence", nb_words=5)
    body       = factory.Faker("text", max_nb_chars=1000)

    subtotal        = Decimal("0.00")
    discount_amount = Decimal("0.00")
    tax_amount      = Decimal("0.00")
    total           = Decimal("0.00")
    amount_paid     = Decimal("0.00")


class SignedContractFactory(ContractFactory):
    status          = "signed"
    sent_at         = factory.LazyFunction(timezone.now)
    signed_at       = factory.LazyFunction(timezone.now)
    signed_by_name  = factory.Faker("name")
    signature_ip    = "127.0.0.1"


# ---------------------------------------------------------------------------
# LineItem
# ---------------------------------------------------------------------------

class InvoiceLineItemFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = "documents.LineItem"

    invoice     = factory.SubFactory(InvoiceFactory)
    quotation   = None

    item_type       = "service"
    description     = factory.Faker("bs")
    quantity        = Decimal("1.000")
    unit_of_measure = Decimal("1.000")
    unit_label      = ""
    unit_price      = factory.fuzzy.FuzzyDecimal(10.00, 5000.00, precision=2)
    discount_percent = Decimal("0.00")
    tax_rate        = Decimal("0.00")
    sort_order      = factory.Sequence(lambda n: n)


class QuotationLineItemFactory(InvoiceLineItemFactory):
    invoice   = None
    quotation = factory.SubFactory(QuotationFactory)


class DiscountLineItemFactory(InvoiceLineItemFactory):
    item_type  = "discount"
    unit_price = factory.fuzzy.FuzzyDecimal(5.00, 500.00, precision=2)


# ---------------------------------------------------------------------------
# PaymentRecord
# ---------------------------------------------------------------------------

class PaymentRecordFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = "documents.PaymentRecord"

    invoice        = factory.SubFactory(InvoiceFactory)
    amount         = factory.fuzzy.FuzzyDecimal(50.00, 2000.00, precision=2)
    currency       = "USD"
    payment_method = "bank_transfer"
    payment_date   = factory.LazyFunction(timezone.localdate)
    reference      = factory.Sequence(lambda n: f"TXN-{n:06d}")
    is_reversed    = False


# ---------------------------------------------------------------------------
# DocumentAttachment
# ---------------------------------------------------------------------------

class InvoiceAttachmentFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = "documents.DocumentAttachment"

    invoice         = factory.SubFactory(InvoiceFactory)
    original_name   = factory.Faker("file_name", extension="pdf")
    mime_type       = "application/pdf"
    file_size       = factory.fuzzy.FuzzyInteger(1024, 5_000_000)
    attachment_type = "supporting"
    uploaded_by     = factory.SubFactory(UserFactory)