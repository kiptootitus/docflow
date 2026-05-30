# analytics/serializers.py
from rest_framework import serializers
from .models import RevenueSnapshot, EventLog, MRRSnapshot, RevenueAlert, EventType, SubscriptionTier
from decimal import Decimal


class RevenueSnapshotSerializer(serializers.ModelSerializer):
    """Serializer for revenue snapshots"""
    
    churn_rate_percentage = serializers.SerializerMethodField()
    retention_rate_percentage = serializers.SerializerMethodField()
    mrr_growth = serializers.SerializerMethodField()
    
    class Meta:
        model = RevenueSnapshot
        fields = [
            'id', 'date', 'mrr', 'arr', 'ltv', 'cac',
            'total_customers', 'active_customers', 'new_customers', 
            'churned_customers', 'trial_customers',
            'mrr_starter', 'mrr_pro', 'mrr_enterprise',
            'churn_rate', 'churn_rate_percentage', 'retention_rate',
            'retention_rate_percentage', 'average_revenue_per_user',
            'total_ai_reviews', 'total_documents_generated', 'ai_credits_used',
            'data_completeness_score', 'created_at', 'updated_at',
            'mrr_growth'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_churn_rate_percentage(self, obj) -> float:
        return float(obj.churn_rate * 100)
    
    def get_retention_rate_percentage(self, obj) -> float:
        return float(obj.retention_rate)
    
    def get_mrr_growth(self, obj) -> float:
        # Calculate growth from previous day
        previous = RevenueSnapshot.objects.filter(date__lt=obj.date).order_by('-date').first()
        if previous and previous.mrr > 0:
            growth = ((obj.mrr - previous.mrr) / previous.mrr) * 100
            return float(growth)
        return 0.0


class EventLogSerializer(serializers.ModelSerializer):
    """Serializer for event logs"""
    
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    
    class Meta:
        model = EventLog
        fields = [
            'id', 'user', 'company_id', 'event_type', 'event_type_display',
            'event_name', 'metadata', 'value', 'session_id', 'ip_address',
            'user_agent', 'referrer', 'request_path', 'response_time_ms',
            'status_code', 'is_bot', 'is_test', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'user']
        extra_kwargs = {
            'ip_address': {'write_only': True},
            'user_agent': {'write_only': True},
            'referrer': {'write_only': True},
        }


class MRRSnapshotSerializer(serializers.ModelSerializer):
    """Serializer for MRR snapshots"""
    
    subscription_tier_display = serializers.CharField(source='get_subscription_tier_display', read_only=True)
    change_type_display = serializers.CharField(source='get_change_type_display', read_only=True)
    monthly_amount_usd = serializers.SerializerMethodField()
    
    class Meta:
        model = MRRSnapshot
        fields = [
            'id', 'user', 'subscription_tier', 'subscription_tier_display',
            'monthly_amount', 'monthly_amount_usd', 'period_start', 'period_end',
            'previous_amount', 'change_reason', 'change_type', 'change_type_display',
            'is_active', 'canceled_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_monthly_amount_usd(self, obj) -> float:
        return float(obj.monthly_amount)


class RevenueAlertSerializer(serializers.ModelSerializer):
    """Serializer for revenue alerts"""
    
    alert_level_display = serializers.CharField(source='get_alert_level_display', read_only=True)
    alert_type_display = serializers.CharField(source='get_alert_type_display', read_only=True)
    resolved_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = RevenueAlert
        fields = [
            'id', 'alert_type', 'alert_type_display', 'alert_level',
            'alert_level_display', 'title', 'message', 'current_value',
            'previous_value', 'threshold', 'is_resolved', 'resolved_at',
            'resolved_by', 'resolved_by_name', 'notification_sent',
            'notification_channel', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'resolved_at']
    
    def get_resolved_by_name(self, obj):
        if obj.resolved_by:
            return obj.resolved_by.get_full_name() or obj.resolved_by.email
        return None


class DashboardMetricsSerializer(serializers.Serializer):
    """Serializer for dashboard metrics"""
    
    mrr = serializers.FloatField()
    arr = serializers.FloatField()
    ltv = serializers.FloatField()
    churn_rate = serializers.FloatField()
    revenue_churn_rate = serializers.FloatField()
    active_customers = serializers.IntegerField()
    new_customers_last_30d = serializers.IntegerField()
    churned_customers_last_30d = serializers.IntegerField()
    arpu = serializers.FloatField()
    mrr_breakdown = serializers.DictField()
    growth_rate = serializers.FloatField()


class MRRAnalysisSerializer(serializers.Serializer):
    """Serializer for MRR analysis"""
    
    total_mrr = serializers.FloatField()
    new_mrr = serializers.FloatField()
    churned_mrr = serializers.FloatField()
    expansion_mrr = serializers.FloatField()
    contraction_mrr = serializers.FloatField()
    net_new_mrr = serializers.FloatField()
    growth_rate = serializers.FloatField()
    by_tier = serializers.DictField()
    mrr_percentage_by_tier = serializers.DictField()


class CohortAnalysisSerializer(serializers.Serializer):
    """Serializer for cohort analysis"""
    
    cohorts = serializers.ListField()
    
    class CohortRetentionSerializer(serializers.Serializer):
        month = serializers.IntegerField()
        retained_customers = serializers.IntegerField()
        retention_rate = serializers.FloatField()


class RevenueTrendsSerializer(serializers.Serializer):
    """Serializer for revenue trends"""
    
    trends = serializers.ListField()
    
    class TrendItemSerializer(serializers.Serializer):
        date = serializers.DateField()
        mrr = serializers.FloatField()
        active_customers = serializers.IntegerField()
        new_customers = serializers.IntegerField()
        churned_customers = serializers.IntegerField()
        churn_rate = serializers.FloatField()
        arpu = serializers.FloatField()

