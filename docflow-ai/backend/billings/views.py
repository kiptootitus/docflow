"""Billing app — Stripe subscription management"""
import stripe
import logging
from django.conf import settings
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY

PLANS = {
    "starter": {"name": "Starter", "price_monthly": 1900, "currency": "usd"},  # $19/mo in cents
    "pro": {"name": "Pro", "price_monthly": 4901, "currency": "usd"},           # $49/mo
    "enterprise": {"name": "Enterprise", "price_monthly": 19900, "currency": "usd"},
}


class CreateCheckoutSessionView(APIView):
    def post(self, request):
        plan = request.data.get("plan", "starter")
        if plan not in PLANS:
            return Response({"error": "Invalid plan."}, status=400)

        plan_data = PLANS[plan]
        frontend_url = settings.FRONTEND_URL

        try:
            checkout_session = stripe.checkout.Session.create(
                customer_email=request.user.email,
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": plan_data["currency"],
                        "product_data": {"name": f"DocFlow AI {plan_data['name']}"},
                        "unit_amount": plan_data["price_monthly"],
                        "recurring": {"interval": "month"},
                    },
                    "quantity": 1,
                }],
                mode="subscription",
                success_url=f"{frontend_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{frontend_url}/billing/cancelled",
                metadata={"user_id": str(request.user.id), "plan": plan},
            )
            return Response({"checkout_url": checkout_session.url})
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {e}")
            return Response({"error": str(e)}, status=400)


class CustomerPortalView(APIView):
    def post(self, request):
        try:
            customers = stripe.Customer.list(email=request.user.email, limit=1)
            if not customers.data:
                return Response({"error": "No Stripe customer found."}, status=404)

            portal_session = stripe.billing_portal.Session.create(
                customer=customers.data[0].id,
                return_url=f"{settings.FRONTEND_URL}/billing",
            )
            return Response({"portal_url": portal_session.url})
        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=400)


class CreateInvoicePaymentLinkView(APIView):
    def post(self, request, invoice_id):
        from apps.documents.models import Invoice
        try:
            invoice = Invoice.objects.get(id=invoice_id, company__owner=request.user)
        except Invoice.DoesNotExist:
            return Response({"error": "Invoice not found."}, status=404)

        try:
            payment_link = stripe.PaymentLink.create(
                line_items=[{
                    "price_data": {
                        "currency": invoice.currency.lower(),
                        "product_data": {"name": f"Invoice {invoice.number}"},
                        "unit_amount": int(invoice.total_amount * 100),
                    },
                    "quantity": 1,
                }],
                metadata={"invoice_id": str(invoice.id)},
                after_completion={"type": "hosted_confirmation", "hosted_confirmation": {"custom_message": "Payment received!"}},
            )
            invoice.stripe_payment_link = payment_link.url
            invoice.save(update_fields=["stripe_payment_link"])
            return Response({"payment_link": payment_link.url})
        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=400)


class StripeWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.DJSTRIPE_WEBHOOK_SECRET
            )
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            return HttpResponse(status=400)

        if event["type"] == "payment_intent.succeeded":
            self._handle_payment_succeeded(event["data"]["object"])
        elif event["type"] == "customer.subscription.deleted":
            logger.info(f"Subscription cancelled: {event['data']['object']['id']}")
        elif event["type"] == "invoice.payment_failed":
            logger.warning(f"Payment failed: {event['data']['object']['id']}")

        return HttpResponse(status=200)

    def _handle_payment_succeeded(self, payment_intent):
        from apps.documents.models import Invoice
        from django.utils import timezone

        invoice_id = payment_intent.get("metadata", {}).get("invoice_id")
        if invoice_id:
            try:
                invoice = Invoice.objects.get(id=invoice_id)
                invoice.status = Invoice.Status.PAID
                invoice.paid_at = timezone.now()
                invoice.stripe_payment_intent_id = payment_intent["id"]
                invoice.save(update_fields=["status", "paid_at", "stripe_payment_intent_id"])
                logger.info(f"Invoice {invoice.number} marked as paid.")
            except Invoice.DoesNotExist:
                logger.error(f"Invoice {invoice_id} not found for payment webhook.")
