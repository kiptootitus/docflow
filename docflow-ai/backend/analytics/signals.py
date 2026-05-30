# analytics/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import EventLog, EventType, MRRSnapshot
from .tasks import check_revenue_alerts

User = get_user_model()


@receiver(post_save, sender=User)
def track_user_creation(sender, instance, created, **kwargs):
    """Track user signup events"""
    if created:
        EventLog.objects.create(
            user=instance,
            event_type=EventType.SIGNUP,
            event_name='User Signup',
            metadata={
                'email': instance.email,
                'is_active': instance.is_active,
            }
        )


@receiver(post_save, sender=MRRSnapshot)
def track_subscription_changes(sender, instance, created, **kwargs):
    """Track subscription changes for analytics"""
    if not created and instance.previous_amount:
        if instance.monthly_amount > instance.previous_amount:
            event_type = EventType.SUBSCRIPTION_UPGRADED
            event_name = 'Subscription Upgraded'
        elif instance.monthly_amount < instance.previous_amount:
            event_type = EventType.SUBSCRIPTION_DOWNGRADED
            event_name = 'Subscription Downgraded'
        else:
            return
        
        EventLog.objects.create(
            user=instance.user,
            event_type=event_type,
            event_name=event_name,
            value=instance.monthly_amount - instance.previous_amount,
            metadata={
                'previous_tier': instance.previous_tier,
                'new_tier': instance.subscription_tier,
                'previous_amount': str(instance.previous_amount),
                'new_amount': str(instance.monthly_amount),
            }
        )
