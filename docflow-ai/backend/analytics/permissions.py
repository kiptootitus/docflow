# analytics/permissions.py
from rest_framework import permissions


class IsAnalyticsManager(permissions.BasePermission):
    """Permission for analytics managers and admins"""
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Allow admins and users with analytics role
        return (
            request.user.is_staff or 
            request.user.is_superuser or
            request.user.groups.filter(name='AnalyticsManager').exists() or
            getattr(request.user, 'role', '') in ['admin', 'owner']
        )
    
    def has_object_permission(self, request, view, obj):
        # For object-level permissions
        return self.has_permission(request, view)


class IsCompanyAdmin(permissions.BasePermission):
    """Permission for company admins to access company analytics"""
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Company admins can access their company's data
        return (
            request.user.is_staff or
            getattr(request.user, 'role', '') in ['admin', 'owner']
        )
    
    def has_object_permission(self, request, view, obj):
        # Check if the object belongs to the user's company
        company_id = getattr(request.user, 'company_id', None)
        
        if not company_id:
            return False
        
        # Handle different object types
        if hasattr(obj, 'user') and hasattr(obj.user, 'company_id'):
            return obj.user.company_id == company_id
        elif hasattr(obj, 'company_id'):
            return obj.company_id == company_id
        
        return False


class IsOwnerOrReadOnly(permissions.BasePermission):
    """Custom permission to only allow owners to edit"""
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only to owner
        return obj.user == request.user
