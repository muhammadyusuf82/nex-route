from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction
from .models import FirmProfile, CourierProfile

User = get_user_model()

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['is_verified'] = user.is_verified
        token['username'] = user.username
        return token
    
    def validate(self, attrs):
        data = super().validate(attrs)
        data["users"] = {
            "id":self.user.id,
            "username":self.user.username,
            "email":self.user.email,
            "role":self.user.role,
            "is_verified":self.user.is_verified
        }
        return data
    
class FirmRegistrationSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(write_only=True)
    firm_type = serializers.ChoiceField(choices=FirmProfile.FirmType.choices, write_only=True)
    tax_id = serializers.CharField(write_only=True)
    address = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'phone_number', 'password', 'company_name', 'firm_type', 'tax_id', 'address']
    
    @transaction.atomic
    def create(self, validated_data):
        company_name = validated_data.pop("company_name")
        firm_type = validated_data.pop("firm_type")
        tax_id = validated_data.pop("tax_id")
        address = validated_data.pop("address")
        
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            phone_number=validated_data["phone_number"],
            password=validated_data["password"],
            role=User.Role.FIRM,
            is_verified=False
        )
        
        FirmProfile.objects.create(
            user=user,
            company_name=company_name,
            firm_type=firm_type,
            tax_id=tax_id,
            address=address
        )
        return user
    
class CourierRegistrationSerializer(serializers.ModelSerializer):
    vehicle_type = serializers.CharField(write_only=True)
    license_plate = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, style={"input_type":"password"})
    
    class Meta:
        model = User
        fields = ["username", "email", "phone_number", "password", "vehicle_type", "license_plate"]
    
    @transaction.atomic
    def create(self, validated_data):
        vehicle_type = validated_data.pop("vehicle_type")
        license_plate = validated_data.pop("license_plate")
        
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            phone_number=validated_data["phone_number"],
            password=validated_data["password"],
            role=User.Role.COURIER,
            is_verified=False
        )
        
        CourierProfile.objects.create(
            user = user,
            vehicle_type = vehicle_type,
            license_plate = license_plate
        )
        return user