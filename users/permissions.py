from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdminUserRole(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and getattr(request.user, "role", None) == "ADMIN"
        )


class IsFirmUser(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.role == "FIRM"
            and request.user.is_verified
        )


class IsCourierUser(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.role == "COURIER"
            and request.user.is_verified
        )


class IsAdminOrSelf(BasePermission):
    """Admins: full access. Other users: only their own account, no create."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == "ADMIN":
            return True
        if view.action == "create":
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if request.user.role == "ADMIN":
            return True
        return obj.pk == request.user.pk


class IsAdminOrVerifiedFirm(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == "ADMIN":
            return True
        return request.user.role == "FIRM" and request.user.is_verified


class IsItemOwnerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.user.role == "ADMIN":
            return True
        if request.method in SAFE_METHODS:
            return (
                obj.owner_id == request.user.id
                or request.user.role in ("COURIER", "FIRM")
            )
        return obj.owner_id == request.user.id and request.user.role == "FIRM"


class IsTodoAssignerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == "ADMIN":
            return True
        if request.method in SAFE_METHODS:
            return True
        if request.method == "POST":
            return request.user.role == "FIRM" and request.user.is_verified
        if request.method in ("PUT", "PATCH"):
            return (
                (request.user.role == "FIRM" and request.user.is_verified)
                or (request.user.role == "COURIER" and request.user.is_verified)
            )
        return False

    def has_object_permission(self, request, view, obj):
        if request.user.role == "ADMIN":
            return True
        if request.user.role == "FIRM" and request.user.is_verified:
            return (
                obj.assigned_by_id == request.user.id
                or obj.firm_id == request.user.id
            )
        if request.user.role == "COURIER" and request.user.is_verified:
            if request.method in SAFE_METHODS:
                return obj.courier.user_id == request.user.id
            if request.method in ("PUT", "PATCH"):
                return obj.courier.user_id == request.user.id
            return False
        return False
