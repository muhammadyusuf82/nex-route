from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from rest_framework.pagination import PageNumberPagination
from users.permissions import (
    IsAdminUserRole,
    IsAdminOrVerifiedFirm,
    IsItemOwnerOrAdmin,
    IsTodoAssignerOrAdmin,
)
from .models import Item, Todo
from .serializers import (
    ItemSerializer,
    TodoSerializer,
    TodoWriteSerializer,
    TodoCourierStatusSerializer,
)
User = get_user_model()

class StandartResultsSetPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = 'page_size'
    max_page_size = 100
class ItemViewSet(viewsets.ModelViewSet):
    """CRUD for items. Firms manage their own; admins manage all."""

    queryset = Item.objects.select_related("owner").all()
    serializer_class = ItemSerializer
    permission_classes = [permissions.IsAuthenticated, IsItemOwnerOrAdmin]
    pagination_class = StandartResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset
        if user.role == User.Role.ADMIN:
            return qs
        if user.role == User.Role.FIRM and user.is_verified:
            return qs.filter(owner=user)
        if user.role == User.Role.COURIER and user.is_verified:
            return qs.none()
        return qs.none()

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsAdminOrVerifiedFirm()]
        if self.action in ("update", "partial_update", "destroy"):
            return [permissions.IsAuthenticated(), IsItemOwnerOrAdmin()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        user = self.request.user
        owner = user
        if user.role == User.Role.ADMIN:
            owner_id = self.request.data.get("owner")
            if owner_id:
                try:
                    owner = User.objects.get(pk=owner_id, role=User.Role.FIRM)
                except User.DoesNotExist:
                    from rest_framework.exceptions import ValidationError
                    raise ValidationError({"owner": "Invalid firm user id."})
            else:
                owner = user
        serializer.save(owner=owner)


class TodoViewSet(viewsets.ModelViewSet):
    """
    CRUD for courier tasks assigned by admins or verified firms.
    Couriers can list their todos and update status only.
    """

    queryset = Todo.objects.select_related(
        "assigned_by", "courier", "courier__user"
    ).all()
    permission_classes = [permissions.IsAuthenticated, IsTodoAssignerOrAdmin]
    pagination_class = StandartResultsSetPagination

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            user = self.request.user
            if user.role == User.Role.COURIER:
                return TodoCourierStatusSerializer
            return TodoWriteSerializer
        return TodoSerializer

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset
        if user.role == User.Role.ADMIN:
            return qs
        if user.role == User.Role.FIRM and user.is_verified:
            return qs.filter(assigned_by=user)
        if user.role == User.Role.COURIER and user.is_verified:
            return qs.filter(courier__user=user)
        return qs.none()

    def create(self, request, *args, **kwargs):
        if request.user.role not in (User.Role.ADMIN, User.Role.FIRM):
            return Response(
                {"detail": "Only admins or verified firms can assign todos."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        todo = self.get_object()
        if request.user.role == User.Role.COURIER:
            return Response(
                {"detail": "Couriers cannot delete todos."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)
