import pytest
from django.test import RequestFactory
from django.core.exceptions import PermissionDenied
import threading

from ai.models import get_current_company_id, set_current_company_id, clear_current_company_id
from ai.middleware import EnterpriseTenantIsolationMiddleware
from ai.tests.factories import CompanyFactory

@pytest.mark.django_db
class TestTenantContextAndMiddleware:
    
    def test_thread_local_isolation(self):
        """Validates that distinct system operational threads manage segregated tenant variables."""
        set_current_company_id("tenant-alpha-id")
        
        def secondary_thread_worker():
            assert get_current_company_id() is None
            set_current_company_id("tenant-beta-id")
            assert get_current_company_id() == "tenant-beta-id"
            clear_current_company_id()

        thread = threading.Thread(target=secondary_thread_worker)
        thread.start()
        thread.join()
        
        assert get_current_company_id() == "tenant-alpha-id"
        clear_current_company_id()

    def test_middleware_attaches_company_context(self, rf):
        """Ensures incoming HTTP headers bind the tenant context safely to execution states."""
        company = CompanyFactory()
        request = rf.get("/api/v1/ai-reviews/", HTTP_X_COMPANY_ID=str(company.id))
        
        middleware = EnterpriseTenantIsolationMiddleware(lambda r: None)
        middleware.process_request(request)
        
        assert get_current_company_id() == str(company.id)
        assert request.company_id == str(company.id)
        
        # Clean down lifecycle context
        middleware.process_response(request, None)
        assert get_current_company_id() is None

    def test_middleware_rejects_invalid_company_id(self, rf):
        """Ensures unmapped or spoofed tenant UUID contexts drop processing operations immediately."""
        invalid_uuid = "00000000-0000-0000-0000-000000000000"
        request = rf.get("/api/v1/ai-reviews/", HTTP_X_COMPANY_ID=invalid_uuid)
        
        middleware = EnterpriseTenantIsolationMiddleware(lambda r: None)
        
        with pytest.raises(PermissionDenied):
            middleware.process_request(request)
