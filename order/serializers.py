from rest_framework import serializers
from django.contrib.auth import get_user_model
from .geolocation import get_street_data_from_lat_and_lon
from .models import Item, Order, Todo

User = get_user_model()


class ItemSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = Item
        fields = ("id", "name", "position", "owner", "owner_username",
                  "created_at", "updated_at")
        read_only_fields = ("id", "owner", "owner_username", "created_at", "updated_at")


class OrderSerializer(serializers.ModelSerializer):
    """Read-only serializer used by WebSocket layer."""
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_position = serializers.CharField(source="item.position", read_only=True)
    courier_username = serializers.CharField(
        source="courier.user.username", read_only=True, default=None
    )
    directions = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ("id", "courier", "courier_username", "item", "item_name",
                  "item_position", "target_position", "status",
                  "status_description", "created_by", "directions",
                  "created_at", "updated_at")
        read_only_fields = fields

    def get_directions(self, obj):
        return {"pickup": obj.item.position, "destination": obj.target_position}


class TodoSerializer(serializers.ModelSerializer):
    assigned_by_username = serializers.CharField(source="assigned_by.username", read_only=True)
    courier_username = serializers.CharField(source="courier.user.username", read_only=True)
    firm_username = serializers.CharField(source="firm.username", read_only=True, default=None)
    address = serializers.SerializerMethodField()

    class Meta:
        model = Todo
        fields = ("id", "title", "description", "assigned_by", "assigned_by_username",
                  "firm", "firm_username", "courier", "courier_username",
                  "scheduled_at", "region", "city", "street", "longitude", "latitude",
                  "address", "status", "created_at", "updated_at")
        read_only_fields = fields

    def get_address(self, obj):
        return {"region": obj.region, "city": obj.city, "street": obj.street,
                "longitude": str(obj.longitude), "latitude": str(obj.latitude)}


class TodoWriteSerializer(serializers.ModelSerializer):
    region = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    street = serializers.CharField(required=False, allow_blank=True)
    class Meta:
        model = Todo
        fields = ("title", "description", "courier", "firm", "scheduled_at",
                  "region", "city", "street", "longitude", "latitude", "status")

    def validate_courier(self, value):
        if not value.user.is_verified or not value.user.is_active:
            raise serializers.ValidationError("Courier must be active and verified.")
        request = self.context.get("request")
        user = request.user if request else None
        
        if user and getattr(user, "role", None) == User.Role.FIRM:
            if getattr(value, "firm_id", None) != user.id:
                raise serializers.ValidationError("You can only assign tasks to couriers of your own firm.")
        return value

    def validate_longitude(self, value):
        if not (-180 <= float(value) <= 180):
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        return value

    def validate_latitude(self, value):
        if not (-90 <= float(value) <= 90):
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None
        role = getattr(user, "role", None)

        if role == User.Role.FIRM and "firm" in attrs and attrs["firm"] != user:
            raise serializers.ValidationError({"firm": "Firms may not assign on behalf of others."})
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["assigned_by"] = request.user
        if getattr(request.user, "role", None) == User.Role.FIRM and not validated_data.get("firm"):
            validated_data["firm"] = request.user
            
        lat = validated_data.get("latitude")
        lon = validated_data.get("longtitude")
        
        if lat is not None and lon is not None:
            address_data = get_street_data_from_lat_and_lon(float(lat), float(lon))
            if address_data: 
                validated_data["region"] = address_data.get("region") or validated_data.get("region", "")
                validated_data["city"] = address_data.get("city") or validated_data.get("city", "")
                validated_data["street"] = address_data.get("street") or validated_data.get("street", "")
        return super().create(validated_data)

class TodoCourierStatusSerializer(serializers.ModelSerializer):
    """Couriers may only update task status."""

    class Meta:
        model = Todo
        fields = ("status",)

    def validate_status(self, value):
        allowed = {Todo.Status.IN_PROGRESS, Todo.Status.COMPLETED}
        if value not in allowed:
            raise serializers.ValidationError("Allowed values: IN_PROGRESS, COMPLETED.")
        current = getattr(self.instance, "status", None)
        if current in Todo.TERMINAL_STATUSES:
            raise serializers.ValidationError("This todo can no longer be updated.")
        return value