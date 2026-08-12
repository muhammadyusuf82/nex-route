from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import *

router = DefaultRouter()
router.register(r"accounts", UserViewSet, basename="user")
router.register(r"firms", FirmViewSet, basename="firm")
router.register(r"couriers", CourierViewSet, basename="courier")

urlpatterns = [
    path("token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("register/firm/", FirmRegisterView.as_view(), name="register_firm"),
    path("register/courier/", CourierRegisterView.as_view(), name="register_courier"),
] + router.urls
