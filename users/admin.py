from django.contrib import admin
from .models import User, FirmProfile, CourierProfile


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "role", "phone_number", "is_verified", "is_active")
    list_filter = ("role", "is_verified", "is_active")
    search_fields = ("username", "email", "phone_number")


@admin.register(FirmProfile)
class FirmProfileAdmin(admin.ModelAdmin):
    list_display = ("company_name", "firm_type", "tax_id", "user")


@admin.register(CourierProfile)
class CourierProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "vehicle_type", "license_plate", "current_status")
    list_filter = ("current_status",)
