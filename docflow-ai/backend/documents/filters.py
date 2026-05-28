"""
DocFlow AI — documents/filters.py

django-filter FilterSets for Invoice, Quotation, and Contract.

All filters scope to the requesting user's company via the view's
get_queryset().  Date range, status, and search filters are provided.
"""

from __future__ import annotations

import django_filters
from django.db.models import Q

from .models import Contract, Invoice, Quotation


class InvoiceFilter(django_filters.FilterSet):
    """
    Supported query params:
      status, status__in
      client_email
      currency
      issue_date__gte / issue_date__lte
      due_date__gte  / due_date__lte
      created_at__gte / created_at__lte
      total__gte / total__lte
      overdue (boolean)
      search  (number, client_name, client_email, subject)
    """

    status = django_filters.ChoiceFilter(
        choices=Invoice._meta.get_field("status").choices,
    )
    status__in = django_filters.BaseInFilter(
        field_name="status", lookup_expr="in",
    )
    client_email = django_filters.CharFilter(
        field_name="client_email", lookup_expr="iexact",
    )
    currency = django_filters.CharFilter(lookup_expr="iexact")

    issue_date__gte = django_filters.DateFilter(field_name="issue_date", lookup_expr="gte")
    issue_date__lte = django_filters.DateFilter(field_name="issue_date", lookup_expr="lte")
    due_date__gte   = django_filters.DateFilter(field_name="due_date",   lookup_expr="gte")
    due_date__lte   = django_filters.DateFilter(field_name="due_date",   lookup_expr="lte")

    created_at__gte = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at__lte = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    total__gte = django_filters.NumberFilter(field_name="total", lookup_expr="gte")
    total__lte = django_filters.NumberFilter(field_name="total", lookup_expr="lte")

    overdue = django_filters.BooleanFilter(method="filter_overdue")

    search = django_filters.CharFilter(method="filter_search")

    def filter_overdue(self, queryset, name, value):
        from django.utils import timezone
        today = timezone.localdate()
        if value:
            return queryset.filter(
                due_date__lt=today,
                status__in=["sent", "viewed", "partial"],
            )
        return queryset

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(number__icontains=value)
            | Q(client_name__icontains=value)
            | Q(client_email__icontains=value)
            | Q(subject__icontains=value)
        )

    class Meta:
        model  = Invoice
        fields = []


class QuotationFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=Quotation._meta.get_field("status").choices,
    )
    status__in = django_filters.BaseInFilter(field_name="status", lookup_expr="in")
    client_email = django_filters.CharFilter(field_name="client_email", lookup_expr="iexact")
    currency = django_filters.CharFilter(lookup_expr="iexact")

    issue_date__gte  = django_filters.DateFilter(field_name="issue_date",  lookup_expr="gte")
    issue_date__lte  = django_filters.DateFilter(field_name="issue_date",  lookup_expr="lte")
    valid_until__gte = django_filters.DateFilter(field_name="valid_until", lookup_expr="gte")
    valid_until__lte = django_filters.DateFilter(field_name="valid_until", lookup_expr="lte")

    total__gte = django_filters.NumberFilter(field_name="total", lookup_expr="gte")
    total__lte = django_filters.NumberFilter(field_name="total", lookup_expr="lte")

    search = django_filters.CharFilter(method="filter_search")

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(number__icontains=value)
            | Q(client_name__icontains=value)
            | Q(client_email__icontains=value)
            | Q(subject__icontains=value)
        )

    class Meta:
        model  = Quotation
        fields = []


class ContractFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=Contract._meta.get_field("status").choices,
    )
    status__in = django_filters.BaseInFilter(field_name="status", lookup_expr="in")
    client_email = django_filters.CharFilter(field_name="client_email", lookup_expr="iexact")

    issue_date__gte = django_filters.DateFilter(field_name="issue_date", lookup_expr="gte")
    issue_date__lte = django_filters.DateFilter(field_name="issue_date", lookup_expr="lte")
    end_date__gte   = django_filters.DateFilter(field_name="end_date",   lookup_expr="gte")
    end_date__lte   = django_filters.DateFilter(field_name="end_date",   lookup_expr="lte")

    expiring_soon = django_filters.BooleanFilter(method="filter_expiring_soon")
    auto_renew    = django_filters.BooleanFilter()

    search = django_filters.CharFilter(method="filter_search")

    def filter_expiring_soon(self, queryset, name, value):
        from django.utils import timezone
        import datetime
        today = timezone.localdate()
        threshold = today + datetime.timedelta(days=30)
        if value:
            return queryset.filter(end_date__gte=today, end_date__lte=threshold)
        return queryset

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(number__icontains=value)
            | Q(client_name__icontains=value)
            | Q(client_email__icontains=value)
            | Q(subject__icontains=value)
        )

    class Meta:
        model  = Contract
        fields = []
