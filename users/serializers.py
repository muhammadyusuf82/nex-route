from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import CourierProfile, FirmProfile

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["is_verified"] = user.is_verified
        token["username"] = user.username
        
        if user.role == user.Role.FIRM and hasattr(user, 'firm_profile'):
            token["firm_profile_id"] = user.firm_profile.id
        elif user.role == user.Role.COURIER and hasattr(user, 'courier_profile'):
            token["courier_profile_id"] = user.courier_profile.id
            
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        
        user_dict = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "role": self.user.role,
            "is_verified": self.user.is_verified,
        }

        if self.user.role == self.user.Role.FIRM and hasattr(self.user, 'firm_profile'):
            user_dict["firm_profile"] = FirmProfileSerializer(self.user.firm_profile).data
        elif self.user.role == self.user.Role.COURIER and hasattr(self.user, 'courier_profile'):
            user_dict["courier_profile"] = CourierProfileSerializer(self.user.courier_profile).data
            
        data["user"] = user_dict
        return data


class FirmRegistrationSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(write_only=True, max_length=255)
    firm_type = serializers.ChoiceField(
        choices=FirmProfile.FirmType.choices, write_only=True
    )
    tax_id = serializers.CharField(write_only=True, max_length=50)
    address = serializers.CharField(write_only=True)
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = [
            "username", "email", "phone_number", "password",
            "company_name", "firm_type", "tax_id", "address",
        ]

    def validate_phone_number(self, value):
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("Phone number already registered.")
        return value

    def validate_tax_id(self, value):
        if FirmProfile.objects.filter(tax_id=value).exists():
            raise serializers.ValidationError("Tax ID already registered.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        company_name = validated_data.pop("company_name")
        firm_type = validated_data.pop("firm_type")
        tax_id = validated_data.pop("tax_id")
        address = validated_data.pop("address")

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email") or "",
            phone_number=validated_data["phone_number"],
            password=password,
            role=User.Role.FIRM,
            is_verified=False,
        )
        FirmProfile.objects.create(
            user=user, company_name=company_name, firm_type=firm_type,
            tax_id=tax_id, address=address,
        )
        return user


class CourierRegistrationSerializer(serializers.ModelSerializer):
    vehicle_type = serializers.CharField(write_only=True, max_length=50)
    license_plate = serializers.CharField(write_only=True, max_length=20)
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )
    firm_id = serializers.IntegerField(
        write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = User
        fields = [
            "username", "email", "phone_number", "password",
            "vehicle_type", "license_plate", "firm_id",
        ]

    def validate_phone_number(self, value):
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("Phone number already registered.")
        return value

    def validate_firm_id(self, value):
        if value is None:
            return value
        firm = User.objects.filter(pk=value, role=User.Role.FIRM).first()
        if not firm:
            raise serializers.ValidationError("Invalid firm id or user is not a FIRM.")
        if not firm.is_verified:
            raise serializers.ValidationError("Firm is not verified.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        vehicle_type = validated_data.pop("vehicle_type")
        license_plate = validated_data.pop("license_plate")
        firm_id = validated_data.pop("firm_id", None)

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email") or "",
            phone_number=validated_data["phone_number"],
            password=password,
            role=User.Role.COURIER,
            is_verified=False,
        )
        CourierProfile.objects.create(
            user=user, firm_id=firm_id, vehicle_type=vehicle_type,
            license_plate=license_plate,
        )
        return user


class FirmProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = FirmProfile
        fields = ("id", "company_name", "firm_type", "tax_id", "address", "balance")
        read_only_fields = ("balance",)


class CourierProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    is_verified = serializers.BooleanField(source="user.is_verified", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    firm_id = serializers.IntegerField(read_only=True)
    firm_username = serializers.CharField(
        source="firm.username", read_only=True, default=None
    )

    class Meta:
        model = CourierProfile
        fields = (
            "id", "user_id", "username", "email", "phone_number",
            "is_verified", "is_active",
            "firm_id", "firm_username",
            "vehicle_type", "license_plate", "current_status", "balance",
        )
        read_only_fields = (
            "id", "user_id", "username", "email", "phone_number",
            "is_verified", "is_active", "firm_id", "firm_username", "balance",
        )


class PublicCourierProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)

    class Meta:
        model = CourierProfile
        fields = ("id", "username", "phone_number", "vehicle_type",
                  "license_plate", "current_status")


class CourierProfileWriteSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False)
    password = serializers.CharField(
        write_only=True, required=False, style={"input_type": "password"}
    )
    is_verified = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)
    firm_id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = CourierProfile
        fields = (
            "username", "email", "phone_number", "password",
            "is_verified", "is_active", "firm_id",
            "vehicle_type", "license_plate", "current_status", "balance",
        )

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_phone_number(self, value):
        qs = User.objects.filter(phone_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.user.pk)
        if qs.exists():
            raise serializers.ValidationError("Phone number already registered.")
        return value

    def validate_firm_id(self, value):
        if value is None:
            return value
        firm = User.objects.filter(pk=value, role=User.Role.FIRM).first()
        if not firm:
            raise serializers.ValidationError("Invalid firm id or user is not a FIRM.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password", None)
        username = validated_data.pop("username", None)
        email = validated_data.pop("email", "") or ""
        phone_number = validated_data.pop("phone_number", None)
        is_verified = validated_data.pop("is_verified", False)
        is_active = validated_data.pop("is_active", True)
        firm_id = validated_data.pop("firm_id", None)

        if not username or not phone_number or not password:
            raise serializers.ValidationError(
                "username, phone_number and password are required to create a courier."
            )
        user = User.objects.create_user(
            username=username, email=email, phone_number=phone_number,
            password=password, role=User.Role.COURIER, is_verified=is_verified,
        )
        user.is_active = is_active
        user.save(update_fields=["is_active"])
        return CourierProfile.objects.create(
            user=user, firm_id=firm_id, **validated_data
        )

    @transaction.atomic
    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        firm_id = validated_data.pop("firm_id", None)
        user = instance.user

        for attr in ("username", "email", "phone_number", "is_verified", "is_active"):
            if attr in validated_data:
                setattr(user, attr, validated_data.pop(attr))
        if password:
            user.set_password(password)
        user.save()

        if firm_id is not None:
            instance.firm_id = firm_id
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
            "id", "username", "email", "phone_number", "role",
            "is_verified", "is_active", "password", "date_joined",
            "firm_profile", "courier_profile",
        )
        read_only_fields = ("id", "date_joined", "firm_profile", "courier_profile")

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_phone_number(self, value):
        qs = User.objects.filter(phone_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Phone number already registered.")
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
        if "role" not in validated_data:
            validated_data["role"] = User.Role.FIRM
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        request = self.context.get("request")
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
