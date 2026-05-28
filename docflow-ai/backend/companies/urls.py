"""
DocFlow AI — companies/urls.py

URL patterns for the companies app.

Mounted at /api/companies/ by the root urls.py.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CompanyBrandingView, CompanyMemberViewSet, CompanyViewSet, VATConfigView

router = DefaultRouter()
router.register(r"", CompanyViewSet, basename="company")

# Nested member router — registered manually for clarity
member_router = DefaultRouter()
member_router.register(r"members", CompanyMemberViewSet, basename="company-member")

urlpatterns = [
    # Company CRUD + restore action
    path("", include(router.urls)),

    # Per-company branding
    path("<uuid:pk>/branding/", CompanyBrandingView.as_view(), name="company-branding"),

    # Per-company VAT config
    path("<uuid:pk>/vat/", VATConfigView.as_view(), name="company-vat"),

    # Nested members (list, retrieve, destroy, invite, update_role)
    path("<uuid:company_pk>/", include(member_router.urls)),
]
