from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InvoiceViewSet, QuotationViewSet, ContractViewSet

router = DefaultRouter()
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("quotations", QuotationViewSet, basename="quotation")
router.register("contracts", ContractViewSet, basename="contract")

urlpatterns = [path("", include(router.urls))]
