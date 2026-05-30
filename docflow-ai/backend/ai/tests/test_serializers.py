import pytest
from django.utils import timezone
from ai.serializers import ContractSerializer, AiReviewSerializer
from ai.tests.factories import CompanyFactory, PromptTemplateFactory, UserFactory
from ai.models import set_current_company_id, clear_current_company_id

@pytest.mark.django_db
class TestAiSerializersValidationPipeline:

    def test_contract_date_temporal_validation(self):
        """Ensures contract configurations reject inverted timelines (expiry prior to initialization)."""
        company = CompanyFactory()
        set_current_company_id(str(company.id))

        payload = {
            "title": "Malformed Lifecycle NDA",
            "contract_number": "NDA-2026-X9",
            "effective_date": timezone.now().date(),
            "expiry_date": timezone.now().date() - timezone.timedelta(days=365), # Invalid temporal state
            "parties": [],
            "clauses": []
        }

        serializer = ContractSerializer(data=payload)
        assert serializer.is_valid() is False
        assert "expiry_date" in serializer.errors
        clear_current_company_id()

    def test_ai_review_read_only_protection(self):
        """Guarantees that sensitive runtime telemetry can never be modified via an API payload."""
        payload = {
            "document_name": "vendor_agreement.pdf",
            "status": "completed", # Should be ignored (Read-Only)
            "tokens_used": 999999,  # Should be ignored (Read-Only)
            "extracted_text": "Malicious override payload structural content"
        }
        
        serializer = AiReviewSerializer(data=payload)
        assert serializer.is_valid() is True
        # Read-only attributes are dropped out of validated workspace output mappings
        assert "status" not in serializer.validated_data
        assert "tokens_used" not in serializer.validated_data
