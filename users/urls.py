from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import *

urlpatterns = [
    # token
    path("token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    
    #register
    path("register/firm/", FirmRegisterView.as_view(), name="register_firm"),
    path("register/courier", CourierRegisterView.as_view(), name="register_courier")
]
