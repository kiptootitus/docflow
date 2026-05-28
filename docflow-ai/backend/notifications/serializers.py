"""
DocFlow AI — notifications/serializers.py
"""
from __future__ import annotations
from rest_framework import serializers
from .models import Notification, NotificationPreference, PushToken, Channel


class NotificationSerializer(serializers.ModelSerializer):
    is_read    = serializers.BooleanField(read_only=True)
    via_email  = serializers.BooleanField(read_only=True)
    via_push   = serializers.BooleanField(read_only=True)
    via_in_app = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Notification
        fields = [
            "id", "category", "priority", "title", "body", "data",
            "action_url", "is_read", "read_at", "created_at",
            "via_email", "via_push", "via_in_app",
        ]
        read_only_fields = fields


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    email  = serializers.SerializerMethodField()
    push   = serializers.SerializerMethodField()
    in_app = serializers.SerializerMethodField()

    class Meta:
        model  = NotificationPreference
        fields = ["id", "category", "channels", "email", "push", "in_app", "updated_at"]
        read_only_fields = ["id", "updated_at"]

    def get_email(self, obj)  -> bool: return bool(obj.channels & Channel.EMAIL)
    def get_push(self, obj)   -> bool: return bool(obj.channels & Channel.PUSH)
    def get_in_app(self, obj) -> bool: return bool(obj.channels & Channel.IN_APP)


class PushTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PushToken
        fields = ["id", "platform", "device_name", "is_active", "created_at", "updated_at"]
        read_only_fields = fields


class PushTokenWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PushToken
        fields = ["token", "platform", "device_name"]

    def validate_token(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("A push token is required.")
        return value.strip()