# analytics/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import RevenueSnapshot, EventLog, MRRSnapshot, RevenueAlert, CohortAnalysis


@admin.register(RevenueSnapshot)
class RevenueSnapshotAdmin(admin.ModelAdmin):
    list_display = ['date', 'mrr', 'arr', 'active_customers', 'churn_rate', 'retention_rate']
    list_filter = ['date', 'active_customers']
    search_fields = ['date']
    readonly_fields = ['id', 'created_at', 'updated_at', 'data_completeness_score']
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('id', 'date')
        }),
        ('Revenue Metrics', {
            'fields': ('mrr', 'arr', 'ltv', 'cac', 'average_revenue_per_user')
        }),
        ('Customer Metrics', {
            'fields': ('total_customers', 'active_customers', 'new_customers', 
                      'churned_customers', 'trial_customers')
        }),
        ('MRR Breakdown', {
            'fields': ('mrr_starter', 'mrr_pro', 'mrr_enterprise')
        }),
        ('Retention Metrics', {
            'fields': ('churn_rate', 'retention_rate')
        }),
        ('AI Usage', {
            'fields': ('total_ai_reviews', 'total_documents_generated', 'ai_credits_used')
        }),
        ('Quality Metrics', {
            'fields': ('data_completeness_score',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing existing object
            return self.readonly_fields + ('date',)
        return self.readonly_fields


@admin.register(EventLog)
class EventLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'user_link', 'event_type', 'event_name', 'value', 'is_bot']
    list_filter = ['event_type', 'is_bot', 'created_at']
    search_fields = ['user__email', 'user__first_name', 'event_name', 'metadata']
    readonly_fields = ['id', 'created_at', 'user']
    date_hierarchy = 'created_at'
    
    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:auth_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.email)
        return '-'
    user_link.short_description = 'User'
    
    fieldsets = (
        ('Event Info', {
            'fields': ('user', 'company_id', 'event_type', 'event_name', 'value')
        }),
        ('Context', {
            'fields': ('session_id', 'ip_address', 'user_agent', 'referrer', 'request_path')
        }),
        ('Technical', {
            'fields': ('response_time_ms', 'status_code', 'is_bot', 'is_test')
        }),
        ('Metadata', {
            'fields': ('metadata',)
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )


@admin.register(MRRSnapshot)
class MRRSnapshotAdmin(admin.ModelAdmin):
    list_display = ['user_link', 'subscription_tier', 'monthly_amount', 'period_start', 'is_active']
    list_filter = ['subscription_tier', 'change_type', 'is_active', 'period_start']
    search_fields = ['user__email', 'user__first_name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    date_hierarchy = 'period_start'
    
    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:auth_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.email)
        return '-'
    user_link.short_description = 'User'


@admin.register(RevenueAlert)
class RevenueAlertAdmin(admin.ModelAdmin):
    list_display = ['title', 'alert_type', 'alert_level', 'created_at', 'is_resolved']
    list_filter = ['alert_type', 'alert_level', 'is_resolved', 'created_at']
    search_fields = ['title', 'message']
    readonly_fields = ['id', 'created_at']
    date_hierarchy = 'created_at'
    
    actions = ['mark_as_resolved']
    
    def mark_as_resolved(self, request, queryset):
        updated = queryset.update(is_resolved=True)
        self.message_user(request, f'{updated} alerts marked as resolved.')
    mark_as_resolved.short_description = 'Mark selected alerts as resolved'


@admin.register(CohortAnalysis)
class CohortAnalysisAdmin(admin.ModelAdmin):
    list_display = ['cohort_name', 'cohort_date', 'cohort_type', 'period_0_users', 'total_revenue_generated']
    list_filter = ['cohort_type', 'cohort_date']
    search_fields = ['cohort_name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    date_hierarchy = 'cohort_date'          