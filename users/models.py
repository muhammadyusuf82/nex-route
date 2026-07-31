from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.
class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN="ADMIN", "System Admin"
        COURIER="COURIER", "Courier"
        FIRM="FIRM", "Firm"
        
    base_role = Role.ADMIN
    
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.FIRM)
    phone_number = models.CharField(max_length=20, unique=True)
    is_verified = models.BooleanField(default=False)
    
    def save(self, *args, **kwargs):
        if not self.pk and not self.role:
            self.role = self.base_role
        super().save(*args, **kwargs)
        
class FirmProfile(models.Model):
    class FirmType(models.TextChoices):
        FACTORY = "FACTORY", "Factory"
        MARKET = "MARKET", "Market"
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='firm_profile')
    company_name = models.CharField(max_length=255)
    firm_type = models.CharField(max_length=25, choices=FirmType.choices)
    tax_id = models.CharField(max_length=50, unique=True)
    address = models.TextField()
    
class CourierProfile(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        ON_DELIVERY = "ON_DELIVERY", "On Delivery"
        OFFLINE = "OFFLINE", "Offline"
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='courier_profile')
    vehiclie_type = models.CharField(max_length=50)
    license_plate = models.CharField(max_length=20)
    current_status = models.CharField(max_length=20, choices=Status.choices, default=Status.OFFLINE)