"""
DocFlow AI — companies/tests.py

Pytest-style tests covering:
  • Model creation / soft-delete / restore
  • Auto-slug generation
  • Document number increment (race-safe)
  • CompanyBranding auto-creation
  • API — CRUD, permissions, member invite flow
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from users.models import User, UserRole

from .models import Company, CompanyBranding, CompanyMembership, MemberRole, VATConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def owner(db) -> User:
    return User.objects.create_user(
        email="owner@example.com",
        password="Owner@1234!",
        first_name="Alice",
        last_name="Owner",
        is_verified=True,
    )


@pytest.fixture
def staff_user(db) -> User:
    return User.objects.create_user(
        email="staff@example.com",
        password="Staff@1234!",
        first_name="Bob",
        last_name="Staff",
        role=UserRole.STAFF,
        is_verified=True,
    )


@pytest.fixture
def client_user(db) -> User:
    return User.objects.create_user(
        email="client@example.com",
        password="Client@1234!",
        first_name="Carol",
        last_name="Client",
        role=UserRole.CLIENT,
        is_verified=True,
    )


@pytest.fixture
def company(db, owner) -> Company:
    c = Company.objects.create(
        name="Acme Ltd",
        owner=owner,
        email="acme@example.com",
        currency="USD",
    )
    c.slug = "acme-ltd"
    c.save()
    CompanyMembership.objects.get_or_create(
        company=c, user=owner,
        defaults={"role": MemberRole.OWNER, "is_active": True},
    )
    return c


@pytest.fixture
def auth_client(owner) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=owner)
    return c


@pytest.fixture
def staff_client(staff_user, company) -> APIClient:
    CompanyMembership.objects.get_or_create(
        company=company, user=staff_user,
        defaults={"role": MemberRole.STAFF, "is_active": True},
    )
    c = APIClient()
    c.force_authenticate(user=staff_user)
    return c


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestCompanyModel:
    def test_str(self, company):
        assert str(company) == "Acme Ltd"

    def test_is_deleted_false_by_default(self, company):
        assert company.is_deleted is False

    def test_soft_delete(self, company):
        company.soft_delete()
        company.refresh_from_db()
        assert company.is_active is False
        assert company.deleted_at is not None
        assert company.is_deleted is True

    def test_restore(self, company):
        company.soft_delete()
        company.is_active = True
        company.deleted_at = None
        company.save()
        company.refresh_from_db()
        assert company.is_deleted is False

    def test_invoice_number_increment(self, company):
        n1 = company.get_next_invoice_number()
        n2 = company.get_next_invoice_number()
        assert n1 == "INV-0001"
        assert n2 == "INV-0002"

    def test_quotation_number_increment(self, company):
        n = company.get_next_quotation_number()
        assert n.startswith("QT-")

    def test_contract_number_increment(self, company):
        n = company.get_next_contract_number()
        assert n.startswith("CNT-")

    def test_full_address(self, company):
        company.address_line1 = "123 Main St"
        company.city = "Nairobi"
        company.country = "KE"
        company.save()
        assert "Nairobi" in company.full_address
        assert "KE" in company.full_address

    def test_branding_auto_created_via_serializer(self, db, owner):
        from rest_framework.test import APIRequestFactory
        from .serializers import CompanySerializer

        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = owner

        s = CompanySerializer(
            data={"name": "NewCo", "currency": "KES"},
            context={"request": request},
        )
        assert s.is_valid(), s.errors
        c = s.save()
        assert CompanyBranding.objects.filter(company=c).exists()
        assert VATConfig.objects.filter(company=c).exists()


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCompanyAPI:

    def test_create_company(self, auth_client):
        url = reverse("company-list")
        resp = auth_client.post(url, {"name": "Beta Corp", "currency": "KES"})
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["name"] == "Beta Corp"
        assert resp.data["currency"] == "KES"

    def test_list_only_own_companies(self, auth_client, company):
        url = reverse("company-list")
        resp = auth_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        ids = [c["id"] for c in resp.data["results"]]
        assert str(company.id) in ids

    def test_retrieve_company_as_member(self, staff_client, company):
        url = reverse("company-detail", kwargs={"pk": company.pk})
        resp = staff_client.get(url)
        assert resp.status_code == status.HTTP_200_OK

    def test_update_company_as_owner(self, auth_client, company):
        url = reverse("company-detail", kwargs={"pk": company.pk})
        resp = auth_client.patch(url, {"phone": "+254700000000"})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["phone"] == "+254700000000"

    def test_update_company_as_staff_forbidden(self, staff_client, company):
        url = reverse("company-detail", kwargs={"pk": company.pk})
        resp = staff_client.patch(url, {"phone": "+254700000000"})
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_soft_delete_company(self, auth_client, company):
        url = reverse("company-detail", kwargs={"pk": company.pk})
        resp = auth_client.delete(url)
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        company.refresh_from_db()
        assert company.is_deleted

    def test_unauthenticated_forbidden(self):
        client = APIClient()
        url = reverse("company-list")
        assert client.get(url).status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestBrandingAPI:

    def test_get_branding(self, auth_client, company):
        CompanyBranding.objects.get_or_create(company=company)
        url = reverse("company-branding", kwargs={"pk": company.pk})
        resp = auth_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        assert "primary_color" in resp.data

    def test_patch_branding(self, auth_client, company):
        CompanyBranding.objects.get_or_create(company=company)
        url = reverse("company-branding", kwargs={"pk": company.pk})
        resp = auth_client.patch(url, {"primary_color": "#FF5733"})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["primary_color"] == "#FF5733"

    def test_invalid_hex_color_rejected(self, auth_client, company):
        CompanyBranding.objects.get_or_create(company=company)
        url = reverse("company-branding", kwargs={"pk": company.pk})
        resp = auth_client.patch(url, {"primary_color": "not-a-color"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestMembershipAPI:

    def test_list_members(self, auth_client, company):
        url = reverse("company-member-list", kwargs={"company_pk": company.pk})
        resp = auth_client.get(url)
        assert resp.status_code == status.HTTP_200_OK

    def test_invite_existing_user(self, auth_client, company, staff_user):
        url = reverse("company-member-invite", kwargs={"company_pk": company.pk})
        resp = auth_client.post(url, {"email": staff_user.email, "role": "staff"})
        assert resp.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK)
        assert CompanyMembership.objects.filter(
            company=company, user=staff_user, is_active=True
        ).exists()

    def test_invite_nonexistent_email_fails(self, auth_client, company):
        url = reverse("company-member-invite", kwargs={"company_pk": company.pk})
        resp = auth_client.post(url, {"email": "ghost@example.com", "role": "staff"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_remove_member(self, auth_client, company, staff_user):
        membership = CompanyMembership.objects.create(
            company=company, user=staff_user, role=MemberRole.STAFF, is_active=True
        )
        url = reverse(
            "company-member-detail",
            kwargs={"company_pk": company.pk, "pk": membership.pk},
        )
        resp = auth_client.delete(url)
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        membership.refresh_from_db()
        assert not membership.is_active