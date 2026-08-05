from rest_framework import viewsets, generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model

from .serializers import (
    CustomTokenObtainPairSerializer,
    FirmRegistrationSerializer,
    CourierRegistrationSerializer,
    UserSerializer,
    CourierProfileSerializer,
    CourierProfileWriteSerializer,
)
from .models import CourierProfile
from .permissions import IsAdminUserRole, IsAdminOrSelf

User = get_user_model()


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class FirmRegisterView(generics.CreateAPIView):
    serializer_class = FirmRegistrationSerializer
    permission_classes = [permissions.AllowAny]


class CourierRegisterView(generics.CreateAPIView):
    serializer_class = CourierRegistrationSerializer
    permission_classes = [permissions.AllowAny]


class UserViewSet(viewsets.ModelViewSet):
    """
    CRUD for users.
    - Admins: full access
    - Authenticated users: retrieve/update/delete own account only
    """

    queryset = User.objects.select_related("firm_profile", "courier_profile").all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSelf]

    def get_queryset(self):
        user = self.request.user
        if user.role == User.Role.ADMIN:
            return self.queryset
        return self.queryset.filter(pk=user.pk)


class CourierViewSet(viewsets.ModelViewSet):
    """CRUD for courier profiles. Admins write; firms/couriers limited read."""

    queryset = CourierProfile.objects.select_related("user").all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CourierProfileWriteSerializer
        return CourierProfileSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [permissions.IsAuthenticated(), IsAdminUserRole()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset
        if user.role == User.Role.ADMIN:
            return qs
        if user.role == User.Role.FIRM and user.is_verified:
            return qs.filter(user__is_active=True, user__is_verified=True)
        if user.role == User.Role.COURIER:
            return qs.filter(user=user)
        return qs.none()
