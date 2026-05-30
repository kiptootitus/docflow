# analytics/management/commands/generate_analytics_snapshots.py
from django.core.management.base import BaseCommand
from analytics.tasks import generate_daily_snapshots, update_mrr_snapshots, check_revenue_alerts
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Generate analytics snapshots and run revenue checks'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--full',
            action='store_true',
            help='Run full analytics generation including historical data'
        )
    
    def handle(self, *args, **options):
        self.stdout.write('Starting analytics snapshot generation...')
        
        if options['full']:
            self.stdout.write('Running full analytics generation...')
            # Generate historical snapshots for last 90 days
            from datetime import timedelta
            from django.utils import timezone
            from analytics.aggregators import RevenueAggregator
            
            aggregator = RevenueAggregator()
            for i in range(90):
                target_date = timezone.now().date() - timedelta(days=i)
                self.stdout.write(f'Generating snapshot for {target_date}')
                aggregator.generate_daily_snapshot(target_date)
        
        # Run regular tasks
        self.stdout.write('Updating MRR snapshots...')
        update_mrr_snapshots.delay()
        
        self.stdout.write('Generating daily snapshots...')
        generate_daily_snapshots.delay()
        
        self.stdout.write('Checking revenue alerts...')
        check_revenue_alerts.delay()
        
        self.stdout.write(self.style.SUCCESS('Successfully triggered analytics generation'))
