from django.conf import settings
from django.db import models, transaction
from django.core.exceptions import ValidationError


class Item(models.Model):
    name = models.CharField(max_length=255)
    position = models.CharField(max_length=512, help_text="Pickup location (address or lat,lng).")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="items",
        limit_choices_to={"role": "FIRM"},   # опционально
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
        Status.PENDING:    {Status.ACCEPTED, Status.CANCELLED},
        Status.ACCEPTED:   {Status.PICKED_UP, Status.FAILED, Status.CANCELLED},
        Status.PICKED_UP:  {Status.IN_TRANSIT, Status.FAILED},
        Status.IN_TRANSIT: {Status.DELIVERED, Status.FAILED},
        Status.DELIVERED:  set(),
        Status.FAILED:     set(),
        Status.CANCELLED:  set(),
    }

    courier = models.ForeignKey(
        "users.CourierProfile",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="orders",
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="orders")
    target_position = models.CharField(max_length=512)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
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
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["courier", "status"]),
        ]

    def __str__(self):
        return f"Order #{self.pk} [{self.status}]"

    def clean(self):
        if self.courier_id and self.status == self.Status.PENDING:
            raise ValidationError("Pending orders cannot have an assigned courier.")

    def transition_to(self, new_status, description="", courier=None):
        if new_status not in self.ALLOWED_TRANSITIONS.get(self.status, set()):
            raise ValidationError(f"Cannot transition from {self.status} to {new_status}.")
        self.status = new_status
        if description is not None:
            self.status_description = description
        if courier is not None:
            self.courier = courier
        self.full_clean(exclude=None)
        self.save()
        return self

    @classmethod
    @transaction.atomic
    def accept_by_courier(cls, order_id, courier_profile):
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
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    TERMINAL_STATUSES = {Status.COMPLETED, Status.CANCELLED}

    title = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assigned_todos",
    )
    # Явная связь с фирмой (даже если создаёт админ — можно указать, "от имени какой фирмы")
    firm = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="firm_todos",
        null=True, blank=True,
        limit_choices_to={"role": "FIRM"},
        help_text="Firm this task belongs to. Auto-set when the assigner is a FIRM.",
    )
    courier = models.ForeignKey(
        "users.CourierProfile",
        on_delete=models.CASCADE,
        related_name="todos",
    )
    scheduled_at = models.DateTimeField()
    region = models.CharField(max_length=128)
    city = models.CharField(max_length=128)
    street = models.CharField(max_length=255)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("scheduled_at",)
        indexes = [
            models.Index(fields=["courier", "status"]),
            models.Index(fields=["firm"]),
        ]

    def __str__(self):
        label = self.title or f"Todo #{self.pk}"
        return f"{label} → {self.courier.user.username}"

    def clean(self):
        super().clean()
        from django.contrib.auth import get_user_model
        User = get_user_model()

        if getattr(self, "assigned_by_id", None):
            if self.assigned_by.role not in (User.Role.ADMIN, User.Role.FIRM):
                raise ValidationError("Only admins or firms can assign todos.")
            if self.assigned_by.role == User.Role.FIRM and not self.assigned_by.is_verified:
                raise ValidationError("Firm must be verified to assign todos.")

        if getattr(self, "courier_id", None):
            if not self.courier.user.is_verified or not self.courier.user.is_active:
                raise ValidationError("Courier must be active and verified.")
            # Проверка, что курьер принадлежит указанной фирме
            if self.firm_id and getattr(self.courier, "firm_id", None) != self.firm_id:
                raise ValidationError("Courier does not belong to the specified firm.")

        if self.latitude is not None and not (-90 <= float(self.latitude) <= 90):
            raise ValidationError({"latitude": "Latitude must be between -90 and 90."})
        if self.longitude is not None and not (-180 <= float(self.longitude) <= 180):
            raise ValidationError({"longitude": "Longitude must be between -180 and 180."})

    def save(self, *args, **kwargs):
        # Автоматически проставляем firm, если задачу создаёт фирма
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if self.assigned_by_id and not self.firm_id:
            if self.assigned_by.role == User.Role.FIRM:
                self.firm = self.assigned_by
            elif self.courier_id and getattr(self.courier, "firm_id", None):
                self.firm = self.courier.firm
        super().save(*args, **kwargs)
