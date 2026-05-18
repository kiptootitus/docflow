"""Invoice API tests"""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from apps.users.models import User
from apps.companies.models import Company, Client
from apps.documents.models import Invoice, InvoiceLineItem
import datetime


@pytest.fixture
def client_api():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="test@docflow.com",
        password="testpass123",
        first_name="Test",
        last_name="User",
        role=User.Role.OWNER,
    )


@pytest.fixture
def auth_client(client_api, user):
    client_api.force_authenticate(user=user)
    return client_api


@pytest.fixture
def company(db, user):
    return Company.objects.create(
        owner=user,
        name="Test Corp",
        email="test@corp.com",
        default_currency="KES",
        tax_rate=16,
    )


@pytest.fixture
def client_obj(db, company):
    return Client.objects.create(
        company=company,
        name="Acme Ltd",
        email="billing@acme.com",
    )


@pytest.fixture
def invoice(db, company, client_obj, user):
    inv = Invoice.objects.create(
        company=company,
        client=client_obj,
        created_by=user,
        number="INV-0001",
        status="draft",
        currency="KES",
        issue_date=datetime.date.today(),
        due_date=datetime.date.today() + datetime.timedelta(days=30),
        tax_rate=16,
    )
    InvoiceLineItem.objects.create(
        invoice=inv, description="Web Design", quantity=1, unit_price=50000, order=0
    )
    inv.calculate_totals()
    return inv


class TestInvoiceAPI:
    def test_list_invoices(self, auth_client, invoice):
        res = auth_client.get("/api/v1/documents/invoices/")
        assert res.status_code == 200
        assert res.data["count"] >= 1

    def test_create_invoice(self, auth_client, company, client_obj):
        payload = {
            "company": str(company.id),
            "client": str(client_obj.id),
            "currency": "KES",
            "issue_date": str(datetime.date.today()),
            "due_date": str(datetime.date.today() + datetime.timedelta(days=30)),
            "tax_rate": 16,
            "discount_amount": 0,
            "line_items": [
                {"description": "Consulting", "quantity": 2, "unit_price": 25000, "order": 0}
            ],
        }
        res = auth_client.post("/api/v1/documents/invoices/", payload, format="json")
        assert res.status_code == 201
        assert res.data["number"].startswith("INV")

    def test_mark_paid(self, auth_client, invoice):
        res = auth_client.post(f"/api/v1/documents/invoices/{invoice.id}/mark_paid/")
        assert res.status_code == 200
        assert res.data["status"] == "paid"

    def test_send_email_requires_client(self, auth_client, company, user):
        inv = Invoice.objects.create(
            company=company, created_by=user, number="INV-0002",
            issue_date=datetime.date.today(), currency="KES", tax_rate=16,
        )
        res = auth_client.post(f"/api/v1/documents/invoices/{inv.id}/send_email/")
        assert res.status_code == 400

    def test_duplicate_invoice(self, auth_client, invoice):
        res = auth_client.post(f"/api/v1/documents/invoices/{invoice.id}/duplicate/")
        assert res.status_code == 201
        assert res.data["id"] != str(invoice.id)

    def test_unauthenticated_denied(self, client_api, invoice):
        res = client_api.get("/api/v1/documents/invoices/")
        assert res.status_code == 401
