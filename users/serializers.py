from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
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
        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "role": self.user.role,
            "is_verified": self.user.is_verified,
        }
        return data


class FirmRegistrationSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(write_only=True)
    firm_type = serializers.ChoiceField(choices=FirmProfile.FirmType.choices, write_only=True)
    tax_id = serializers.CharField(write_only=True)
    address = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = [
            'username', 'email', 'phone_number', 'password',
            'company_name', 'firm_type', 'tax_id', 'address',
        ]

    def validate_password(self, value):
        validate_password(value)
        return value

    @transaction.atomic
    def create(self, validated_data):
        company_name = validated_data.pop("company_name")
        firm_type = validated_data.pop("firm_type")
        tax_id = validated_data.pop("tax_id")
        address = validated_data.pop("address")
        password = validated_data.pop("password")

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            phone_number=validated_data["phone_number"],
            password=password,
            role=User.Role.FIRM,
            is_verified=False,
        )

        FirmProfile.objects.create(
            user=user,
            company_name=company_name,
            firm_type=firm_type,
            tax_id=tax_id,
            address=address,
        )
        return user


class CourierRegistrationSerializer(serializers.ModelSerializer):
    vehicle_type = serializers.CharField(write_only=True)
    license_plate = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = [
            "username", "email", "phone_number", "password",
            "vehicle_type", "license_plate",
        ]

    def validate_password(self, value):
        validate_password(value)
        return value

    @transaction.atomic
    def create(self, validated_data):
        vehicle_type = validated_data.pop("vehicle_type")
        license_plate = validated_data.pop("license_plate")
        password = validated_data.pop("password")

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            phone_number=validated_data["phone_number"],
            password=password,
            role=User.Role.COURIER,
            is_verified=False,
        )

        CourierProfile.objects.create(
            user=user,
            vehicle_type=vehicle_type,
            license_plate=license_plate,
        )
        return user


class FirmProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = FirmProfile
        fields = ("id", "company_name", "firm_type", "tax_id", "address")


class CourierProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    is_verified = serializers.BooleanField(source="user.is_verified", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = CourierProfile
        fields = (
            "id",
            "user_id",
            "username",
            "email",
            "phone_number",
            "is_verified",
            "vehicle_type",
            "license_plate",
            "current_status",
        )
        read_only_fields = ("id", "user_id", "username", "email", "phone_number", "is_verified")


class CourierProfileWriteSerializer(serializers.ModelSerializer):
    """Admin create/update of courier profile fields plus optional user fields."""

    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False)
    password = serializers.CharField(
        write_only=True, required=False, style={"input_type": "password"}
    )
    is_verified = serializers.BooleanField(required=False)

    class Meta:
        model = CourierProfile
        fields = (
            "username",
            "email",
            "phone_number",
            "password",
            "is_verified",
            "vehicle_type",
            "license_plate",
            "current_status",
        )

    def validate_password(self, value):
        validate_password(value)
        return value

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password", None)
        username = validated_data.pop("username", None)
        email = validated_data.pop("email", "")
        phone_number = validated_data.pop("phone_number", None)
        is_verified = validated_data.pop("is_verified", False)

        if not username or not phone_number or not password:
            raise serializers.ValidationError(
                "username, phone_number, and password are required to create a courier."
            )

        user = User.objects.create_user(
            username=username,
            email=email,
            phone_number=phone_number,
            password=password,
            role=User.Role.COURIER,
            is_verified=is_verified,
        )
        return CourierProfile.objects.create(user=user, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = instance.user

        for attr in ("username", "email", "phone_number", "is_verified"):
            if attr in validated_data:
                setattr(user, attr, validated_data.pop(attr))
        if password:
            user.set_password(password)
        user.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=False, style={"input_type": "password"}
    )
    firm_profile = FirmProfileSerializer(read_only=True)
    courier_profile = CourierProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "phone_number",
            "role",
            "is_verified",
            "is_active",
            "password",
            "date_joined",
            "firm_profile",
            "courier_profile",
        )
        read_only_fields = ("id", "date_joined", "firm_profile", "courier_profile")

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_role(self, value):
        request = self.context.get("request")
        if request and getattr(request.user, "role", None) != User.Role.ADMIN:
            raise serializers.ValidationError("Only admins can change roles.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "This field is required."})
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        request = self.context.get("request")

        # Non-admins cannot escalate privileges
        if request and request.user.role != User.Role.ADMIN:
            validated_data.pop("role", None)
            validated_data.pop("is_verified", None)
            validated_data.pop("is_active", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
