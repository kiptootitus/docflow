from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import IntegrationConfig, SyncHistory, WebhookLog


class SyncHistoryInline(admin.TabularInline):
    """Shows recent sync history records directly inside the Integration Config view."""
    model = SyncHistory
    extra = 0
    max_num = 5  # Limit to prevent heavy queries
    ordering = ["-started_at"]
    readonly_fields = ["sync_type", "status", "items_processed", "items_succeeded", "items_failed", "started_at"]
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(IntegrationConfig)
class IntegrationConfigAdmin(admin.ModelAdmin):
    list_display = [
        "company",
        "integration_type",
        "status_badge",
        "is_active",
        "is_default",
        "sync_frequency",
        "last_sync_at",
        "success_rate_display",
    ]
    list_filter = ["integration_type", "status", "is_active", "is_default", "sync_frequency"]
    search_fields = ["company__name", "last_sync_status", "last_error"]
    list_select_related = ["company"]  # Prevents N+1 database queries
    inlines = [SyncHistoryInline]
    
    fieldsets = (
        (_("Core Information"), {
            "fields": ("company", "integration_type", "status", "is_active", "is_default")
        }),
        (_("Security & Credentials"), {
            "classes": ("collapse",),  # Keeps credentials hidden by default
            "fields": ("credentials",),
        }),
        (_("Sync Rules"), {
            "fields": ("auto_sync_enabled", "sync_frequency")
        }),
        (_("Latest Sync Health"), {
            "fields": ("last_sync_at", "last_sync_status", "last_error"),
        }),
        (_("Performance Analytics"), {
            "fields": ("total_syncs", "successful_syncs", "failed_syncs", "success_rate_display"),
        }),
    )
    
    readonly_fields = ["created_at", "updated_at", "success_rate_display"]

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            "active": "#28a745",       # Green
            "degraded": "#ffc107",     # Yellow
            "inactive": "#6c757d",     # Grey
            "error": "#dc3545",        # Red
            "pending": "#17a2b8",      # Cyan
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 10px; border-radius: 12px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )

    @admin.display(description="Success Rate")
    def success_rate_display(self, obj):
        rate = obj.success_rate
        if rate >= 90:
            color = "green"
        elif rate >= 70:
            color = "orange"
        else:
            color = "red"
        return format_html('<b style="color: {};">{:.1f}%</b>', color, rate)


@admin.register(SyncHistory)
class SyncHistoryAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "company",
        "integration",
        "sync_type",
        "status_badge",
        "items_summary",
        "started_at",
        "completed_at",
    ]
    list_filter = ["sync_type", "status", "started_at"]
    search_fields = ["company__name", "integration__integration_type", "error_log"]
    list_select_related = ["company", "integration"]
    ordering = ["-started_at"]
    
    # Logs should fundamentally be Read-Only in production admin dashboards
    readonly_fields = [
        "company", "integration", "sync_type", "status", 
        "items_processed", "items_succeeded", "items_failed", 
        "started_at", "completed_at", "error_log", "sync_metadata"
    ]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            "success": "#28a745",
            "failed": "#dc3545",
            "running": "#007bff",
            "partial": "#ffc107",
            "pending": "#6c757d",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )

    @admin.display(description="Processed (Suc/Fail)")
    def items_summary(self, obj):
        return format_html(
            "Total: <b>{}</b> (<span style='color: green;'>{}</span> / <span style='color: red;'>{}</span>)",
            obj.items_processed, obj.items_succeeded, obj.items_failed
        )


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "company",
        "direction_badge",
        "event_type",
        "response_status_display",
        "success_badge",
        "created_at",
    ]
    list_filter = ["direction", "success", "response_status", "created_at"]
    search_fields = ["company__name", "event_type", "url", "error_message"]
    list_select_related = ["company", "integration"]
    ordering = ["-created_at"]
    
    # Completely Read-Only to maintain reliable audit trailing
    readonly_fields = [
        "company", "integration", "direction", "event_type", 
        "url", "request_payload", "response_status", 
        "response_payload", "success", "error_message", "created_at"
    ]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

    @admin.display(description="Direction", ordering="direction")
    def direction_badge(self, obj):
        if obj.direction == "in":
            return format_html('<span style="color: #17a2b8;">⬇ Incoming</span>')
        return format_html('<span style="color: #6610f2;">⬆ Outgoing</span>')

    @admin.display(description="Success", ordering="success")
    def success_badge(self, obj):
        if obj.success:
            return format_html('<span style="color: green; font-size: 16px;">✔</span>')
        return format_html('<span style="color: red; font-size: 16px;">✘</span>')

    @admin.display(description="HTTP Status", ordering="response_status")
    def response_status_display(self, obj):
        if not obj.response_status:
            return "-"
        if 200 <= obj.response_status < 300:
            return format_html('<b style="color: green;">{}</b>', obj.response_status)
        return format_html('<b style="color: red;">{}</b>', obj.response_status)