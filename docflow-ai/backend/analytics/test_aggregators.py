# analytics/tests/test_aggregators.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from unittest.mock import Mock, patch
from analytics.aggregators import RevenueAggregator, MRRMetrics, ChurnMetrics
from analytics.models import MRRSnapshot, EventLog, EventType

User = get_user_model()


class RevenueAggregatorTest(TestCase):
    """Test cases for RevenueAggregator"""
    
    def setUp(self):
        self.aggregator = RevenueAggregator()
        
        # Create test users with subscriptions
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        self.user3 = User.objects.create_user(
            username='user3',
            email='user3@example.com',
            password='testpass123'
        )
        
        # Create MRR snapshots
        today = timezone.now().date()
        
        MRRSnapshot.objects.create(
            user=self.user1,
            subscription_tier='pro',
            monthly_amount=Decimal('49.00'),
            period_start=today,
            period_end=today + timedelta(days=30),
            change_type='new',
            is_active=True
        )
        
        MRRSnapshot.objects.create(
            user=self.user2,
            subscription_tier='starter',
            monthly_amount=Decimal('19.00'),
            period_start=today,
            period_end=today + timedelta(days=30),
            change_type='new',
            is_active=True
        )
        
        MRRSnapshot.objects.create(
            user=self.user3,
            subscription_tier='enterprise',
            monthly_amount=Decimal('99.00'),
            period_start=today,
            period_end=today + timedelta(days=30),
            change_type='new',
            is_active=True
        )
    
    def test_calculate_current_mrr(self):
        """Test MRR calculation"""
        mrr_metrics = self.aggregator.calculate_current_mrr()
        
        # Total MRR: 49 + 19 + 99 = 167
        self.assertEqual(mrr_metrics.total_mrr, Decimal('167.00'))
        self.assertEqual(mrr_metrics.mrr_starter, Decimal('19.00'))
        self.assertEqual(mrr_metrics.mrr_pro, Decimal('49.00'))
        self.assertEqual(mrr_metrics.mrr_enterprise, Decimal('99.00'))
    
    def test_calculate_mrr_breakdown(self):
        """Test MRR breakdown dictionary"""
        mrr_metrics = self.aggregator.calculate_current_mrr()
        
        breakdown = mrr_metrics.mrr_breakdown
        self.assertEqual(breakdown['starter'], 19.00)
        self.assertEqual(breakdown['pro'], 49.00)
        self.assertEqual(breakdown['enterprise'], 99.00)
    
    def test_calculate_churn_metrics(self):
        """Test churn metrics calculation"""
        # Create churn events
        EventLog.objects.create(
            user=self.user1,
            event_type=EventType.CHURNED,
            event_name='Customer Churned',
            created_at=timezone.now() - timedelta(days=15)
        )
        
        churn_metrics = self.aggregator.calculate_churn_metrics(period_days=30)
        
        self.assertEqual(churn_metrics.customer_churned_count, 1)
        self.assertIsNotNone(churn_metrics.logo_churn_rate)
    
    def test_calculate_annual_recurring_revenue(self):
        """Test ARR calculation"""
        arr = self.aggregator.calculate_annual_recurring_revenue()
        
        # MRR = 167, ARR = 167 * 12 = 2004
        self.assertEqual(arr, Decimal('2004.00'))
    
    def test_customer_ltv_calculation(self):
        """Test LTV calculation"""
        ltv = self.aggregator.calculate_customer_ltv()
        
        # Should return positive value
        self.assertGreater(ltv, Decimal('0'))
    
    def test_new_mrr_calculation(self):
        """Test new MRR calculation"""
        new_mrr = self.aggregator._calculate_new_mrr(last_n_days=30)
        
        # All subscriptions are new (created in this period)
        self.assertEqual(new_mrr, Decimal('167.00'))
    
    def test_generate_daily_snapshot(self):
        """Test daily snapshot generation"""
        snapshot = self.aggregator.generate_daily_snapshot()
        
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.mrr, Decimal('167.00'))
        self.assertEqual(snapshot.active_customers, 3)
        self.assertEqual(snapshot.new_customers, 3)
    
    def test_revenue_trends(self):
        """Test revenue trends generation"""
        trends = self.aggregator.get_revenue_trends(days=5)
        
        self.assertIsInstance(trends, list)
        self.assertGreaterEqual(len(trends), 1)
        
        for trend in trends:
            self.assertIn('date', trend)
            self.assertIn('mrr', trend)
            self.assertIn('active_customers', trend)
    
    def test_company_filter(self):
        """Test company-specific aggregator"""
        # This would need company setup in your actual app
        pass
    
    def test_calculate_arpu(self):
        """Test ARPU calculation"""
        arpu = self.aggregator._calculate_arpu()
        
        # ARPU = MRR / Active Customers = 167 / 3 = 55.67
        expected_arpu = Decimal('55.6666666667')
        self.assertAlmostEqual(float(arpu), float(expected_arpu), places=2)


class MRRMetricsDataClassTest(TestCase):
    """Test MRRMetrics dataclass"""
    
    def test_mrr_metrics_creation(self):
        """Test MRRMetrics dataclass"""
        metrics = MRRMetrics(
            total_mrr=Decimal('1000.00'),
            mrr_starter=Decimal('200.00'),
            mrr_pro=Decimal('500.00'),
            mrr_enterprise=Decimal('300.00'),
            mrr_growth_rate=10.5,
            new_mrr_added=Decimal('100.00'),
            churned_mrr=Decimal('50.00'),
            expansion_mrr=Decimal('75.00'),
            contraction_mrr=Decimal('25.00'),
            net_new_mrr=Decimal('100.00')
        )
        
        self.assertEqual(metrics.total_mrr, Decimal('1000.00'))
        self.assertEqual(metrics.mrr_growth_rate, 10.5)
        
        # Test property
        breakdown = metrics.mrr_breakdown
        self.assertEqual(breakdown['starter'], 200.00)
        self.assertEqual(breakdown['pro'], 500.00)
        self.assertEqual(breakdown['enterprise'], 300.00)


class ChurnMetricsDataClassTest(TestCase):
    """Test ChurnMetrics dataclass"""
    
    def test_churn_metrics_creation(self):
        """Test ChurnMetrics dataclass"""
        metrics = ChurnMetrics(
            logo_churn_rate=5.0,
            revenue_churn_rate=3.5,
            net_revenue_churn=2.0,
            gross_revenue_churn=4.0,
            customer_churned_count=10,
            mrr_churned=Decimal('500.00'),
            customers_at_start=200,
            customers_at_end=195
        )
        
        self.assertEqual(metrics.logo_churn_rate, 5.0)
        self.assertEqual(metrics.customer_churned_count, 10)
        
        # Test retention rate property
        self.assertEqual(metrics.retention_rate, 95.0)
