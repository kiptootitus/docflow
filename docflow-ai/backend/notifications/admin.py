"""
DocFlow AI — notifications/admin.py

Enterprise Django Administrative interface for notification tracking,
device registration token auditing, and preference matrix overrides.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Notification, NotificationPreference, PushToken

@admin.register(PushToken)
class PushTokenAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "platform", "device_name", "is_active", "created_at", "updated_at"]
    list_filter = ["platform", "is_active", "created_at", "updated_at"]
    search_fields = ["user__email", "user__username", "token", "device_name"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["-updated_at"]
    actions = ["bulk_deactivate"]

    @admin.action(description=_("Deactivate selected push tokens"))
    def bulk_deactivate(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, _(f"Successfully deactivated {updated} push token(s)."))


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "category", "priority", "title", "is_read", "created_at"]
    list_filter = ["category", "priority", "created_at", "read_at"]
    search_fields = ["user__email", "title", "body", "email_message_id", "push_ticket_id"]
    readonly_fields = ["id", "created_at", "email_message_id", "push_ticket_id"]
    ordering = ["-created_at"]
    actions = ["bulk_mark_read"]

    @admin.action(description=_("Mark selected notifications as read"))
    def bulk_mark_read(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(read_at__isnull=True).update(read_at=timezone.now())
        self.message_user(request, _(f"Successfully marked {updated} notification(s) as read."))


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "category", "channels", "updated_at"]
    list_filter = ["category", "updated_at"]
    search_fields = ["user__email", "category"]
    readonly_fields = ["id", "updated_at"]
    ordering = ["user", "category"]