from rest_framework.permissions import BasePermission

class IsAdminUserRole(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "ADMIN"

class IsFirmUser(BasePermission):
    def has_permission(self, request, view):
        return (request.user.is_authenticated and request.user.role == "FIRM" and request.user.is_verified)
    
class IsCourierUser(BasePermission):
    def has_permission(self, request, view):
        return (request.user.is_authenticated and request.user.role == "COURIER" and request.user.is_verified)
    