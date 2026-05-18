"""Companies serializers"""
from rest_framework import serializers
from .models import Company, CompanyMember, Client


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = "__all__"
        read_only_fields = ["id", "owner", "invoice_counter", "created_at", "updated_at"]


class CompanyMemberSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = CompanyMember
        fields = ["id", "user", "user_email", "user_name", "role", "created_at"]


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = "__all__"
        read_only_fields = ["id", "company", "created_at", "updated_at"]
