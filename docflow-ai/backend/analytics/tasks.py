# analytics/tasks.py
from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta
import logging
from decimal import Decimal 

from .models import RevenueSnapshot, RevenueAlert, EventLog, EventType
from .aggregators import RevenueAggregator
from notifications.tasks import send_alert_notification

logger = logging.getLogger(__name__)


@shared_task
def generate_daily_snapshots():
    """Generate revenue snapshots for all companies"""
    logger.info("Starting daily snapshot generation")
    
    # Get all distinct company IDs
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    company_ids = User.objects.filter(
        company_id__isnull=False
    ).values_list('company_id', flat=True).distinct()
    
    snapshots_created = 0
    
    for company_id in company_ids:
        try:
            aggregator = RevenueAggregator(company_id=company_id)
            snapshot = aggregator.generate_daily_snapshot()
            snapshots_created += 1
            logger.info(f"Snapshot created for company {company_id}")
        except Exception as e:
            logger.error(f"Failed to generate snapshot for company {company_id}: {str(e)}")
    
    # Also generate overall snapshot (no company filter)
    try:
        aggregator = RevenueAggregator()
        aggregator.generate_daily_snapshot()
        snapshots_created += 1
    except Exception as e:
        logger.error(f"Failed to generate overall snapshot: {str(e)}")
    
    logger.info(f"Daily snapshot generation completed. Created {snapshots_created} snapshots")
    
    return {
        'status': 'completed',
        'snapshots_created': snapshots_created,
        'timestamp': timezone.now().isoformat()
    }


@shared_task
def check_revenue_alerts():
    """Check for revenue anomalies and create alerts"""
    logger.info("Checking revenue alerts")
    
    aggregator = RevenueAggregator()
    alerts_created = []
    
    try:
        # Check for MRR milestones
        current_mrr = aggregator.calculate_current_mrr().total_mrr
        milestone_thresholds = [1000, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000]
        
        for threshold in milestone_thresholds:
            if current_mrr >= Decimal(str(threshold)):
                # Check if we already have this milestone alert
                existing = RevenueAlert.objects.filter(
                    alert_type=RevenueAlert.AlertType.MRR_MILESTONE,
                    metadata__threshold=threshold,
                    created_at__gte=timezone.now() - timedelta(days=1)
                ).exists()
                
                if not existing:
                    alert = RevenueAlert.objects.create(
                        alert_type=RevenueAlert.AlertType.MRR_MILESTONE,
                        alert_level=RevenueAlert.AlertLevel.SUCCESS,
                        title=f"MRR Milestone Reached: ${threshold:,.0f}",
                        message=f"Congratulations! Your MRR has reached ${threshold:,.0f}.",
                        current_value=current_mrr,
                        threshold=Decimal(str(threshold)),
                        metadata={'threshold': threshold}
                    )
                    alerts_created.append(str(alert.id))
                    
                    # Send notification
                    send_alert_notification.delay(str(alert.id))
        
        # Check for churn spikes
        churn_metrics = aggregator.calculate_churn_metrics(period_days=7)
        churn_rate = churn_metrics.logo_churn_rate
        
        if churn_rate > 10:  # 10% churn rate threshold
            existing = RevenueAlert.objects.filter(
                alert_type=RevenueAlert.AlertType.CHURN_SPIKE,
                created_at__gte=timezone.now() - timedelta(days=7)
            ).exists()
            
            if not existing:
                alert = RevenueAlert.objects.create(
                    alert_type=RevenueAlert.AlertType.CHURN_SPIKE,
                    alert_level=RevenueAlert.AlertLevel.CRITICAL,
                    title=f"High Churn Rate Detected: {churn_rate:.1f}%",
                    message=f"Your 7-day churn rate is {churn_rate:.1f}%, which exceeds the 10% threshold. "
                           f"{churn_metrics.customer_churned_count} customers churned in the last 7 days.",
                    current_value=Decimal(str(churn_rate)),
                    threshold=Decimal('10.0')
                )
                alerts_created.append(str(alert.id))
                send_alert_notification.delay(str(alert.id))
        
        # Check for payment failure spikes
        failure_threshold = 5  # 5 failures in last hour
        recent_failures = EventLog.objects.filter(
            event_type=EventType.PAYMENT_FAILED,
            created_at__gte=timezone.now() - timedelta(hours=1)
        ).count()
        
        if recent_failures >= failure_threshold:
            existing = RevenueAlert.objects.filter(
                alert_type=RevenueAlert.AlertType.PAYMENT_FAILURE,
                created_at__gte=timezone.now() - timedelta(hours=2)
            ).exists()
            
            if not existing:
                alert = RevenueAlert.objects.create(
                    alert_type=RevenueAlert.AlertType.PAYMENT_FAILURE,
                    alert_level=RevenueAlert.AlertLevel.WARNING,
                    title=f"Payment Failure Spike: {recent_failures} in last hour",
                    message=f"{recent_failures} payment failures have occurred in the last hour. "
                           f"Please check your payment processor integration.",
                    current_value=Decimal(str(recent_failures)),
                    threshold=Decimal(str(failure_threshold))
                )
                alerts_created.append(str(alert.id))
                send_alert_notification.delay(str(alert.id))
        
        # Check for upgrade activity spikes
        recent_upgrades = EventLog.objects.filter(
            event_type=EventType.SUBSCRIPTION_UPGRADED,
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).count()
        
        if recent_upgrades > 50:
            existing = RevenueAlert.objects.filter(
                alert_type=RevenueAlert.AlertType.UPGRADE_BOOST,
                created_at__gte=timezone.now() - timedelta(hours=24)
            ).exists()
            
            if not existing:
                alert = RevenueAlert.objects.create(
                    alert_type=RevenueAlert.AlertType.UPGRADE_BOOST,
                    alert_level=RevenueAlert.AlertLevel.SUCCESS,
                    title=f"Upgrade Activity Spike: {recent_upgrades} upgrades in 24h",
                    message=f"Great news! {recent_upgrades} customers upgraded their plans in the last 24 hours.",
                    current_value=Decimal(str(recent_upgrades))
                )
                alerts_created.append(str(alert.id))
                send_alert_notification.delay(str(alert.id))
                
    except Exception as e:
        logger.error(f"Error checking revenue alerts: {str(e)}")
    
    logger.info(f"Alert check completed. Created {len(alerts_created)} alerts")
    
    return {
        'status': 'completed',
        'alerts_created': len(alerts_created),
        'alert_ids': alerts_created
    }


@shared_task
def update_mrr_snapshots():
    """Update MRR snapshots for active subscriptions"""
    logger.info("Updating MRR snapshots")
    
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    today = timezone.now().date()
    period_start = today.replace(day=1)
    
    # Get next month's end date
    if period_start.month == 12:
        period_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        period_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    
    # Update snapshots for all active users
    from .models import MRRSnapshot
    
    snapshots_updated = 0
    
    for user in User.objects.filter(is_active=True):
        # Get user's subscription from billing system
        # This is a simplified example - you'll need to integrate with your billing system
        subscription_tier = getattr(user, 'subscription_tier', None)
        monthly_amount = getattr(user, 'monthly_amount', None)
        
        if subscription_tier and monthly_amount:
            snapshot, created = MRRSnapshot.objects.update_or_create(
                user=user,
                period_start=period_start,
                defaults={
                    'period_end': period_end,
                    'subscription_tier': subscription_tier,
                    'monthly_amount': monthly_amount,
                    'is_active': True
                }
            )
            snapshots_updated += 1
    
    logger.info(f"Updated {snapshots_updated} MRR snapshots")
    
    return {
        'status': 'completed',
        'snapshots_updated': snapshots_updated
    }


@shared_task
def send_analytics_report_email():
    """Send daily/weekly analytics report email to admins"""
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    # Get admin users
    admins = User.objects.filter(
        Q(is_staff=True) | Q(is_superuser=True) | Q(groups__name='AnalyticsManager')
    ).distinct()
    
    aggregator = RevenueAggregator()
    mrr_metrics = aggregator.calculate_current_mrr()
    churn_metrics = aggregator.calculate_churn_metrics()
    
    # Prepare email context
    context = {
        'mrr': mrr_metrics.total_mrr,
        'arr': aggregator.calculate_annual_recurring_revenue(),
        'churn_rate': churn_metrics.logo_churn_rate,
        'active_customers': churn_metrics.customers_at_end,
        'new_customers': churn_metrics.customer_churned_count,
        'date': timezone.now().date(),
    }
    
    html_content = render_to_string('analytics/email_report.html', context)
    
    for admin in admins:
        try:
            send_mail(
                subject=f'Daily Analytics Report - {timezone.now().date()}',
                message=f'MRR: ${mrr_metrics.total_mrr}\nChurn Rate: {churn_metrics.logo_churn_rate}%',
                from_email='analytics@docflow.ai',
                recipient_list=[admin.email],
                html_message=html_content,
                fail_silently=False,
            )
        except Exception as e:
            logger.error(f"Failed to send analytics email to {admin.email}: {str(e)}")
    
    return {
        'status': 'completed',
        'recipients_count': admins.count()
    }