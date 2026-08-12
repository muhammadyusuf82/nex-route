from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "System Admin"
        COURIER = "COURIER", "Courier"
        FIRM = "FIRM", "Firm"

    role = models.CharField(max_length=20, choices=Role.choices)
    phone_number = models.CharField(max_length=20, unique=True)
    is_verified = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["is_verified"]),
        ]


class FirmProfile(models.Model):
    class FirmType(models.TextChoices):
        FACTORY = "FACTORY", "Factory"
        MARKET = "MARKET", "Market"

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="firm_profile"
    )
    company_name = models.CharField(max_length=255)
    firm_type = models.CharField(max_length=25, choices=FirmType.choices)
    tax_id = models.CharField(max_length=50, unique=True)
    address = models.TextField()
    balance = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    class Meta:
        indexes = [models.Index(fields=["firm_type"])]

    def clean(self):
        super().clean()
        if self.user_id and self.user.role != User.Role.FIRM:
            raise ValidationError("FirmProfile must belong to a User with role=FIRM.")

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["balance"] if kwargs.get("update_fields") else None)
        super().save(*args, **kwargs)


class CourierProfile(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        ON_DELIVERY = "ON_DELIVERY", "On Delivery"
        OFFLINE = "OFFLINE", "Offline"

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="courier_profile"
    )
    firm = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="couriers",
        limit_choices_to={"role": "FIRM"},
        null=True,
        blank=True,
    )
    vehicle_type = models.CharField(max_length=50)
    license_plate = models.CharField(max_length=20)
    current_status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OFFLINE
    )
    balance = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    class Meta:
        indexes = [
            models.Index(fields=["firm"]),
            models.Index(fields=["current_status"]),
        ]

    def clean(self):
        super().clean()
        if self.user_id and self.user.role != User.Role.COURIER:
            raise ValidationError(
                "CourierProfile must belong to a User with role=COURIER."
            )
        if self.firm_id:
            if self.firm.role != User.Role.FIRM:
                raise ValidationError("firm must be a User with role=FIRM.")
            if not self.firm.is_verified:
                raise ValidationError("Cannot attach courier to an unverified firm.")

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["balance"] if kwargs.get("update_fields") else None)
        super().save(*args, **kwargs)
