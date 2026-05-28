"""
DocFlow AI — documents/urls.py

Mounted at /api/ by the root urls.py.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ContractViewSet, InvoiceViewSet, QuotationViewSet

router = DefaultRouter()
router.register(r"invoices",   InvoiceViewSet,   basename="invoice")
router.register(r"quotations", QuotationViewSet, basename="quotation")
router.register(r"contracts",  ContractViewSet,  basename="contract")

urlpatterns = [
    path("", include(router.urls)),
]
