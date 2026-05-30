import pytest
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse

from ai.models import set_current_company_id, clear_current_company_id, AiReview
from ai.tests.factories import (
    CompanyFactory, CompanyMembershipFactory, TenantQuotaFactory,
    AiReviewFactory, PromptTemplateFactory
)

@pytest.mark.django_db
class TestAiAppControllerEndpoints:

    def setup_method(self):
        self.client = APIClient()
        
        # Build System Workspace Topology (Tenant A)
        self.company_a = CompanyFactory()
        self.quota_a = TenantQuotaFactory(company=self.company_a)
        self.membership_a = CompanyMembershipFactory(
            company=self.company_a, 
            role="admin"
        )
        self.user_a = self.membership_a.user

        # Build Cross Tenant Environment (Tenant B)
        self.company_b = CompanyFactory()
        self.membership_b = CompanyMembershipFactory(company=self.company_b)
        self.user_b = self.membership_b.user

    def test_strict_multi_tenant_viewset_filtering(self):
        """Guarantees records belonging to Tenant B are completely invisible to queries from Tenant A."""
        set_current_company_id(str(self.company_a.id))
        review_a = AiReviewFactory(company=self.company_a, created_by=self.user_a)
        clear_current_company_id()

        set_current_company_id(str(self.company_b.id))
        review_b = AiReviewFactory(company=self.company_b, created_by=self.user_b)
        clear_current_company_id()

        # Query endpoint under Tenant A's session context
        self.client.force_authenticate(user=self.user_a)
        url = reverse('ai-review-list')
        response = self.client.get(url, HTTP_X_COMPANY_ID=str(self.company_a.id))

        assert response.status_code == status.HTTP_200_OK
        returned_ids = [item['id'] for item in response.data]
        assert str(review_a.id) in returned_ids
        assert str(review_b.id) not in returned_ids  # Critical Isolation Screen Check

    def test_quota_exhaustion_blocks_ai_review_execution(self):
        """Verifies that an organization is blocked from executing an AI review if their token quota is reached."""
        # Max out quota limits for Company A
        self.quota_a.current_monthly_tokens_used = 5000000
        self.quota_a.monthly_token_limit = 5000000
        self.quota_a.save()

        self.client.force_authenticate(user=self.user_a)
        url = reverse('ai-review-list')
        payload = {"document_name": "procurement_policy.pdf"}

        set_current_company_id(str(self.company_a.id))
        response = self.client.post(url, payload, format='json', HTTP_X_COMPANY_ID=str(self.company_a.id))
        clear_current_company_id()

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "quota limit exceeded" in response.data['error']

    def test_semantic_vector_search_payload_validation(self):
        """Ensures vector indexing parameters require valid arrays matching dimension targets."""
        self.client.force_authenticate(user=self.user_a)
        url = reverse('clause-library-semantic-search')
        
        # Faulty execution array signature size (3 dimensions instead of 1536)
        malformed_payload = {"embedding": [0.1, 0.45, -0.22], "threshold": 0.25}
        
        set_current_company_id(str(self.company_a.id))
        response = self.client.post(url, malformed_payload, format='json', HTTP_X_COMPANY_ID=str(self.company_a.id))
        clear_current_company_id()

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "1536-dimensional float vector matrix" in response.data['error']

