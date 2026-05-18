"""Companies app models"""
import uuid
from django.db import models
from django.conf import settings


class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_companies",
    )
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to="company_logos/", null=True, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)

    # Address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default="KE")

    # Finance
    vat_number = models.CharField(max_length=50, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=16.00)
    default_currency = models.CharField(max_length=3, default="KES")
    branding_color = models.CharField(max_length=7, default="#6366f1")

    # Invoice settings
    invoice_prefix = models.CharField(max_length=10, default="INV")
    invoice_counter = models.PositiveIntegerField(default=1)
    invoice_notes = models.TextField(blank=True)
    invoice_terms = models.TextField(blank=True)
    payment_due_days = models.PositiveIntegerField(default=30)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "companies"
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name

    def next_invoice_number(self):
        number = f"{self.invoice_prefix}-{self.invoice_counter:04d}"
        self.invoice_counter += 1
        self.save(update_fields=["invoice_counter"])
        return number


class CompanyMember(models.Model):
    """Links users to companies with role-based access."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="company_memberships")
    role = models.CharField(max_length=20, choices=[
        ("owner", "Owner"),
        ("staff", "Staff"),
        ("accountant", "Accountant"),
        ("viewer", "Viewer"),
    ], default="staff")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "company_members"
        unique_together = [["company", "user"]]

    def __str__(self):
        return f"{self.user.email} @ {self.company.name} ({self.role})"


class Client(models.Model):
    """Clients belong to a company (multi-tenancy via company FK)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="clients")
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    vat_number = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clients"
        unique_together = [["company", "email"]]

    def __str__(self):
        return f"{self.name} ({self.company.name})"
