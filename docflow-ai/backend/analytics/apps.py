# analytics/apps.py
from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AnalyticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analytics'
    verbose_name = 'Analytics & Business Intelligence'
    
    def ready(self):
        """Initialize analytics app with signal handlers"""
        import analytics.signals
        
        # Set up post-migrate signal to create necessary database views
        post_migrate.connect(create_analytics_views, sender=self)


def create_analytics_views(sender, **kwargs):
    """Create database views for materialized analytics"""
    from django.db import connection
    
    views = [
        """
        CREATE OR REPLACE VIEW analytics_daily_mrr_view AS
        SELECT 
            date(created_at) as date,
            SUM(value) as total_mrr,
            COUNT(DISTINCT user_id) as active_customers
        FROM analytics_event_logs
        WHERE event_type IN ('subscription_started', 'subscription_renewed')
        GROUP BY date(created_at)
        """
    ]
    
    with connection.cursor() as cursor:
        for view_sql in views:
            try:
                cursor.execute(view_sql)
            except Exception as e:
                # View might already exist
                pass