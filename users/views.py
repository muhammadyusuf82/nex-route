from django.shortcuts import render
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import *
# Create your views here.

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class FirmRegisterView(generics.CreateAPIView):
    serializer_class = FirmRegistrationSerializer
    permission_classes = [permissions.AllowAny]

class CourierRegisterView(generics.CreateAPIView):
    serializer_class = CourierRegistrationSerializer
    permission_classes = [permissions.AllowAny]