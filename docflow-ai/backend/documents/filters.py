"""
DocFlow AI — documents/filters.py
===================================
django-filter FilterSets for all document types.

All filters are scoped to the requesting user's company via the
view's get_queryset() — no user-scope logic lives here.

FilterSet index
───────────────
  InvoiceFilter           status, date range, amount range, overdue, search
  QuotationFilter         status, date range, amount range, expired, search
  ContractFilter          status, date range, expiring_soon, auto_renew, search
  PaymentRecordFilter     invoice, method, date range, reversed
  DocumentActivityFilter  doc_type, action, actor, date range
  RecurringInvoiceFilter  frequency, is_active, due_today
"""

from __future__ import annotations

import django_filters
from django.db.models import Q
from django.utils import timezone

from .models import (
    Contract,
    DocumentActivity,
    Invoice,
    PaymentRecord,
    Quotation,
    RecurringInvoice,
)


# ---------------------------------------------------------------------------
# INVOICE
# ---------------------------------------------------------------------------

class InvoiceFilter(django_filters.FilterSet):
    """
    Supported query params:
      status               exact choice
      status__in           comma-separated e.g. ?status__in=sent,partial
      client_email         case-insensitive exact
      currency             case-insensitive exact
      issue_date__gte      YYYY-MM-DD
      issue_date__lte      YYYY-MM-DD
      due_date__gte        YYYY-MM-DD
      due_date__lte        YYYY-MM-DD
      created_at__gte      datetime
      created_at__lte      datetime
      total__gte           decimal
      total__lte           decimal
      amount_paid__gte     decimal
      amount_paid__lte     decimal
      overdue              true/false — past due_date & not paid/void
      has_pdf              true/false — pdf_file is set
      search               number, client_name, client_email, subject
    """

    status = django_filters.ChoiceFilter(
        choices=Invoice._meta.get_field("status").choices,
    )
    status__in = django_filters.BaseInFilter(
        field_name="status",
        lookup_expr="in",
    )
    client_email = django_filters.CharFilter(
        field_name="client_email",
        lookup_expr="iexact",
    )
    currency = django_filters.CharFilter(lookup_expr="iexact")

    issue_date__gte = django_filters.DateFilter(field_name="issue_date", lookup_expr="gte")
    issue_date__lte = django_filters.DateFilter(field_name="issue_date", lookup_expr="lte")
    due_date__gte   = django_filters.DateFilter(field_name="due_date",   lookup_expr="gte")
    due_date__lte   = django_filters.DateFilter(field_name="due_date",   lookup_expr="lte")

    created_at__gte = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at__lte = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    total__gte       = django_filters.NumberFilter(field_name="total",       lookup_expr="gte")
    total__lte       = django_filters.NumberFilter(field_name="total",       lookup_expr="lte")
    amount_paid__gte = django_filters.NumberFilter(field_name="amount_paid", lookup_expr="gte")
    amount_paid__lte = django_filters.NumberFilter(field_name="amount_paid", lookup_expr="lte")

    overdue  = django_filters.BooleanFilter(method="filter_overdue")
    has_pdf  = django_filters.BooleanFilter(method="filter_has_pdf")
    search   = django_filters.CharFilter(method="filter_search")

    class Meta:
        model  = Invoice
        fields = []

    def filter_overdue(self, queryset, name, value):
        today = timezone.localdate()
        if value:
            return queryset.filter(
                due_date__lt=today,
                status__in=["sent", "viewed", "partial"],
            )
        return queryset.exclude(
            due_date__lt=today,
            status__in=["sent", "viewed", "partial"],
        )

    def filter_has_pdf(self, queryset, name, value):
        if value:
            return queryset.exclude(pdf_file="").exclude(pdf_file__isnull=True)
        return queryset.filter(Q(pdf_file="") | Q(pdf_file__isnull=True))

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(number__icontains=value)
            | Q(client_name__icontains=value)
            | Q(client_email__icontains=value)
            | Q(subject__icontains=value)
        )


# ---------------------------------------------------------------------------
# QUOTATION
# ---------------------------------------------------------------------------

class QuotationFilter(django_filters.FilterSet):
    """
    Supported query params:
      status, status__in
      client_email         case-insensitive exact
      currency             case-insensitive exact
      issue_date__gte / lte
      valid_until__gte / lte
      total__gte / lte
      expired              true/false — past valid_until
      accepted             shortcut for status=accepted
      search               number, client_name, client_email, subject
    """

    status = django_filters.ChoiceFilter(
        choices=Quotation._meta.get_field("status").choices,
    )
    status__in = django_filters.BaseInFilter(
        field_name="status", lookup_expr="in",
    )
    client_email = django_filters.CharFilter(
        field_name="client_email", lookup_expr="iexact",
    )
    currency = django_filters.CharFilter(lookup_expr="iexact")

    issue_date__gte  = django_filters.DateFilter(field_name="issue_date",  lookup_expr="gte")
    issue_date__lte  = django_filters.DateFilter(field_name="issue_date",  lookup_expr="lte")
    valid_until__gte = django_filters.DateFilter(field_name="valid_until", lookup_expr="gte")
    valid_until__lte = django_filters.DateFilter(field_name="valid_until", lookup_expr="lte")

    created_at__gte = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at__lte = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    total__gte = django_filters.NumberFilter(field_name="total", lookup_expr="gte")
    total__lte = django_filters.NumberFilter(field_name="total", lookup_expr="lte")

    expired  = django_filters.BooleanFilter(method="filter_expired")
    accepted = django_filters.BooleanFilter(method="filter_accepted")
    search   = django_filters.CharFilter(method="filter_search")

    class Meta:
        model  = Quotation
        fields = []

    def filter_expired(self, queryset, name, value):
        today = timezone.localdate()
        if value:
            return queryset.filter(
                valid_until__lt=today,
                status__in=["draft", "sent", "viewed"],
            )
        return queryset.exclude(
            valid_until__lt=today,
            status__in=["draft", "sent", "viewed"],
        )

    def filter_accepted(self, queryset, name, value):
        if value:
            return queryset.filter(status="accepted")
        return queryset.exclude(status="accepted")

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(number__icontains=value)
            | Q(client_name__icontains=value)
            | Q(client_email__icontains=value)
            | Q(subject__icontains=value)
        )


# ---------------------------------------------------------------------------
# CONTRACT
# ---------------------------------------------------------------------------

class ContractFilter(django_filters.FilterSet):
    """
    Supported query params:
      status, status__in
      client_email         case-insensitive exact
      issue_date__gte / lte
      start_date__gte / lte
      end_date__gte / lte
      signed               true/false
      expiring_soon        true/false — expiring within 30 days
      expired              true/false — past end_date
      auto_renew           true/false
      has_ai_review        true/false
      search               number, client_name, client_email, subject, signed_by_name
    """

    status = django_filters.ChoiceFilter(
        choices=Contract._meta.get_field("status").choices,
    )
    status__in = django_filters.BaseInFilter(
        field_name="status", lookup_expr="in",
    )
    client_email = django_filters.CharFilter(
        field_name="client_email", lookup_expr="iexact",
    )

    issue_date__gte  = django_filters.DateFilter(field_name="issue_date",  lookup_expr="gte")
    issue_date__lte  = django_filters.DateFilter(field_name="issue_date",  lookup_expr="lte")
    start_date__gte  = django_filters.DateFilter(field_name="start_date",  lookup_expr="gte")
    start_date__lte  = django_filters.DateFilter(field_name="start_date",  lookup_expr="lte")
    end_date__gte    = django_filters.DateFilter(field_name="end_date",    lookup_expr="gte")
    end_date__lte    = django_filters.DateFilter(field_name="end_date",    lookup_expr="lte")

    created_at__gte  = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at__lte  = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    signed         = django_filters.BooleanFilter(method="filter_signed")
    expiring_soon  = django_filters.BooleanFilter(method="filter_expiring_soon")
    expired        = django_filters.BooleanFilter(method="filter_expired")
    auto_renew     = django_filters.BooleanFilter()
    has_ai_review  = django_filters.BooleanFilter(method="filter_has_ai_review")
    search         = django_filters.CharFilter(method="filter_search")

    class Meta:
        model  = Contract
        fields = []

    def filter_signed(self, queryset, name, value):
        if value:
            return queryset.filter(status__in=["signed", "active", "completed"])
        return queryset.exclude(status__in=["signed", "active", "completed"])

    def filter_expiring_soon(self, queryset, name, value):
        today     = timezone.localdate()
        threshold = today + __import__("datetime").timedelta(days=30)
        if value:
            return queryset.filter(
                end_date__gte=today,
                end_date__lte=threshold,
                status__in=["signed", "active"],
            )
        return queryset

    def filter_expired(self, queryset, name, value):
        today = timezone.localdate()
        if value:
            return queryset.filter(
                end_date__lt=today,
                status__in=["signed", "active"],
            )
        return queryset.exclude(
            end_date__lt=today,
            status__in=["signed", "active"],
        )

    def filter_has_ai_review(self, queryset, name, value):
        if value:
            # ai_review is a JSONField — non-empty dict
            return queryset.exclude(ai_review={}).exclude(ai_review__isnull=True)
        return queryset.filter(Q(ai_review={}) | Q(ai_review__isnull=True))

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(number__icontains=value)
            | Q(client_name__icontains=value)
            | Q(client_email__icontains=value)
            | Q(subject__icontains=value)
            | Q(signed_by_name__icontains=value)
        )


# ---------------------------------------------------------------------------
# PAYMENT RECORD
# ---------------------------------------------------------------------------

class PaymentRecordFilter(django_filters.FilterSet):
    """
    Supported query params:
      invoice              UUID of the parent invoice
      payment_method       exact match from choices
      payment_date__gte    YYYY-MM-DD
      payment_date__lte    YYYY-MM-DD
      amount__gte          decimal
      amount__lte          decimal
      is_reversed          true/false
      reference            case-insensitive contains
    """

    invoice        = django_filters.UUIDFilter(field_name="invoice_id")
    payment_method = django_filters.ChoiceFilter(
        choices=PaymentRecord.PAYMENT_METHOD_CHOICES,
    )
    payment_date__gte = django_filters.DateFilter(field_name="payment_date", lookup_expr="gte")
    payment_date__lte = django_filters.DateFilter(field_name="payment_date", lookup_expr="lte")
    amount__gte       = django_filters.NumberFilter(field_name="amount", lookup_expr="gte")
    amount__lte       = django_filters.NumberFilter(field_name="amount", lookup_expr="lte")
    is_reversed       = django_filters.BooleanFilter()
    reference         = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model  = PaymentRecord
        fields = []


# ---------------------------------------------------------------------------
# DOCUMENT ACTIVITY
# ---------------------------------------------------------------------------

class DocumentActivityFilter(django_filters.FilterSet):
    """
    Supported query params:
      doc_type             invoice | quotation | contract
      doc_id               UUID of the specific document
      action               ActivityAction choice value
      action__in           comma-separated
      actor                UUID of the user
      created_at__gte      datetime
      created_at__lte      datetime
      company_id           UUID of the company
    """

    doc_type = django_filters.ChoiceFilter(
        choices=DocumentActivity._meta.get_field("doc_type").choices,
    )
    doc_id  = django_filters.UUIDFilter()
    action  = django_filters.ChoiceFilter(
        choices=DocumentActivity._meta.get_field("action").choices,
    )
    action__in = django_filters.BaseInFilter(
        field_name="action", lookup_expr="in",
    )
    actor      = django_filters.UUIDFilter(field_name="actor_id")
    company_id = django_filters.UUIDFilter()

    created_at__gte = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at__lte = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model  = DocumentActivity
        fields = []


# ---------------------------------------------------------------------------
# RECURRING INVOICE
# ---------------------------------------------------------------------------

class RecurringInvoiceFilter(django_filters.FilterSet):
    """
    Supported query params:
      frequency            weekly | monthly | quarterly | ...
      is_active            true/false
      auto_send            true/false
      due_today            true/false — next_invoice_date <= today
      next_date__gte       YYYY-MM-DD
      next_date__lte       YYYY-MM-DD
    """

    frequency  = django_filters.ChoiceFilter(
        choices=RecurringInvoice._meta.get_field("frequency").choices,
    )
    is_active  = django_filters.BooleanFilter()
    auto_send  = django_filters.BooleanFilter()
    due_today  = django_filters.BooleanFilter(method="filter_due_today")

    next_date__gte = django_filters.DateFilter(
        field_name="next_invoice_date", lookup_expr="gte",
    )
    next_date__lte = django_filters.DateFilter(
        field_name="next_invoice_date", lookup_expr="lte",
    )

    class Meta:
        model  = RecurringInvoice
        fields = []

    def filter_due_today(self, queryset, name, value):
        today = timezone.localdate()
        if value:
            return queryset.filter(is_active=True, next_invoice_date__lte=today)
        return queryset.filter(next_invoice_date__gt=today)