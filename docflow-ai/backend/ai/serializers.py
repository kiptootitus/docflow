from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
import hashlib

from .models import (
    Company, TenantQuota, CompanyMembership, AiModelTier, AiReview,
    PromptTemplate, AiGeneration, Contract, ContractParty, DocumentVersion,
    DocumentShare, ClauseLibrary, ContractClause, RiskScore, ApprovalWorkflow,
    ApprovalStep, ContractSignature, ContractObligation, ComplianceRule,
    ComplianceAlert, ContractComment, AIConversation, AIMessage,
    WebhookSubscription, WebhookDelivery, Notification, AuditLog,
    UsageMetric, AiPromptLog, TaskExecution, ApiKey, LoginAudit,
    DataRetentionPolicy, get_current_company_id
)

User = get_user_model()

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'name', 'domain', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class TenantQuotaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantQuota
        fields = [
            'id', 'company', 'max_users', 'max_documents_storage_gb',
            'monthly_token_limit', 'current_monthly_tokens_used', 'reset_date'
        ]
        read_only_fields = ['id', 'company', 'current_monthly_tokens_used']


class CompanyMembershipSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = CompanyMembership
        fields = ['id', 'user', 'user_email', 'company', 'role', 'permissions', 'granted_at']
        read_only_fields = ['id', 'granted_at']

    def validate_permissions(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Permissions payload must be a JSON object structure.")
        required_keys = ["contracts", "ai_tools", "compliance", "billing"]
        for key in required_keys:
            if key not in value:
                raise serializers.ValidationError(f"Missing mandatory permission block key: '{key}'")
        return value


class AiModelTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = AiModelTier
        fields = ['id', 'name', 'primary_model', 'secondary_fallback', 'tertiary_fallback', 'is_active']


class RiskScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskScore
        fields = ['id', 'score', 'risk_breakdown', 'mitigation_strategy']


class ContractPartySerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractParty
        fields = ['id', 'name', 'email', 'role', 'signed']


class ContractClauseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractClause
        fields = ['id', 'clause', 'content', 'ai_generated']


class DocumentVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentVersion
        fields = [
            'id', 'version_number', 'content', 'searchable_content',
            'pdf_file', 'docx_file', 'checksum', 'created_by', 'created_at'
        ]
        read_only_fields = ['id', 'checksum', 'created_by', 'created_at']


class ClauseLibrarySerializer(serializers.ModelSerializer):
    """
    Master template library serializer tracking clause items.
    Excludes high-dimension vector embeddings from default output payloads for efficiency.
    """
    class Meta:
        model = ClauseLibrary
        fields = [
            'id', 'title', 'category', 'jurisdiction', 'content',
            'version', 'supersedes', 'risk_level', 'approved', 'created_at'
        ]
        read_only_fields = ['id', 'version', 'created_at']


class ContractSerializer(serializers.ModelSerializer):
    parties = ContractPartySerializer(many=True, required=False)
    clauses = ContractClauseSerializer(many=True, required=False)
    risk_profile = RiskScoreSerializer(read_only=True)
    versions = DocumentVersionSerializer(many=True, read_only=True)

    class Meta:
        model = Contract
        fields = [
            'id', 'title', 'contract_number', 'generation', 'status',
            'drafted_at', 'review_started_at', 'approved_at', 'signed_at',
            'activated_at', 'terminated_at', 'effective_date', 'expiry_date',
            'auto_renew', 'renewal_notice_days', 'tags', 'encrypted_value',
            'metadata', 'parties', 'clauses', 'risk_profile', 'versions'
        ]
        read_only_fields = [
            'id', 'status', 'drafted_at', 'review_started_at', 
            'approved_at', 'signed_at', 'activated_at', 'terminated_at'
        ]

    def validate(self, attrs):
        effective_date = attrs.get('effective_date')
        expiry_date = attrs.get('expiry_date')
        if expiry_date and effective_date and expiry_date <= effective_date:
            raise serializers.ValidationError({"expiry_date": "Contract expiry date must post-date the effective date."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        parties_data = validated_data.pop('parties', [])
        clauses_data = validated_data.pop('clauses', [])
        
        # Inject the middleware validated company scope directly
        validated_data['company_id'] = get_current_company_id()
        validated_data['status'] = Contract.Status.DRAFT
        validated_data['drafted_at'] = timezone.now()

        contract = Contract.objects.create(**validated_data)

        for party in parties_data:
            ContractParty.objects.create(contract=contract, **party)

        for clause in clauses_data:
            ContractClause.objects.create(contract=contract, **clause)

        return contract


class AiReviewSerializer(serializers.ModelSerializer):
    risk_profile = RiskScoreSerializer(read_only=True)

    class Meta:
        model = AiReview
        fields = [
            'id', 'created_by', 'document_name', 'document_file', 'extracted_text',
            'review_results', 'status', 'model_used', 'fallback_triggered',
            'tokens_used', 'error_message', 'completed_at', 'risk_profile'
        ]
        read_only_fields = ['id', 'created_by', 'status', 'extracted_text', 'review_results', 'tokens_used', 'completed_at']


class PromptTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptTemplate
        fields = ['id', 'name', 'template_type', 'system_prompt', 'user_prompt', 'variables', 'version', 'active']


class AiGenerationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AiGeneration
        fields = ['id', 'created_by', 'template', 'input_fields', 'generated_content', 'model_used', 'tokens_used']
        read_only_fields = ['id', 'created_by', 'generated_content', 'tokens_used']


class ContractSignatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractSignature
        fields = [
            'id', 'contract', 'signer', 'signature_hash', 'signed_document_checksum',
            'signature_provider', 'user_agent', 'geo_location', 'ip_address', 'signed_at'
        ]
        read_only_fields = ['id', 'signature_hash', 'signed_at']

    def create(self, validated_data):
        request = self.context.get('request')
        if request:
            validated_data['ip_address'] = request.META.get('REMOTE_ADDR')
            validated_data['user_agent'] = request.META.get('HTTP_USER_AGENT', '')
        
        payload = f"{validated_data['contract'].id}-{validated_data['signer'].id}-{timezone.now().isoformat()}"
        validated_data['signature_hash'] = hashlib.sha256(payload.encode()).hexdigest()
        
        return super().create(validated_data)


class ComplianceAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceAlert
        fields = ['id', 'contract', 'rule', 'severity', 'description', 'resolved']