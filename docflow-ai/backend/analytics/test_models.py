# analytics/tests/test_models.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from unittest.mock import Mock, patch
from analytics.models import RevenueSnapshot, EventLog, MRRSnapshot, RevenueAlert, EventType

User = get_user_model()


class RevenueSnapshotModelTest(TestCase):
    """Test cases for RevenueSnapshot model"""
    
    def setUp(self):
        self.snapshot = RevenueSnapshot.objects.create(
            date=timezone.now().date(),
            mrr=Decimal('10000.00'),
            arr=Decimal('120000.00'),
            active_customers=100,
            new_customers=10,
            churned_customers=5,
            mrr_starter=Decimal('3000.00'),
            mrr_pro=Decimal('5000.00'),
            mrr_enterprise=Decimal('2000.00'),
            churn_rate=Decimal('0.05'),
            retention_rate=Decimal('95.00')
        )
    
    def test_snapshot_creation(self):
        """Test revenue snapshot creation"""
        self.assertIsNotNone(self.snapshot.id)
        self.assertEqual(self.snapshot.mrr, Decimal('10000.00'))
        self.assertEqual(self.snapshot.active_customers, 100)
    
    def test_auto_calculate_arpu(self):
        """Test ARPU auto-calculation on save"""
        self.snapshot.save()
        expected_arpu = Decimal('100.00')  # 10000 / 100
        self.assertEqual(self.snapshot.average_revenue_per_user, expected_arpu)
    
    def test_tier_consistency(self):
        """Test that tier totals match overall MRR"""
        self.snapshot.mrr_starter = Decimal('4000.00')
        self.snapshot.mrr_pro = Decimal('4000.00')
        self.snapshot.mrr_enterprise = Decimal('2000.00')
        self.snapshot.save()
        
        # Should auto-correct to match tier sum
        self.assertEqual(self.snapshot.mrr, Decimal('10000.00'))
    
    def test_validation_churn_rate(self):
        """Test churn rate validation"""
        with self.assertRaises(Exception):
            snapshot = RevenueSnapshot(
                date=timezone.now().date(),
                mrr=Decimal('10000.00'),
                churn_rate=Decimal('150.00')  # Invalid > 100
            )
            snapshot.full_clean()
    
    def test_str_method(self):
        """Test string representation"""
        expected_str = f"Snapshot {self.snapshot.date.isoformat()} - MRR: $10000.00"
        self.assertEqual(str(self.snapshot), expected_str)


class EventLogModelTest(TestCase):
    """Test cases for EventLog model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_event_creation(self):
        """Test event log creation"""
        event = EventLog.objects.create(
            user=self.user,
            event_type=EventType.SIGNUP,
            event_name='User Signup',
            metadata={'source': 'web'}
        )
        
        self.assertIsNotNone(event.id)
        self.assertEqual(event.event_type, EventType.SIGNUP)
        self.assertEqual(event.user, self.user)
    
    def test_track_event_factory(self):
        """Test track_event factory method"""
        event = EventLog.track_event(
            user=self.user,
            event_type=EventType.LOGIN,
            metadata={'ip': '127.0.0.1'},
            session_id='test_session_123'
        )
        
        self.assertEqual(event.event_type, EventType.LOGIN)
        self.assertEqual(event.session_id, 'test_session_123')
        self.assertEqual(event.metadata, {'ip': '127.0.0.1'})
    
    def test_event_str_method(self):
        """Test event string representation"""
        event = EventLog.objects.create(
            user=self.user,
            event_type=EventType.SIGNUP,
            event_name='User Signup'
        )
        
        expected_str = f"SIGNUP - {self.user} - {event.created_at}"
        self.assertEqual(str(event), expected_str)
    
    def test_event_metadata_json(self):
        """Test JSON metadata field"""
        complex_metadata = {
            'user_agent': 'Mozilla/5.0',
            'platform': 'web',
            'features_used': ['analytics', 'dashboard'],
            'performance': {'load_time': 1.23, 'api_calls': 5}
        }
        
        event = EventLog.objects.create(
            user=self.user,
            event_type=EventType.FEATURE_USED,
            event_name='Dashboard Viewed',
            metadata=complex_metadata
        )
        
        self.assertEqual(event.metadata['platform'], 'web')
        self.assertEqual(event.metadata['performance']['api_calls'], 5)


class MRRSnapshotModelTest(TestCase):
    """Test cases for MRRSnapshot model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='mrruser',
            email='mrr@example.com',
            password='testpass123'
        )
    
    def test_mrr_snapshot_creation(self):
        """Test MRR snapshot creation"""
        snapshot = MRRSnapshot.objects.create(
            user=self.user,
            subscription_tier='pro',
            monthly_amount=Decimal('49.00'),
            period_start=timezone.now().date(),
            period_end=timezone.now().date() + timezone.timedelta(days=30),
            change_type='new',
            is_active=True
        )
        
        self.assertIsNotNone(snapshot.id)
        self.assertEqual(snapshot.monthly_amount, Decimal('49.00'))
        self.assertTrue(snapshot.is_active)
    
    def test_unique_constraint(self):
        """Test unique constraint on user and period_start"""
        period_start = timezone.now().date()
        
        MRRSnapshot.objects.create(
            user=self.user,
            subscription_tier='starter',
            monthly_amount=Decimal('19.00'),
            period_start=period_start,
            period_end=period_start + timezone.timedelta(days=30),
            change_type='new'
        )
        
        # Trying to create another snapshot for same period should raise error
        with self.assertRaises(Exception):
            MRRSnapshot.objects.create(
                user=self.user,
                subscription_tier='pro',
                monthly_amount=Decimal('49.00'),
                period_start=period_start,
                period_end=period_start + timezone.timedelta(days=30),
                change_type='upgrade'
            )


class RevenueAlertModelTest(TestCase):
    """Test cases for RevenueAlert model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='adminuser',
            email='admin@example.com',
            password='adminpass123'
        )
    
    def test_alert_creation(self):
        """Test revenue alert creation"""
        alert = RevenueAlert.objects.create(
            alert_type=RevenueAlert.AlertType.MRR_MILESTONE,
            alert_level=RevenueAlert.AlertLevel.SUCCESS,
            title="MRR Milestone Reached: $10,000",
            message="Congratulations! Your MRR has reached $10,000.",
            current_value=Decimal('10000.00'),
            threshold=Decimal('10000.00')
        )
        
        self.assertIsNotNone(alert.id)
        self.assertEqual(alert.get_alert_level_display(), 'Success')
        self.assertFalse(alert.is_resolved)
    
    def test_resolve_alert(self):
        """Test alert resolution"""
        alert = RevenueAlert.objects.create(
            alert_type=RevenueAlert.AlertType.CHURN_SPIKE,
            alert_level=RevenueAlert.AlertLevel.CRITICAL,
            title="High Churn Rate Detected",
            message="Churn rate exceeded threshold"
        )
        
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.resolved_by = self.user
        alert.save()
        
        self.assertTrue(alert.is_resolved)
        self.assertIsNotNone(alert.resolved_at)
        self.assertEqual(alert.resolved_by, self.user)
    
    def test_alert_str_method(self):
        """Test alert string representation"""
        alert = RevenueAlert.objects.create(
            alert_type=RevenueAlert.AlertType.MRR_MILESTONE,
            alert_level=RevenueAlert.AlertLevel.INFO,
            title="Test Alert Title",
            message="Test alert message"
        )
        
        expected_str = f"Info: Test Alert Title"
        self.assertEqual(str(alert), expected_str)
