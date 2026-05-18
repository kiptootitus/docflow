from django.contrib import admin
from .models import Company, CompanyMember, Client


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "default_currency", "is_active", "created_at"]
    search_fields = ["name", "email"]
    list_filter = ["is_active", "default_currency"]


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "company", "is_active"]
    search_fields = ["name", "email"]
    list_filter = ["company", "is_active"]


@admin.register(CompanyMember)
class CompanyMemberAdmin(admin.ModelAdmin):
    list_display = ["user", "company", "role", "created_at"]
