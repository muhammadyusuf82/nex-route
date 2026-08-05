from django.conf import settings
from django.db import models, transaction
from django.core.exceptions import ValidationError


class Item(models.Model):
    """A deliverable item with a pickup position."""

    name = models.CharField(max_length=255)
    position = models.CharField(
        max_length=512,
        help_text="Pickup location (address or lat,lng).",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="items",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.name


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        PICKED_UP = "PICKED_UP", "Picked Up"
        IN_TRANSIT = "IN_TRANSIT", "In Transit"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    TERMINAL_STATUSES = {Status.DELIVERED, Status.FAILED, Status.CANCELLED}

    ALLOWED_TRANSITIONS = {
        Status.PENDING: {Status.ACCEPTED, Status.CANCELLED},
        Status.ACCEPTED: {Status.PICKED_UP, Status.FAILED, Status.CANCELLED},
        Status.PICKED_UP: {Status.IN_TRANSIT, Status.FAILED},
        Status.IN_TRANSIT: {Status.DELIVERED, Status.FAILED},
        Status.DELIVERED: set(),
        Status.FAILED: set(),
        Status.CANCELLED: set(),
    }

    courier = models.ForeignKey(
        "users.CourierProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    item = models.ForeignKey(
        Item,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    target_position = models.CharField(
        max_length=512,
        help_text="Delivery destination (address or lat,lng).",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    status_description = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Order #{self.pk} [{self.status}]"

    def clean(self):
        if self.courier_id and self.status == self.Status.PENDING:
            raise ValidationError("Pending orders cannot have an assigned courier.")

    def transition_to(self, new_status, description="", courier=None):
        if new_status not in self.ALLOWED_TRANSITIONS.get(self.status, set()):
            raise ValidationError(
                f"Cannot transition from {self.status} to {new_status}."
            )
        self.status = new_status
        if description is not None:
            self.status_description = description
        if courier is not None:
            self.courier = courier
        self.save()
        return self

    @classmethod
    @transaction.atomic
    def accept_by_courier(cls, order_id, courier_profile):
        """Atomically accept a pending order (first courier wins)."""
        order = (
            cls.objects.select_for_update()
            .select_related("item", "courier", "created_by")
            .get(pk=order_id)
        )
        if order.status != cls.Status.PENDING:
            raise ValidationError("Order is no longer available.")
        if order.courier_id is not None:
            raise ValidationError("Order already assigned.")

        order.courier = courier_profile
        order.status = cls.Status.ACCEPTED
        order.status_description = "Order accepted by courier."
        order.save(update_fields=["courier", "status", "status_description", "updated_at"])

        courier_profile.current_status = courier_profile.Status.ON_DELIVERY
        courier_profile.save(update_fields=["current_status"])
        return order


class Todo(models.Model):
    """A task assigned by an admin or firm to a specific courier."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    title = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assigned_todos",
    )
    courier = models.ForeignKey(
        "users.CourierProfile",
        on_delete=models.CASCADE,
        related_name="todos",
    )
    scheduled_at = models.DateTimeField(
        help_text="When the courier should perform the task.",
    )
    region = models.CharField(max_length=128)
    city = models.CharField(max_length=128)
    street = models.CharField(max_length=255)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("scheduled_at",)

    def __str__(self):
        label = self.title or f"Todo #{self.pk}"
        return f"{label} → {self.courier.user.username}"

    def clean(self):
        if self.assigned_by.role not in (
            self.assigned_by.Role.ADMIN,
            self.assigned_by.Role.FIRM,
        ):
            raise ValidationError("Only admins or firms can assign todos.")
        if self.assigned_by.role == self.assigned_by.Role.FIRM and not self.assigned_by.is_verified:
            raise ValidationError("Firm must be verified to assign todos.")
        if not self.courier.user.is_verified or not self.courier.user.is_active:
            raise ValidationError("Courier must be active and verified.")
        if not (-90 <= float(self.latitude) <= 90):
            raise ValidationError("Latitude must be between -90 and 90.")
        if not (-180 <= float(self.longitude) <= 180):
            raise ValidationError("Longitude must be between -180 and 180.")
