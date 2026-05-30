from rest_framework import permissions
from .models import CompanyMembership, get_current_company_id

class IsTenantAuthenticated(permissions.BasePermission):
    """
    Verifies that a user is explicitly authenticated and belongs to 
    the active tenant context currently injected by middleware.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        company_id = get_current_company_id()
        if not company_id:
            return False
            
        return CompanyMembership.objects.filter(
            user=request.user, 
            company_id=company_id
        ).exists()


class HasRbacPermission(permissions.BasePermission):
    """
    Maps incoming REST framework request methods onto fine-grained
    corporate structural JSON permissions within the user's membership node.
    """
    ACTION_MAP = {
        "GET": "read",
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete"
    }

    MODULE_MAP = {
        "ContractViewSet": "contracts",
        "AiReviewViewSet": "ai_tools",
        "AiGenerationViewSet": "ai_tools",
        "ComplianceAlertViewSet": "compliance",
        "TenantQuotaViewSet": "billing"
    }

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        company_id = get_current_company_id()
        if not company_id:
            return False

        try:
            membership = CompanyMembership.objects.get(user=request.user, company_id=company_id)
        except CompanyMembership.DoesNotExist:
            return False

        # Bypass structural checks for System Owners or Admins
        if membership.role in [CompanyMembership.RoleChoices.OWNER, CompanyMembership.RoleChoices.ADMIN]:
            return True

        view_class_name = view.__class__.__name__
        module_key = self.MODULE_MAP.get(view_class_name)
        action_key = self.ACTION_MAP.get(request.method)

        if not module_key or not action_key:
            return False

        # Check permission matrix inside the JSON field
        user_permissions = membership.permissions
        if not isinstance(user_permissions, dict):
            return False

        module_matrix = user_permissions.get(module_key, {})
        return bool(module_matrix.get(action_key, False))
