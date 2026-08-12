from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import CourierProfile, FirmProfile
from .permissions import IsAdminOrSelf, IsAdminUserRole
from .serializers import (
    CourierProfileSerializer,
    CourierProfileWriteSerializer,
    CourierRegistrationSerializer,
    CustomTokenObtainPairSerializer,
    FirmProfileSerializer,
    FirmRegistrationSerializer,
    PublicCourierProfileSerializer,
    UserSerializer,
)

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
    queryset = User.objects.select_related("firm_profile", "courier_profile").all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSelf]

    def get_queryset(self):
        user = self.request.user
        if user.role == User.Role.ADMIN:
            return self.queryset
        return self.queryset.filter(pk=user.pk)


class FirmViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = FirmProfile.objects.select_related("user").all()
    serializer_class = FirmProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == User.Role.ADMIN:
            return self.queryset
        if user.role == User.Role.FIRM:
            return self.queryset.filter(user=user)
        return self.queryset.none()

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUserRole])
    def adjust_balance(self, request, pk=None):
        try:
            amount = Decimal(request.data.get("amount", 0))
        except InvalidOperation:
            return Response(
                {"error": "invalid amount format"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount == 0:
            return Response(
                {"error": "amount must not be 0"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        FirmProfile.objects.filter(pk=pk).update(balance=F("balance") + amount)
        updated = self.get_object()
        return Response(
            {"message": "balance updated", "new_balance": str(updated.balance)}
        )

    @action(detail=False, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def deposit(self, request):
        user = request.user
        if user.role != User.Role.FIRM:
            return Response(
                {"error": "only firms can top up balance"},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            amount = Decimal(request.data.get("amount", 0))
        except InvalidOperation:
            return Response(
                {"error": "invalid amount format"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount <= 0:
            return Response(
                {"error": "amount must be positive"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            updated = FirmProfile.objects.filter(user=user).update(
                balance=F("balance") + amount
            )
            if not updated:
                return Response(
                    {"error": "firm profile not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            profile = FirmProfile.objects.get(user=user)
        return Response(
            {"message": "deposit completed", "new_balance": str(profile.balance)}
        )


class CourierViewSet(viewsets.ModelViewSet):
    queryset = CourierProfile.objects.select_related("user", "firm").all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CourierProfileWriteSerializer
        if self.request.user.role == User.Role.FIRM:
            return PublicCourierProfileSerializer
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
            # Firm sees ONLY its own couriers (no leak across firms).
            return qs.filter(user__is_active=True, user__is_verified=True, firm=user)
        if user.role == User.Role.COURIER:
            return qs.filter(user=user)
        return qs.none()

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUserRole])
    def adjust_balance(self, request, pk=None):
        try:
            amount = Decimal(request.data.get("amount", 0))
        except InvalidOperation:
            return Response(
                {"error": "invalid amount"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount == 0:
            return Response(
                {"error": "amount must not be 0"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        CourierProfile.objects.filter(pk=pk).update(balance=F("balance") + amount)
        updated = self.get_object()
        return Response(
            {"message": "balance updated", "new_balance": str(updated.balance)}
        )
