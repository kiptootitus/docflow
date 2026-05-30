# analytics/aggregators.py
from decimal import Decimal
from django.db.models import Sum, Count, Q, Avg, F
from django.utils import timezone
from datetime import timedelta, date
from typing import Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass
from collections import defaultdict

from .models import RevenueSnapshot, EventLog, MRRSnapshot, EventType, SubscriptionTier
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)


@dataclass
class MRRMetrics:
    """MRR Metrics Data Class"""
    total_mrr: Decimal
    mrr_starter: Decimal
    mrr_pro: Decimal
    mrr_enterprise: Decimal
    mrr_growth_rate: float
    new_mrr_added: Decimal
    churned_mrr: Decimal
    expansion_mrr: Decimal
    contraction_mrr: Decimal
    net_new_mrr: Decimal
    
    @property
    def mrr_breakdown(self) -> Dict:
        return {
            'starter': float(self.mrr_starter),
            'pro': float(self.mrr_pro),
            'enterprise': float(self.mrr_enterprise),
        }


@dataclass
class ChurnMetrics:
    """Churn and Retention Metrics"""
    logo_churn_rate: float
    revenue_churn_rate: float
    net_revenue_churn: float
    gross_revenue_churn: float
    customer_churned_count: int
    mrr_churned: Decimal
    customers_at_start: int
    customers_at_end: int
    
    @property
    def retention_rate(self) -> float:
        return 100 - self.logo_churn_rate


class RevenueAggregator:
    """Enterprise-grade revenue aggregation and analytics"""
    
    def __init__(self, company_id: Optional[str] = None):
        self.company_id = company_id
        self._cache = {}
    
    def calculate_current_mrr(self) -> MRRMetrics:
        """Calculate current MRR across all active subscriptions"""
        base_qs = MRRSnapshot.objects.filter(
            is_active=True,
            period_start__lte=timezone.now().date(),
            period_end__gte=timezone.now().date()
        )
        
        if self.company_id:
            base_qs = base_qs.filter(user__company_id=self.company_id)
        
        # Calculate MRR by tier
        mrr_starter = base_qs.filter(subscription_tier=SubscriptionTier.STARTER).aggregate(
            total=Sum('monthly_amount')
        )['total'] or Decimal('0.00')
        
        mrr_pro = base_qs.filter(subscription_tier=SubscriptionTier.PRO).aggregate(
            total=Sum('monthly_amount')
        )['total'] or Decimal('0.00')
        
        mrr_enterprise = base_qs.filter(subscription_tier=SubscriptionTier.ENTERPRISE).aggregate(
            total=Sum('monthly_amount')
        )['total'] or Decimal('0.00')
        
        total_mrr = mrr_starter + mrr_pro + mrr_enterprise
        
        # Calculate MRR movements
        previous_month = timezone.now().date() - timedelta(days=30)
        previous_mrr = self._get_mrr_at_date(previous_month)
        
        mrr_growth_rate = 0.0
        if previous_mrr > 0:
            mrr_growth_rate = float((total_mrr - previous_mrr) / previous_mrr * 100)
        
        # Calculate MRR components
        new_mrr = self._calculate_new_mrr(last_n_days=30)
        churned_mrr = self._calculate_churned_mrr(last_n_days=30)
        expansion_mrr = self._calculate_expansion_mrr(last_n_days=30)
        contraction_mrr = self._calculate_contraction_mrr(last_n_days=30)
        
        net_new_mrr = new_mrr + expansion_mrr - churned_mrr - contraction_mrr
        
        return MRRMetrics(
            total_mrr=total_mrr,
            mrr_starter=mrr_starter,
            mrr_pro=mrr_pro,
            mrr_enterprise=mrr_enterprise,
            mrr_growth_rate=mrr_growth_rate,
            new_mrr_added=new_mrr,
            churned_mrr=churned_mrr,
            expansion_mrr=expansion_mrr,
            contraction_mrr=contraction_mrr,
            net_new_mrr=net_new_mrr,
        )
    
    def calculate_churn_metrics(self, period_days: int = 30) -> ChurnMetrics:
        """Calculate comprehensive churn metrics"""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=period_days)
        
        # Customers at period start
        customers_start = self._get_active_customers_at_date(start_date)
        customers_end = self._get_active_customers_at_date(end_date)
        
        # Calculate churned customers
        churned_customers = self._get_churned_customers(start_date, end_date)
        churned_count = churned_customers.count()
        
        logo_churn_rate = (churned_count / customers_start * 100) if customers_start > 0 else 0
        
        # Calculate churned MRR
        mrr_at_start = self._get_mrr_at_date(start_date)
        mrr_churned = self._calculate_churned_mrr(period_days=period_days)
        mrr_at_end = self._get_mrr_at_date(end_date)
        
        revenue_churn_rate = (float(mrr_churned) / float(mrr_at_start) * 100) if mrr_at_start > 0 else 0
        
        # Net revenue churn (includes expansion)
        expansion_mrr = self._calculate_expansion_mrr(period_days=period_days)
        net_revenue_churn = ((float(mrr_churned) - float(expansion_mrr)) / float(mrr_at_start) * 100) if mrr_at_start > 0 else 0
        
        # Gross revenue churn
        gross_revenue_churn = float(mrr_churned) / float(mrr_at_start) * 100 if mrr_at_start > 0 else 0
        
        return ChurnMetrics(
            logo_churn_rate=logo_churn_rate,
            revenue_churn_rate=revenue_churn_rate,
            net_revenue_churn=net_revenue_churn,
            gross_revenue_churn=gross_revenue_churn,
            customer_churned_count=churned_count,
            mrr_churned=mrr_churned,
            customers_at_start=customers_start,
            customers_at_end=customers_end,
        )
    
    def calculate_customer_ltv(self, cohort_months: int = 12) -> Decimal:
        """Calculate Customer Lifetime Value (LTV)"""
        # Get average monthly revenue per customer
        active_customers = self._get_active_customers()
        if active_customers == 0:
            return Decimal('0.00')
        
        current_mrr = self.calculate_current_mrr().total_mrr
        avg_monthly_revenue = current_mrr / Decimal(str(active_customers))
        
        # Get average customer lifespan in months
        avg_lifespan_months = self._calculate_average_customer_lifespan()
        
        # Calculate LTV: ARPU * Customer Lifespan
        ltv = avg_monthly_revenue * Decimal(str(avg_lifespan_months))
        
        return ltv
    
    def calculate_cohort_retention(self, cohort_date: date, cohort_type: str = 'signup_week') -> Dict:
        """Calculate retention metrics for a specific cohort"""
        if cohort_type == 'signup_week':
            end_date = cohort_date + timedelta(days=7)
        elif cohort_type == 'signup_month':
            end_date = cohort_date + timedelta(days=30)
        else:
            end_date = cohort_date + timedelta(days=90)
        
        # Get customers who signed up in cohort period
        cohort_customers = User.objects.filter(
            date_joined__date__gte=cohort_date,
            date_joined__date__lt=end_date
        )
        
        if self.company_id:
            cohort_customers = cohort_customers.filter(company_id=self.company_id)
        
        cohort_size = cohort_customers.count()
        
        if cohort_size == 0:
            return {'cohort_size': 0, 'retention': []}
        
        # Calculate retention over time (months 1-12)
        retention_data = []
        for month in range(1, 13):
            period_start = cohort_date + timedelta(days=30 * month)
            period_end = period_start + timedelta(days=30)
            
            retained = cohort_customers.filter(
                mrr_snapshots__period_start__lte=period_end,
                mrr_snapshots__period_end__gte=period_start,
                mrr_snapshots__is_active=True
            ).distinct().count()
            
            retention_rate = (retained / cohort_size) * 100
            retention_data.append({
                'month': month,
                'retained_customers': retained,
                'retention_rate': round(retention_rate, 2),
            })
        
        return {
            'cohort_size': cohort_size,
            'cohort_period': f"{cohort_date} to {end_date}",
            'retention': retention_data,
        }
    
    def calculate_annual_recurring_revenue(self) -> Decimal:
        """Calculate Annual Recurring Revenue (ARR)"""
        current_mrr = self.calculate_current_mrr().total_mrr
        return current_mrr * Decimal('12.00')
    
    def generate_daily_snapshot(self, target_date: date = None) -> RevenueSnapshot:
        """Generate a complete revenue snapshot for a given date"""
        if not target_date:
            target_date = timezone.now().date()
        
        mrr_metrics = self.calculate_current_mrr()
        churn_metrics = self.calculate_churn_metrics()
        
        # Get daily metrics
        active_customers = self._get_active_customers_at_date(target_date)
        new_customers = self._get_new_customers_on_date(target_date)
        churned_customers = self._get_churned_customers_on_date(target_date)
        trial_customers = self._get_trial_customers_at_date(target_date)
        
        # Get AI usage metrics
        ai_metrics = self._get_ai_usage_metrics(target_date)
        
        # Calculate data completeness (for data quality monitoring)
        completeness_score = self._calculate_data_completeness(target_date)
        
        snapshot, created = RevenueSnapshot.objects.update_or_create(
            date=target_date,
            defaults={
                'mrr': mrr_metrics.total_mrr,
                'arr': self.calculate_annual_recurring_revenue(),
                'ltv': self.calculate_customer_ltv(),
                'total_customers': self._get_total_customers(),
                'active_customers': active_customers,
                'new_customers': new_customers,
                'churned_customers': churned_customers,
                'trial_customers': trial_customers,
                'mrr_starter': mrr_metrics.mrr_starter,
                'mrr_pro': mrr_metrics.mrr_pro,
                'mrr_enterprise': mrr_metrics.mrr_enterprise,
                'churn_rate': Decimal(str(churn_metrics.logo_churn_rate)),
                'retention_rate': Decimal(str(churn_metrics.retention_rate)),
                'average_revenue_per_user': self._calculate_arpu(),
                'total_ai_reviews': ai_metrics.get('total_reviews', 0),
                'total_documents_generated': ai_metrics.get('total_documents', 0),
                'ai_credits_used': ai_metrics.get('credits_used', 0),
                'data_completeness_score': completeness_score,
            }
        )
        
        return snapshot
    
    # Private helper methods
    def _get_mrr_at_date(self, target_date: date) -> Decimal:
        """Get total MRR at a specific date"""
        mrr_snapshots = MRRSnapshot.objects.filter(
            period_start__lte=target_date,
            period_end__gte=target_date,
            is_active=True
        )
        
        if self.company_id:
            mrr_snapshots = mrr_snapshots.filter(user__company_id=self.company_id)
        
        total = mrr_snapshots.aggregate(total=Sum('monthly_amount'))['total']
        return total or Decimal('0.00')
    
    def _get_active_customers_at_date(self, target_date: date) -> int:
        """Get number of active customers at a specific date"""
        return MRRSnapshot.objects.filter(
            period_start__lte=target_date,
            period_end__gte=target_date,
            is_active=True
        ).values('user').distinct().count()
    
    def _get_active_customers(self) -> int:
        """Get current active customers"""
        return self._get_active_customers_at_date(timezone.now().date())
    
    def _get_total_customers(self) -> int:
        """Get total customers (all time)"""
        qs = User.objects.filter(is_active=True)
        if self.company_id:
            qs = qs.filter(company_id=self.company_id)
        return qs.count()
    
    def _get_new_customers_on_date(self, target_date: date) -> int:
        """Get number of new customers on a specific date"""
        return User.objects.filter(
            date_joined__date=target_date
        ).count()
    
    def _get_churned_customers_on_date(self, target_date: date) -> int:
        """Get number of customers who churned on a specific date"""
        return EventLog.objects.filter(
            event_type=EventType.CHURNED,
            created_at__date=target_date
        ).values('user').distinct().count()
    
    def _get_churned_customers(self, start_date: date, end_date: date):
        """Get customers who churned in date range"""
        return EventLog.objects.filter(
            event_type=EventType.CHURNED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).values('user').distinct()
    
    def _get_trial_customers_at_date(self, target_date: date) -> int:
        """Get number of customers in trial period at a specific date"""
        return MRRSnapshot.objects.filter(
            subscription_tier=SubscriptionTier.FREE_TRIAL,
            period_start__lte=target_date,
            period_end__gte=target_date,
            is_active=True
        ).values('user').distinct().count()
    
    def _get_ai_usage_metrics(self, target_date: date) -> Dict:
        """Get AI usage metrics for a specific date"""
        events = EventLog.objects.filter(
            created_at__date=target_date,
            event_type__in=[EventType.AI_REVIEW_COMPLETED, EventType.DOCUMENT_GENERATED]
        )
        
        return {
            'total_reviews': events.filter(event_type=EventType.AI_REVIEW_COMPLETED).count(),
            'total_documents': events.filter(event_type=EventType.DOCUMENT_GENERATED).count(),
            'credits_used': events.aggregate(total=Sum('value'))['total'] or 0,
        }
    
    def _calculate_arpu(self) -> Decimal:
        """Calculate Average Revenue Per User"""
        mrr = self.calculate_current_mrr().total_mrr
        active_users = self._get_active_customers()
        
        if active_users == 0:
            return Decimal('0.00')
        
        return mrr / Decimal(str(active_users))
    
    def _calculate_average_customer_lifespan(self) -> float:
        """Calculate average customer lifespan in months"""
        # Get all churned customers
        churned_users = EventLog.objects.filter(
            event_type=EventType.CHURNED
        ).values('user').distinct()
        
        lifespans = []
        for churn_event in EventLog.objects.filter(
            event_type=EventType.CHURNED,
            user__in=churned_users
        ):
            # Get signup date
            signup_date = churn_event.user.date_joined
            
            # Calculate lifespan in months
            months = (churn_event.created_at - signup_date).days / 30.44
            if months > 0:
                lifespans.append(months)
        
        if not lifespans:
            return 24.0  # Default assumption for new SaaS
        
        return sum(lifespans) / len(lifespans)
    
    def _calculate_new_mrr(self, last_n_days: int = 30) -> Decimal:
        """Calculate MRR from new customers in period"""
        start_date = timezone.now().date() - timedelta(days=last_n_days)
        
        new_subs = MRRSnapshot.objects.filter(
            change_type='new',
            period_start__gte=start_date,
            is_active=True
        )
        
        if self.company_id:
            new_subs = new_subs.filter(user__company_id=self.company_id)
        
        total = new_subs.aggregate(total=Sum('monthly_amount'))['total']
        return total or Decimal('0.00')
    
    def _calculate_churned_mrr(self, last_n_days: int = 30) -> Decimal:
        """Calculate MRR lost from churn in period"""
        start_date = timezone.now().date() - timedelta(days=last_n_days)
        
        churned_subs = MRRSnapshot.objects.filter(
            change_type='cancellation',
            period_start__gte=start_date,
            is_active=False
        )
        
        if self.company_id:
            churned_subs = churned_subs.filter(user__company_id=self.company_id)
        
        total = churned_subs.aggregate(total=Sum('monthly_amount'))['total']
        return total or Decimal('0.00')
    
    def _calculate_expansion_mrr(self, last_n_days: int = 30) -> Decimal:
        """Calculate MRR gained from upgrades in period"""
        start_date = timezone.now().date() - timedelta(days=last_n_days)
        
        upgrades = MRRSnapshot.objects.filter(
            change_type='upgrade',
            period_start__gte=start_date,
            is_active=True
        )
        
        if self.company_id:
            upgrades = upgrades.filter(user__company_id=self.company_id)
        
        # Calculate MRR uplift from upgrades
        total_uplift = Decimal('0.00')
        for upgrade in upgrades:
            if upgrade.previous_amount:
                uplift = upgrade.monthly_amount - upgrade.previous_amount
                if uplift > 0:
                    total_uplift += uplift
        
        return total_uplift
    
    def _calculate_contraction_mrr(self, last_n_days: int = 30) -> Decimal:
        """Calculate MRR lost from downgrades in period"""
        start_date = timezone.now().date() - timedelta(days=last_n_days)
        
        downgrades = MRRSnapshot.objects.filter(
            change_type='downgrade',
            period_start__gte=start_date,
            is_active=True
        )
        
        if self.company_id:
            downgrades = downgrades.filter(user__company_id=self.company_id)
        
        # Calculate MRR reduction from downgrades
        total_reduction = Decimal('0.00')
        for downgrade in downgrades:
            if downgrade.previous_amount:
                reduction = downgrade.previous_amount - downgrade.monthly_amount
                if reduction > 0:
                    total_reduction += reduction
        
        return total_reduction
    
    def _calculate_data_completeness(self, target_date: date) -> float:
        """Calculate data completeness score for quality monitoring"""
        required_metrics = [
            self._get_active_customers_at_date(target_date) > 0,
            self.calculate_current_mrr().total_mrr > 0,
            EventLog.objects.filter(created_at__date=target_date).exists(),
        ]
        
        completeness = (sum(required_metrics) / len(required_metrics)) * 100
        return completeness
    
    def get_revenue_trends(self, days: int = 30) -> List[Dict]:
        """Get daily revenue trends for the last N days"""
        trends = []
        
        for i in range(days):
            target_date = timezone.now().date() - timedelta(days=i)
            snapshot = self.generate_daily_snapshot(target_date)
            
            trends.append({
                'date': target_date.isoformat(),
                'mrr': float(snapshot.mrr),
                'active_customers': snapshot.active_customers,
                'new_customers': snapshot.new_customers,
                'churned_customers': snapshot.churned_customers,
                'churn_rate': float(snapshot.churn_rate),
                'arpu': float(snapshot.average_revenue_per_user),
            })
        
        return trends
