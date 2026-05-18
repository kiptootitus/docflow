"""Companies views"""
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Company, CompanyMember, Client
from .serializers import CompanySerializer, CompanyMemberSerializer, ClientSerializer


class IsCompanyOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Company):
            return obj.owner == request.user
        return obj.company.owner == request.user


class CompanyViewSet(viewsets.ModelViewSet):
    serializer_class = CompanySerializer

    def get_queryset(self):
        return Company.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        company = serializer.save(owner=self.request.user)
        # Auto-add owner as member
        CompanyMember.objects.create(company=company, user=self.request.user, role="owner")

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        company = self.get_object()
        from apps.documents.models import Invoice
        invoices = Invoice.objects.filter(company=company)
        return Response({
            "total_invoices": invoices.count(),
            "paid": invoices.filter(status="paid").count(),
            "pending": invoices.filter(status="sent").count(),
            "draft": invoices.filter(status="draft").count(),
            "total_revenue": str(invoices.filter(status="paid").aggregate(
                total=__import__("django.db.models", fromlist=["Sum"]).Sum("total_amount")
            )["total"] or 0),
        })


class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    search_fields = ["name", "email"]
    filterset_fields = ["is_active"]

    def get_queryset(self):
        return Client.objects.filter(company__owner=self.request.user)

    def perform_create(self, serializer):
        company_id = self.request.data.get("company")
        from .models import Company
        company = Company.objects.get(id=company_id, owner=self.request.user)
        serializer.save(company=company)
