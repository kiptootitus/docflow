# analytics/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q
from django.core.cache import cache
from datetime import timedelta, date
from decimal import Decimal
import logging
from typing import Dict, Any

from .models import RevenueSnapshot, EventLog, MRRSnapshot, RevenueAlert, EventType
from .aggregators import RevenueAggregator, MRRMetrics, ChurnMetrics
from .serializers import (
    RevenueSnapshotSerializer, EventLogSerializer, MRRSnapshotSerializer,
    RevenueAlertSerializer, DashboardMetricsSerializer, MRRAnalysisSerializer,
    CohortAnalysisSerializer, RevenueTrendsSerializer
)
from .permissions import IsAnalyticsManager, IsCompanyAdmin
from .tasks import generate_daily_snapshots, check_revenue_alerts

logger = logging.getLogger(__name__)


class AnalyticsDashboardViewSet(viewsets.GenericViewSet):
    """Enterprise analytics dashboard endpoints"""
    
    permission_classes = [IsAuthenticated, IsAnalyticsManager]
    authentication_classes = [TokenAuthentication]
    
    def get_company_id(self):
        """Get company ID from request user"""
        return getattr(self.request.user, 'company_id', None)
    
    @action(detail=False, methods=['get'])
    def metrics(self, request):
        """Get current dashboard metrics"""
        company_id = self.get_company_id()
        aggregator = RevenueAggregator(company_id=company_id)
        
        # Try to get from cache (30 second TTL for real-time data)
        cache_key = f"dashboard_metrics_{company_id}"
        metrics = cache.get(cache_key)
        
        if not metrics:
            mrr_metrics = aggregator.calculate_current_mrr()
            churn_metrics = aggregator.calculate_churn_metrics()
            arr = aggregator.calculate_annual_recurring_revenue()
            ltv = aggregator.calculate_customer_ltv()
            
            metrics = {
                'mrr': float(mrr_metrics.total_mrr),
                'arr': float(arr),
                'ltv': float(ltv),
                'churn_rate': churn_metrics.logo_churn_rate,
                'revenue_churn_rate': churn_metrics.revenue_churn_rate,
                'active_customers': churn_metrics.customers_at_end,
                'new_customers_last_30d': self._get_new_customers_count(30),
                'churned_customers_last_30d': churn_metrics.customer_churned_count,
                'arpu': float(aggregator._calculate_arpu()),
                'mrr_breakdown': mrr_metrics.mrr_breakdown,
                'growth_rate': mrr_metrics.mrr_growth_rate,
            }
            
            cache.set(cache_key, metrics, 30)  # Cache for 30 seconds
        
        serializer = DashboardMetricsSerializer(data=metrics)
        serializer.is_valid(raise_exception=True)
        
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def revenue_trends(self, request):
        """Get revenue trends over time"""
        days = int(request.query_params.get('days', 30))
        company_id = self.get_company_id()
        
        aggregator = RevenueAggregator(company_id=company_id)
        trends = aggregator.get_revenue_trends(days=days)
        
        serializer = RevenueTrendsSerializer(data={'trends': trends})
        serializer.is_valid(raise_exception=True)
        
        return Response(trends)
    
    @action(detail=False, methods=['get'])
    def mrr_analysis(self, request):
        """Detailed MRR analysis including components"""
        company_id = self.get_company_id()
        aggregator = RevenueAggregator(company_id=company_id)
        
        mrr_metrics = aggregator.calculate_current_mrr()
        
        analysis = {
            'total_mrr': float(mrr_metrics.total_mrr),
            'new_mrr': float(mrr_metrics.new_mrr_added),
            'churned_mrr': float(mrr_metrics.churned_mrr),
            'expansion_mrr': float(mrr_metrics.expansion_mrr),
            'contraction_mrr': float(mrr_metrics.contraction_mrr),
            'net_new_mrr': float(mrr_metrics.net_new_mrr),
            'growth_rate': mrr_metrics.mrr_growth_rate,
            'by_tier': {
                'starter': float(mrr_metrics.mrr_starter),
                'pro': float(mrr_metrics.mrr_pro),
                'enterprise': float(mrr_metrics.mrr_enterprise),
            },
            'mrr_percentage_by_tier': self._calculate_tier_percentages(mrr_metrics),
        }
        
        serializer = MRRAnalysisSerializer(data=analysis)
        serializer.is_valid(raise_exception=True)
        
        return Response(analysis)
    
    @action(detail=False, methods=['get'])
    def churn_analysis(self, request):
        """Detailed churn and retention analysis"""
        company_id = self.get_company_id()
        aggregator = RevenueAggregator(company_id=company_id)
        
        churn_metrics = aggregator.calculate_churn_metrics()
        
        # Get churn by cohort
        churn_by_tier = self._get_churn_by_tier()
        churn_by_plan_duration = self._get_churn_by_plan_duration()
        
        analysis = {
            'logo_churn_rate': churn_metrics.logo_churn_rate,
            'revenue_churn_rate': churn_metrics.revenue_churn_rate,
            'net_revenue_churn': churn_metrics.net_revenue_churn,
            'gross_revenue_churn': churn_metrics.gross_revenue_churn,
            'customer_churned_count': churn_metrics.customer_churned_count,
            'mrr_churned': float(churn_metrics.mrr_churned),
            'customers_at_start': churn_metrics.customers_at_start,
            'customers_at_end': churn_metrics.customers_at_end,
            'retention_rate': churn_metrics.retention_rate,
            'churn_by_tier': churn_by_tier,
            'churn_by_plan_duration': churn_by_plan_duration,
        }
        
        return Response(analysis)
    
    @action(detail=False, methods=['get'])
    def cohort_analysis(self, request):
        """Cohort-based retention analysis"""
        company_id = self.get_company_id()
        aggregator = RevenueAggregator(company_id=company_id)
        
        # Get cohorts for last 6 months
        cohorts = []
        today = timezone.now().date()
        
        for i in range(6):
            cohort_date = today.replace(day=1) - timedelta(days=30 * i)
            cohort_data = aggregator.calculate_cohort_retention(
                cohort_date=cohort_date,
                cohort_type='signup_month'
            )
            cohorts.append({
                'cohort_month': cohort_date.strftime('%Y-%m'),
                'cohort_size': cohort_data['cohort_size'],
                'retention_rates': cohort_data['retention'],
            })
        
        serializer = CohortAnalysisSerializer(data={'cohorts': cohorts})
        serializer.is_valid(raise_exception=True)
        
        return Response(cohorts)
    
    @action(detail=False, methods=['get'])
    def alerts(self, request):
        """Get revenue alerts and anomalies"""
        company_id = self.get_company_id()
        
        alerts = RevenueAlert.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=7),
            is_resolved=False
        ).order_by('-created_at')
        
        if company_id:
            alerts = alerts.filter(metadata__company_id=str(company_id))
        
        serializer = RevenueAlertSerializer(alerts, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def refresh_snapshot(self, request):
        """Manually trigger daily snapshot generation"""
        company_id = self.get_company_id()
        
        # Trigger async task
        generate_daily_snapshots.delay()
        
        return Response({
            'status': 'success',
            'message': 'Snapshot generation triggered',
            'timestamp': timezone.now().isoformat()
        })
    
    @action(detail=False, methods=['get'])
    def events_summary(self, request):
        """Get summary of key business events"""
        days = int(request.query_params.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        company_id = self.get_company_id()
        
        events_qs = EventLog.objects.filter(
            created_at__gte=start_date
        )
        
        if company_id:
            events_qs = events_qs.filter(company_id=company_id)
        
        # Aggregate events by type
        events_by_type = events_qs.values('event_type').annotate(
            count=Count('id'),
            total_value=Sum('value')
        )
        
        # Get daily event counts
        daily_events = events_qs.extra(
            {'date': "date(created_at)"}
        ).values('date', 'event_type').annotate(
            count=Count('id')
        ).order_by('-date')
        
        return Response({
            'events_by_type': list(events_by_type),
            'daily_events': list(daily_events),
            'total_events': events_qs.count(),
            'period_days': days,
        })
    
    @action(detail=False, methods=['get'])
    def revenue_forecast(self, request):
        """Generate revenue forecast based on historical trends"""
        company_id = self.get_company_id()
        aggregator = RevenueAggregator(company_id=company_id)
        
        # Get historical trends (last 90 days)
        trends = aggregator.get_revenue_trends(days=90)
        
        if not trends:
            return Response({'error': 'Insufficient data for forecasting'}, status=400)
        
        # Calculate growth rate
        current_mrr = trends[0]['mrr']
        historical_mrr = [t['mrr'] for t in trends]
        
        # Simple linear regression for forecast
        forecast_months = 3
        forecast = []
        
        for month in range(1, forecast_months + 1):
            # Use average growth rate from last 30 days
            if len(historical_mrr) >= 30:
                recent_growth = (historical_mrr[0] - historical_mrr[29]) / historical_mrr[29] if historical_mrr[29] > 0 else 0
                projected_mrr = current_mrr * (1 + recent_growth * month)
            else:
                projected_mrr = current_mrr
            
            forecast.append({
                'month': month,
                'projected_mrr': round(projected_mrr, 2),
                'confidence_lower': round(projected_mrr * 0.85, 2),
                'confidence_upper': round(projected_mrr * 1.15, 2),
            })
        
        return Response({
            'current_mrr': current_mrr,
            'forecast': forecast,
            'forecast_basis': '30-day average growth rate',
        })
    
    # Private helper methods
    def _get_new_customers_count(self, days: int) -> int:
        """Get number of new customers in last N days"""
        start_date = timezone.now() - timedelta(days=days)
        
        return EventLog.objects.filter(
            event_type=EventType.SIGNUP,
            created_at__gte=start_date
        ).values('user').distinct().count()
    
    def _calculate_tier_percentages(self, mrr_metrics: MRRMetrics) -> Dict:
        """Calculate percentage breakdown by tier"""
        total = float(mrr_metrics.total_mrr)
        
        if total == 0:
            return {'starter': 0, 'pro': 0, 'enterprise': 0}
        
        return {
            'starter': round(float(mrr_metrics.mrr_starter) / total * 100, 2),
            'pro': round(float(mrr_metrics.mrr_pro) / total * 100, 2),
            'enterprise': round(float(mrr_metrics.mrr_enterprise) / total * 100, 2),
        }
    
    def _get_churn_by_tier(self) -> Dict:
        """Get churn rate breakdown by subscription tier"""
        tiers = ['starter', 'pro', 'enterprise']
        churn_by_tier = {}
        
        for tier in tiers:
            churned = EventLog.objects.filter(
                event_type=EventType.CHURNED,
                metadata__subscription_tier=tier,
                created_at__gte=timezone.now() - timedelta(days=30)
            ).count()
            
            total = MRRSnapshot.objects.filter(
                subscription_tier=tier,
                is_active=True
            ).values('user').distinct().count()
            
            churn_rate = (churned / total * 100) if total > 0 else 0
            churn_by_tier[tier] = round(churn_rate, 2)
        
        return churn_by_tier
    
    def _get_churn_by_plan_duration(self) -> Dict:
        """Get churn rate by plan duration"""
        durations = {
            'monthly': 'monthly',
            'annual': 'annual',
        }
        
        churn_by_duration = {}
        
        for duration_type, duration_key in durations.items():
            churned = EventLog.objects.filter(
                event_type=EventType.CHURNED,
                metadata__billing_period=duration_key,
                created_at__gte=timezone.now() - timedelta(days=30)
            ).count()
            
            total = MRRSnapshot.objects.filter(
                metadata__billing_period=duration_key,
                is_active=True
            ).values('user').distinct().count()
            
            churn_rate = (churned / total * 100) if total > 0 else 0
            churn_by_duration[duration_type] = round(churn_rate, 2)
        
        return churn_by_duration


class EventTrackingViewSet(viewsets.ModelViewSet):
    """Event tracking and logging endpoints"""
    
    queryset = EventLog.objects.all()
    serializer_class = EventLogSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]
    
    def perform_create(self, serializer):
        """Create event log with user context"""
        event = serializer.save(
            user=self.request.user,
            company_id=getattr(self.request.user, 'company_id', None),
            ip_address=self._get_client_ip(self.request),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            referrer=self.request.META.get('HTTP_REFERER', ''),
            request_path=self.request.path,
        )
        
        # Trigger real-time alert checks for critical events
        if event.event_type in [EventType.PAYMENT_FAILED, EventType.CHURNED]:
            check_revenue_alerts.delay()
        
        return event
    
    @action(detail=False, methods=['post'])
    def track_batch(self, request):
        """Track multiple events in batch"""
        events_data = request.data.get('events', [])
        
        if not events_data:
            return Response(
                {'error': 'No events provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        created_events = []
        for event_data in events_data:
            serializer = EventLogSerializer(data=event_data)
            if serializer.is_valid():
                event = self.perform_create(serializer)
                created_events.append(event.id)
        
        return Response({
            'status': 'success',
            'events_created': len(created_events),
            'event_ids': created_events
        })
    
    def _get_client_ip(self, request) -> str:
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class MRRAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    """MRR analytics and reporting endpoints"""
    
    queryset = MRRSnapshot.objects.all()
    serializer_class = MRRSnapshotSerializer
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    authentication_classes = [TokenAuthentication]
    
    def get_queryset(self):
        """Filter by company"""
        queryset = super().get_queryset()
        company_id = getattr(self.request.user, 'company_id', None)
        
        if company_id:
            queryset = queryset.filter(user__company_id=company_id)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get MRR summary statistics"""
        queryset = self.get_queryset()
        
        summary = queryset.aggregate(
            total_mrr=Sum('monthly_amount'),
            average_mrr=Avg('monthly_amount'),
            total_active_subscriptions=Count('id', filter=Q(is_active=True)),
            total_canceled=Count('id', filter=Q(is_active=False)),
        )
        
        return Response({
            'total_mrr': float(summary['total_mrr'] or 0),
            'average_mrr': float(summary['average_mrr'] or 0),
            'active_subscriptions': summary['total_active_subscriptions'],
            'canceled_subscriptions': summary['total_canceled'],
        })
    
    @action(detail=False, methods=['get'])
    def mrr_history(self, request):
        """Get MRR history over time"""
        months = int(request.query_params.get('months', 12))
        start_date = timezone.now().date() - timedelta(days=30 * months)
        
        snapshots = self.get_queryset().filter(
            period_start__gte=start_date
        ).order_by('period_start')
        
        history = []
        for snapshot in snapshots:
            history.append({
                'date': snapshot.period_start.isoformat(),
                'mrr': float(snapshot.monthly_amount),
                'tier': snapshot.subscription_tier,
                'is_active': snapshot.is_active,
            })
        
        return Response({
            'history': history,
            'period_months': months,
        })


class RevenueAlertViewSet(viewsets.ModelViewSet):
    """Revenue alert management"""
    
    queryset = RevenueAlert.objects.all()
    serializer_class = RevenueAlertSerializer
    permission_classes = [IsAuthenticated, IsAnalyticsManager]
    authentication_classes = [TokenAuthentication]
    
    def get_queryset(self):
        """Filter by company"""
        queryset = super().get_queryset()
        company_id = getattr(self.request.user, 'company_id', None)
        
        if company_id:
            queryset = queryset.filter(metadata__company_id=str(company_id))
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark an alert as resolved"""
        alert = self.get_object()
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user
        alert.save()
        
        return Response({
            'status': 'success',
            'message': 'Alert resolved',
            'resolved_at': alert.resolved_at.isoformat()
        })
    
    @action(detail=False, methods=['post'])
    def test_alert(self, request):
        """Test alert notification system"""
        alert_type = request.data.get('alert_type')
        
        if not alert_type:
            return Response(
                {'error': 'alert_type required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create test alert
        test_alert = RevenueAlert.objects.create(
            alert_type=alert_type,
            alert_level=RevenueAlert.AlertLevel.INFO,
            title=f"Test Alert: {alert_type}",
            message="This is a test alert from the analytics system.",
            metadata={'test': True, 'company_id': str(self.get_company_id())}
        )
        
        # Trigger notification (async)
        from .tasks import send_alert_notification
        send_alert_notification.delay(str(test_alert.id))
        
        return Response({
            'status': 'success',
            'message': 'Test alert created',
            'alert_id': str(test_alert.id)
        })
    
    def get_company_id(self):
        return getattr(self.request.user, 'company_id', None)