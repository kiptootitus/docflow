from django.urls import path
from .views import CreateCheckoutSessionView, CustomerPortalView, CreateInvoicePaymentLinkView, StripeWebhookView

urlpatterns = [
    path("checkout/", CreateCheckoutSessionView.as_view(), name="billing-checkout"),
    path("portal/", CustomerPortalView.as_view(), name="billing-portal"),
    path("invoices/<uuid:invoice_id>/payment-link/", CreateInvoicePaymentLinkView.as_view(), name="invoice-payment-link"),
    path("webhooks/stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
