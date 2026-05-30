import pytest
from rest_framework.test import APIRequestFactory
from ai.permissions import HasRbacPermission, IsTenantAuthenticated
from ai.tests.factories import CompanyMembershipFactory, CompanyFactory, UserFactory
from ai.models import set_current_company_id, clear_current_company_id

class DummyReviewViewSet:
    __class__ = type("AiReviewViewSet", (), {})

@pytest.mark.django_db
class TestRbacSecurityEvaluationEngine:
    
    def test_has_rbac_permission_authorized(self, rf):
        """Validates matching affirmative matrix flags pass RBAC tests."""
        company = CompanyFactory()
        set_current_company_id(str(company.id))
        
        membership = CompanyMembershipFactory(
            company=company,
            permissions={"ai_tools": {"create": True, "read": True}}
        )
        
        request = rf.post("/api/v1/ai-reviews/")
        request.user = membership.user
        
        permission_checker = HasRbacPermission()
        view = DummyReviewViewSet()
        
        assert permission_checker.has_permission(request, view) is True
        clear_current_company_id()

    def test_has_rbac_permission_denied(self, rf):
        """Validates that missing permission matrix elements trigger security drops."""
        company = CompanyFactory()
        set_current_company_id(str(company.id))
        
        membership = CompanyMembershipFactory(
            company=company,
            permissions={"ai_tools": {"create": False, "read": True}}
        )
        
        request = rf.post("/api/v1/ai-reviews/")
        request.user = membership.user
        
        permission_checker = HasRbacPermission()
        view = DummyReviewViewSet()
        
        assert permission_checker.has_permission(request, view) is False
        clear_current_company_id()
