from rest_framework import serializers
from django.contrib.auth import get_user_model

from users.models import CourierProfile
from .models import Item, Order, Todo

User = get_user_model()


class ItemSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = Item
        fields = (
            "id",
            "name",
            "position",
            "owner",
            "owner_username",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "owner", "owner_username", "created_at", "updated_at")


class OrderSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_position = serializers.CharField(source="item.position", read_only=True)
    courier_username = serializers.CharField(
        source="courier.user.username", read_only=True, default=None
    )
    directions = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "courier",
            "courier_username",
            "item",
            "item_name",
            "item_position",
            "target_position",
            "status",
            "status_description",
            "created_by",
            "directions",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_directions(self, obj):
        return {
            "pickup": obj.item.position,
            "destination": obj.target_position,
        }


class TodoSerializer(serializers.ModelSerializer):
    assigned_by_username = serializers.CharField(
        source="assigned_by.username", read_only=True
    )
    courier_username = serializers.CharField(
        source="courier.user.username", read_only=True
    )
    address = serializers.SerializerMethodField()

    class Meta:
        model = Todo
        fields = (
            "id",
            "title",
            "description",
            "assigned_by",
            "assigned_by_username",
            "courier",
            "courier_username",
            "scheduled_at",
            "region",
            "city",
            "street",
            "longitude",
            "latitude",
            "address",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_address(self, obj):
        return {
            "region": obj.region,
            "city": obj.city,
            "street": obj.street,
            "longitude": str(obj.longitude),
            "latitude": str(obj.latitude),
        }


class TodoWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Todo
        fields = (
            "title",
            "description",
            "courier",
            "scheduled_at",
            "region",
            "city",
            "street",
            "longitude",
            "latitude",
            "status",
        )

    def validate_courier(self, value):
        if not value.user.is_verified or not value.user.is_active:
            raise serializers.ValidationError("Courier must be active and verified.")
        return value

    def validate_longitude(self, value):
        if not (-180 <= float(value) <= 180):
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        return value

    def validate_latitude(self, value):
        if not (-90 <= float(value) <= 90):
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_status(self, value):
        request = self.context.get("request")
        if request and request.user.role == User.Role.COURIER:
            allowed = {Todo.Status.IN_PROGRESS, Todo.Status.COMPLETED}
            if value not in allowed:
                raise serializers.ValidationError(
                    "Couriers may only set status to IN_PROGRESS or COMPLETED."
                )
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None

        if user and user.role == User.Role.COURIER:
            disallowed = {"courier", "scheduled_at", "region", "city", "street", "longitude", "latitude", "title", "description"}
            if self.instance is None:
                raise serializers.ValidationError("Couriers cannot create todos.")
            for field in disallowed:
                if field in attrs:
                    raise serializers.ValidationError(
                        {field: "Couriers cannot modify this field."}
                    )
        return attrs

    def create(self, validated_data):
        validated_data["assigned_by"] = self.context["request"].user
        return super().create(validated_data)


class TodoCourierStatusSerializer(serializers.ModelSerializer):
    """Couriers may only update task status."""

    class Meta:
        model = Todo
        fields = ("status",)

    def validate_status(self, value):
        allowed = {Todo.Status.IN_PROGRESS, Todo.Status.COMPLETED}
        if value not in allowed:
            raise serializers.ValidationError(
                "Allowed values: IN_PROGRESS, COMPLETED."
            )
        if self.instance.status in (Todo.Status.COMPLETED, Todo.Status.CANCELLED):
            raise serializers.ValidationError("This todo can no longer be updated.")
        return value
