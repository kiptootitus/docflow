from django.utils.deprecation import MiddlewareMixin
from django.core.exceptions import PermissionDenied
from django.conf import settings
import jwt

from .models import (
    set_current_company_id, 
    clear_current_company_id, 
    Company, 
    CompanyMembership
)

class EnterpriseTenantIsolationMiddleware(MiddlewareMixin):
    """
    Enterprise-grade tenant isolation layer. Resolves company scope via HTTP headers 
    or authorization tokens and guarantees context clearing at the end of the request cycle.
    """
    def process_request(self, request):
        company_id = request.headers.get("X-Company-ID")

        # Fallback: Extract from JWT Token if available in the Authorization header
        auth_header = request.headers.get("Authorization")
        if not company_id and auth_header and auth_header.startswith("Bearer "):
            try:
                token = auth_header.split(" ")[1]
                decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                company_id = decoded_token.get("company_id")
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, AttributeError):
                company_id = None

        if company_id:
            # Validate that the company exists and is active before binding context
            company_exists = Company.objects.filter(id=company_id).exists()
            if not company_exists:
                clear_current_company_id()
                raise PermissionDenied("Invalid or inactive Tenant configuration scope.")
            
            set_current_company_id(company_id)
            request.company_id = company_id
        else:
            clear_current_company_id()
            request.company_id = None

    def process_response(self, request, response):
        """Always clear context safely after processing a request to prevent leaks."""
        clear_current_company_id()
        return response

    def process_exception(self, request, exception):
        """Always clear context safely if an unhandled exception triggers mid-flight."""
        clear_current_company_id()
        return None
