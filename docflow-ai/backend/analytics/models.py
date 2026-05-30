# analytics/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.db.models import Q, F, Sum, Count, Avg
from decimal import Decimal
from uuid import uuid4
from enum import Enum

User = get_user_model()


class RevenueStreamType(models.TextChoices):
    SUBSCRIPTION = 'subscription', 'Subscription'
    AI_CREDITS = 'ai_credits', 'AI Credits'
    ONE_TIME = 'one_time', 'One-time Payment'
    ENTERPRISE = 'enterprise', 'Enterprise Contract'
    USAGE_BASED = 'usage_based', 'Usage-based'


class SubscriptionTier(models.TextChoices):
    STARTER = 'starter', 'Starter'
    PRO = 'pro', 'Pro'
    ENTERPRISE = 'enterprise', 'Enterprise'
    FREE_TRIAL = 'free_trial', 'Free Trial'


class EventType(models.TextChoices):
    # Customer Events
    SIGNUP = 'signup', 'User Signup'
    SUBSCRIPTION_STARTED = 'subscription_started', 'Subscription Started'
    SUBSCRIPTION_CANCELED = 'subscription_canceled', 'Subscription Canceled'
    SUBSCRIPTION_RENEWED = 'subscription_renewed', 'Subscription Renewed'
    SUBSCRIPTION_UPGRADED = 'subscription_upgraded', 'Subscription Upgraded'
    SUBSCRIPTION_DOWNGRADED = 'subscription_downgraded', 'Subscription Downgraded'
    
    # Payment Events
    PAYMENT_SUCCESS = 'payment_success', 'Payment Success'
    PAYMENT_FAILED = 'payment_failed', 'Payment Failed'
    REFUND_ISSUED = 'refund_issued', 'Refund Issued'
    INVOICE_PAID = 'invoice_paid', 'Invoice Paid'
    
    # Usage Events
    AI_REVIEW_COMPLETED = 'ai_review_completed', 'AI Review Completed'
    DOCUMENT_GENERATED = 'document_generated', 'Document Generated'
    PDF_EXPORTED = 'pdf_exported', 'PDF Exported'
    
    # Customer Lifecycle
    TRIAL_STARTED = 'trial_started', 'Trial Started'
    TRIAL_ENDED = 'trial_ended', 'Trial Ended'
    CHURNED = 'churned', 'Customer Churned'
    REACTIVATED = 'reactivated', 'Customer Reactivated'
    
    # Engagement
    LOGIN = 'login', 'User Login'
    FEATURE_USED = 'feature_used', 'Feature Used'
    SUPPORT_TICKET = 'support_ticket', 'Support Ticket'


class RevenueSnapshot(models.Model):
    """Daily snapshot of revenue metrics for analytics"""
    
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    date = models.DateField(unique=True, db_index=True)
    
    # Core metrics
    mrr = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    arr = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    ltv = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cac = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # Customer metrics
    total_customers = models.IntegerField(default=0)
    active_customers = models.IntegerField(default=0)
    new_customers = models.IntegerField(default=0)
    churned_customers = models.IntegerField(default=0)
    trial_customers = models.IntegerField(default=0)
    
    # Revenue breakdown by tier
    mrr_starter = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    mrr_pro = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    mrr_enterprise = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # Additional metrics
    churn_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.0000'))
    retention_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('100.0000'))
    average_revenue_per_user = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # AI usage metrics
    total_ai_reviews = models.IntegerField(default=0)
    total_documents_generated = models.IntegerField(default=0)
    ai_credits_used = models.IntegerField(default=0)
    
    # Quality metrics
    data_completeness_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'analytics_revenue_snapshots'
        indexes = [
            models.Index(fields=['-date']),
            models.Index(fields=['active_customers', 'mrr']),
            models.Index(fields=['churn_rate']),
        ]
        ordering = ['-date']
        verbose_name_plural = 'Revenue Snapshots'
    
    def __str__(self):
        return f"Snapshot {self.date.isoformat()} - MRR: ${self.mrr}"
    
    def save(self, *args, **kwargs):
        """Auto-calculate derived metrics before saving"""
        if self.active_customers > 0:
            self.average_revenue_per_user = self.mrr / Decimal(str(self.active_customers))
        
        # Ensure consistency with tier breakdowns
        total_tier_mrr = self.mrr_starter + self.mrr_pro + self.mrr_enterprise
        if total_tier_mrr != self.mrr:
            self.mrr = total_tier_mrr
        
        super().save(*args, **kwargs)
    
    def clean(self):
        """Validate data consistency"""
        if self.churn_rate < 0 or self.churn_rate > 100:
            raise ValidationError({'churn_rate': 'Churn rate must be between 0 and 100'})
        if self.retention_rate < 0 or self.retention_rate > 100:
            raise ValidationError({'retention_rate': 'Retention rate must be between 0 and 100'})
        if self.churned_customers > self.active_customers + self.churned_customers:
            raise ValidationError({'churned_customers': 'Churned customers cannot exceed total customers'})


class EventLog(models.Model):
    """Track all business events for analytics and audit trail"""
    
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='analytics_events')
    company_id = models.UUIDField(null=True, blank=True, db_index=True)
    
    event_type = models.CharField(max_length=50, choices=EventType.choices, db_index=True)
    event_name = models.CharField(max_length=100)
    
    # Event metadata
    metadata = models.JSONField(default=dict, help_text="Flexible event data")
    value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    # Session and context
    session_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    referrer = models.URLField(blank=True)
    
    # Technical tracking
    request_path = models.CharField(max_length=500, blank=True)
    response_time_ms = models.IntegerField(null=True)
    status_code = models.IntegerField(null=True)
    
    # Feature flags
    is_bot = models.BooleanField(default=False)
    is_test = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    
    class Meta:
        db_table = 'analytics_event_logs'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['event_type', 'created_at']),
            models.Index(fields=['company_id', 'event_type']),
            models.Index(fields=['created_at', 'event_type']),
            models.Index(fields=['session_id']),
        ]
        ordering = ['-created_at']
        verbose_name_plural = 'Event Logs'
    
    def __str__(self):
        return f"{self.event_type} - {self.user} - {self.created_at}"
    
    @classmethod
    def track_event(cls, user, event_type, **kwargs):
        """Factory method to easily track events"""
        event = cls.objects.create(
            user=user,
            event_type=event_type,
            event_name=event_type.label,
            metadata=kwargs.get('metadata', {}),
            value=kwargs.get('value'),
            session_id=kwargs.get('session_id'),
            ip_address=kwargs.get('ip_address'),
            user_agent=kwargs.get('user_agent', ''),
            referrer=kwargs.get('referrer', ''),
            request_path=kwargs.get('request_path', ''),
            response_time_ms=kwargs.get('response_time_ms'),
            status_code=kwargs.get('status_code'),
            is_bot=kwargs.get('is_bot', False),
            is_test=kwargs.get('is_test', False),
        )
        return event


class MRRSnapshot(models.Model):
    """Real-time MRR tracking with change history"""
    
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mrr_history')
    
    subscription_tier = models.CharField(max_length=20, choices=SubscriptionTier.choices)
    monthly_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Snapshot period
    period_start = models.DateField(db_index=True)
    period_end = models.DateField(db_index=True)
    
    # Change tracking
    previous_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    change_reason = models.CharField(max_length=200, blank=True)
    change_type = models.CharField(max_length=20, choices=[
        ('new', 'New Customer'),
        ('upgrade', 'Upgrade'),
        ('downgrade', 'Downgrade'),
        ('renewal', 'Renewal'),
        ('cancellation', 'Cancellation'),
    ])
    
    # Status
    is_active = models.BooleanField(default=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'analytics_mrr_snapshots'
        indexes = [
            models.Index(fields=['user', 'period_start']),
            models.Index(fields=['period_start', 'subscription_tier']),
            models.Index(fields=['is_active', 'canceled_at']),
        ]
        ordering = ['-period_start']
        unique_together = [['user', 'period_start']]
    
    def __str__(self):
        return f"{self.user} - {self.period_start} - ${self.monthly_amount}"


class CohortAnalysis(models.Model):
    """Track user cohorts for retention analysis"""
    
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    cohort_name = models.CharField(max_length=100)
    cohort_date = models.DateField(db_index=True)
    cohort_type = models.CharField(max_length=50, choices=[
        ('signup_week', 'Signup Week'),
        ('signup_month', 'Signup Month'),
        ('signup_quarter', 'Signup Quarter'),
        ('acquisition_source', 'Acquisition Source'),
    ])
    
    # Cohort metrics over time
    period_0_users = models.IntegerField(default=0)  # Initial cohort size
    period_1_retained = models.IntegerField(default=0)
    period_2_retained = models.IntegerField(default=0)
    period_3_retained = models.IntegerField(default=0)
    period_4_retained = models.IntegerField(default=0)
    period_5_retained = models.IntegerField(default=0)
    period_6_retained = models.IntegerField(default=0)
    period_12_retained = models.IntegerField(default=0)
    
    # Revenue contribution
    total_revenue_generated = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'analytics_cohorts'
        indexes = [
            models.Index(fields=['cohort_date', 'cohort_type']),
            models.Index(fields=['cohort_name']),
        ]
        ordering = ['-cohort_date']
    
    @property
    def retention_rate_period_1(self):
        if self.period_0_users > 0:
            return (self.period_1_retained / self.period_0_users) * 100
        return 0.0
    
    @property
    def retention_rate_period_3(self):
        if self.period_0_users > 0:
            return (self.period_3_retained / self.period_0_users) * 100
        return 0.0


class RevenueAlert(models.Model):
    """Automated alerts for revenue anomalies and milestones"""
    
    class AlertLevel(models.TextChoices):
        INFO = 'info', 'Info'
        WARNING = 'warning', 'Warning'
        CRITICAL = 'critical', 'Critical'
        SUCCESS = 'success', 'Success'
    
    class AlertType(models.TextChoices):
        MRR_MILESTONE = 'mrr_milestone', 'MRR Milestone Reached'
        CHURN_SPIKE = 'churn_spike', 'Churn Rate Spike'
        PAYMENT_FAILURE = 'payment_failure', 'Payment Failure Spike'
        UPGRADE_BOOST = 'upgrade_boost', 'Upgrade Activity Spike'
        TRIAL_CONVERSION = 'trial_conversion', 'Trial Conversion Milestone'
    
    alert_type = models.CharField(max_length=50, choices=AlertType.choices)
    alert_level = models.CharField(max_length=20, choices=AlertLevel.choices, default=AlertLevel.INFO)
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    
    # Metrics at time of alert
    current_value = models.DecimalField(max_digits=15, decimal_places=2, null=True)
    previous_value = models.DecimalField(max_digits=15, decimal_places=2, null=True)
    threshold = models.DecimalField(max_digits=15, decimal_places=2, null=True)
    
    # Status tracking
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_alerts')
    
    # Notifications
    notification_sent = models.BooleanField(default=False)
    notification_channel = models.CharField(max_length=50, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'analytics_alerts'
        indexes = [
            models.Index(fields=['alert_type', 'created_at']),
            models.Index(fields=['alert_level', 'is_resolved']),
            models.Index(fields=['-created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_alert_level_display()}: {self.title}"