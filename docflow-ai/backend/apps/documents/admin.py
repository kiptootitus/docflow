from django.contrib import admin
from .models import Invoice, InvoiceLineItem, Quotation, Contract


class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 0
    readonly_fields = ["amount"]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["number", "company", "client", "status", "total_amount", "currency", "created_at"]
    list_filter = ["status", "currency"]
    search_fields = ["number", "client__name", "company__name"]
    inlines = [InvoiceLineItemInline]
    readonly_fields = ["subtotal", "tax_amount", "total_amount", "portal_token", "created_at"]


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "client", "status", "contract_type", "created_at"]
    list_filter = ["status", "contract_type"]
    search_fields = ["title", "client__name"]
