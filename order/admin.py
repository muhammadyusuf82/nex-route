from django.contrib import admin
from .models import Item, Order, Todo


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "position", "owner", "created_at")
    search_fields = ("name", "position", "owner__username")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "item", "courier", "status", "target_position", "created_at")
    list_filter = ("status",)
    search_fields = ("item__name", "target_position", "status_description")


@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "courier",
        "assigned_by",
        "scheduled_at",
        "city",
        "status",
    )
    list_filter = ("status", "region", "city")
    search_fields = ("title", "region", "city", "street", "courier__user__username")
