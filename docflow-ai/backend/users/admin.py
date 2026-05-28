from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count

from .models import (
    User,
    UserRole,
    UserAuditLog,
    EmailVerificationToken,
    PasswordResetToken,
)


# ---------------------------------------------------------------------------
# Helpers / Filters
# ---------------------------------------------------------------------------

class RoleFilter(admin.SimpleListFilter):
    title = _("Role")
    parameter_name = "role"

    def lookups(self, request, model_admin):
        return [(r.value, r.name.title()) for r in UserRole]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(role=self.value())
        return queryset


class VerifiedFilter(admin.SimpleListFilter):
    title = _("Verified")
    parameter_name = "verified"

    def lookups(self, request, model_admin):
        return [
            ("yes", _("Verified")),
            ("no", _("Not Verified")),
        ]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(is_verified=True)
        if self.value() == "no":
            return queryset.filter(is_verified=False)
        return queryset


class DeletedFilter(admin.SimpleListFilter):
    title = _("Deleted")
    parameter_name = "deleted"

    def lookups(self, request, model_admin):
        return [
            ("yes", _("Deleted")),
            ("no", _("Active")),
        ]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(deleted_at__isnull=False)
        if self.value() == "no":
            return queryset.filter(deleted_at__isnull=True)
        return queryset


# ---------------------------------------------------------------------------
# User Admin
# ---------------------------------------------------------------------------

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "full_name",
        "role",
        "is_active",
        "is_verified",
        "is_staff",
        "totp_enabled",
        "deleted_status",
        "date_joined",
    )

    list_filter = (
        RoleFilter,
        VerifiedFilter,
        DeletedFilter,
        "is_active",
        "is_staff",
        "totp_enabled",
    )

    search_fields = (
        "email",
        "first_name",
        "last_name",
    )

    ordering = ("-date_joined",)

    readonly_fields = (
        "id",
        "date_joined",
        "updated_at",
        "last_login_ip",
        "deleted_at",
        "password_preview",
    )

    fieldsets = (
        (_("Identity"), {
            "fields": ("id", "email", "first_name", "last_name", "avatar")
        }),
        (_("Access & Role"), {
            "fields": ("role", "is_active", "is_staff", "is_verified")
        }),
        (_("Security"), {
            "fields": ("totp_enabled", "last_login_ip", "password_preview")
        }),
        (_("Preferences"), {
            "fields": ("timezone_name", "language")
        }),
        (_("Lifecycle"), {
            "fields": ("date_joined", "updated_at", "deleted_at")
        }),
    )

    actions = ["soft_delete_users", "restore_users", "mark_verified"]

    # -------------------------------------------------------------------
    # Display helpers
    # -------------------------------------------------------------------

    def deleted_status(self, obj):
        if obj.deleted_at:
            return format_html("<span style='color:red'>Deleted</span>")
        return format_html("<span style='color:green'>Active</span>")

    deleted_status.short_description = "Status"

    def password_preview(self, obj):
        return "******** (hashed)"

    password_preview.short_description = "Password"

    # -------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------

    def soft_delete_users(self, request, queryset):
        updated = 0
        for user in queryset:
            user.soft_delete()
            updated += 1
        self.message_user(request, f"{updated} users soft-deleted.")

    soft_delete_users.short_description = "Soft delete selected users"

    def restore_users(self, request, queryset):
        updated = 0
        for user in queryset:
            user.restore()
            updated += 1
        self.message_user(request, f"{updated} users restored.")

    restore_users.short_description = "Restore selected users"

    def mark_verified(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f"{updated} users marked as verified.")

    mark_verified.short_description = "Mark as verified"


# ---------------------------------------------------------------------------
# Audit Log Admin (Read-only, security-critical)
# ---------------------------------------------------------------------------

@admin.register(UserAuditLog)
class UserAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "event",
        "ip_address",
        "created_at",
    )

    list_filter = (
        "event",
        "created_at",
    )

    search_fields = (
        "user__email",
        "ip_address",
        "event",
    )

    readonly_fields = (
        "id",
        "user",
        "event",
        "ip_address",
        "user_agent",
        "metadata",
        "created_at",
    )

    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False  # immutable log

    def has_change_permission(self, request, obj=None):
        return False  # immutable log

    def has_delete_permission(self, request, obj=None):
        return False  # immutable log


# ---------------------------------------------------------------------------
# Email Verification Token Admin
# ---------------------------------------------------------------------------

@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "token_preview",
        "is_used",
        "is_expired",
        "created_at",
    )

    search_fields = ("user__email", "token")
    readonly_fields = ("id", "user", "token", "created_at", "used_at")

    ordering = ("-created_at",)

    def token_preview(self, obj):
        return f"{obj.token[:10]}..."

    token_preview.short_description = "Token"


# ---------------------------------------------------------------------------
# Password Reset Token Admin (secure preview only)
# ---------------------------------------------------------------------------

@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "token_hash_preview",
        "is_used",
        "is_expired",
        "created_at",
    )

    search_fields = ("user__email", "token_hash")
    readonly_fields = ("id", "user", "token_hash", "created_at", "used_at")

    ordering = ("-created_at",)

    def token_hash_preview(self, obj):
        return f"{obj.token_hash[:12]}..."

    token_hash_preview.short_description = "Token Hash"