"""
WebSocket consumers for order lifecycle.

Endpoints (JWT required via ?token=<access_jwt>):
  ws/orders/   — firms create orders; couriers accept & update status
  ws/admin/    — admins receive real-time feed of all order/courier events
"""

from __future__ import annotations

import json
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, ObjectDoesNotExist

from .models import Item, Order
from .serializers import OrderSerializer

User = get_user_model()

COURIERS_GROUP = "couriers"
ADMINS_GROUP = "admins"


def _order_payload(order: Order) -> dict[str, Any]:
    return OrderSerializer(order).data


class AuthenticatedConsumer(AsyncJsonWebsocketConsumer):
    """Base consumer: requires authenticated user on scope (JWT middleware)."""

    required_roles: set[str] = set()
    require_verified: bool = True

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        if self.required_roles and user.role not in self.required_roles:
            await self.close(code=4403)
            return
        if self.require_verified and user.role != User.Role.ADMIN and not user.is_verified:
            await self.close(code=4403)
            return
        await self.accept()

    async def send_error(self, message: str, code: str = "error"):
        await self.send_json({"type": "error", "code": code, "detail": message})


class OrderConsumer(AuthenticatedConsumer):
    """
    Firm / Admin / Courier shared order channel.

    Firm/Admin actions:
      {"action": "create_order", "item_id": 1, "target_position": "..."}

    Courier actions:
      {"action": "accept_order", "order_id": 1}
      {"action": "update_status", "order_id": 1, "status": "IN_TRANSIT",
       "status_description": "...", "position": "optional current location"}
    """

    required_roles = {User.Role.FIRM, User.Role.COURIER, User.Role.ADMIN}

    async def connect(self):
        await super().connect()
        if self.scope.get("user") is None or not self.scope["user"].is_authenticated:
            return

        user = self.scope["user"]
        self.user_group = f"user_{user.id}"
        await self.channel_layer.group_add(self.user_group, self.channel_name)

        if user.role == User.Role.COURIER:
            await self.channel_layer.group_add(COURIERS_GROUP, self.channel_name)
        if user.role == User.Role.ADMIN:
            await self.channel_layer.group_add(ADMINS_GROUP, self.channel_name)

    async def disconnect(self, close_code):
        user = self.scope.get("user")
        if user and user.is_authenticated:
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
            if user.role == User.Role.COURIER:
                await self.channel_layer.group_discard(COURIERS_GROUP, self.channel_name)
            if user.role == User.Role.ADMIN:
                await self.channel_layer.group_discard(ADMINS_GROUP, self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = content.get("action")
        handlers = {
            "create_order": self.handle_create_order,
            "accept_order": self.handle_accept_order,
            "update_status": self.handle_update_status,
        }
        handler = handlers.get(action)
        if not handler:
            await self.send_error("Unknown or missing action.", "invalid_action")
            return
        try:
            await handler(content)
        except ValidationError as exc:
            await self.send_error(self._format_validation(exc))
        except ObjectDoesNotExist:
            await self.send_error("Resource not found.", "not_found")
        except PermissionError as exc:
            await self.send_error(str(exc) or "Forbidden.", "forbidden")
        except Exception:
            await self.send_error("Internal server error.", "server_error")

    @staticmethod
    def _format_validation(exc: ValidationError) -> str:
        if hasattr(exc, "messages"):
            return "; ".join(str(m) for m in exc.messages)
        return str(exc)

    async def handle_create_order(self, content: dict):
        user = self.scope["user"]
        if user.role not in (User.Role.FIRM, User.Role.ADMIN):
            raise PermissionError("Only firms or admins can create orders.")

        item_id = content.get("item_id")
        target_position = (content.get("target_position") or "").strip()
        if not item_id or not target_position:
            raise ValidationError("item_id and target_position are required.")
        if len(target_position) > 512:
            raise ValidationError("target_position is too long.")

        order = await self._create_order(user.id, int(item_id), target_position, user.role)
        payload = await database_sync_to_async(_order_payload)(order)

        # Notify available couriers (order created → courier notified)
        await self.channel_layer.group_send(
            COURIERS_GROUP,
            {
                "type": "order.offered",
                "order": payload,
            },
        )
        await self.channel_layer.group_send(
            ADMINS_GROUP,
            {
                "type": "admin.event",
                "event": "order_created",
                "order": payload,
            },
        )
        await self.send_json({"type": "order_created", "order": payload})

    async def handle_accept_order(self, content: dict):
        user = self.scope["user"]
        if user.role != User.Role.COURIER:
            raise PermissionError("Only couriers can accept orders.")

        order_id = content.get("order_id")
        if not order_id:
            raise ValidationError("order_id is required.")

        order = await self._accept_order(int(order_id), user.id)
        payload = await database_sync_to_async(_order_payload)(order)

        # Directions for the accepting courier
        await self.send_json(
            {
                "type": "order_accepted",
                "order": payload,
                "directions": {
                    "pickup": payload["item_position"],
                    "destination": payload["target_position"],
                },
            }
        )
        # Notify other couriers the offer is gone
        await self.channel_layer.group_send(
            COURIERS_GROUP,
            {
                "type": "order.taken",
                "order_id": order.id,
                "accepted_by": user.id,
            },
        )
        await self.channel_layer.group_send(
            ADMINS_GROUP,
            {
                "type": "admin.event",
                "event": "order_accepted",
                "order": payload,
            },
        )
        # Notify order creator
        await self.channel_layer.group_send(
            f"user_{order.created_by_id}",
            {
                "type": "order.update",
                "event": "order_accepted",
                "order": payload,
            },
        )

    async def handle_update_status(self, content: dict):
        user = self.scope["user"]
        if user.role != User.Role.COURIER:
            raise PermissionError("Only couriers can update delivery status.")

        order_id = content.get("order_id")
        new_status = content.get("status")
        description = content.get("status_description", "")
        position = content.get("position")

        if not order_id or not new_status:
            raise ValidationError("order_id and status are required.")
        if description and len(str(description)) > 2000:
            raise ValidationError("status_description is too long.")
        if position and len(str(position)) > 512:
            raise ValidationError("position is too long.")

        order = await self._update_status(
            int(order_id), user.id, new_status, str(description or ""), position
        )
        payload = await database_sync_to_async(_order_payload)(order)

        event = {
            "type": "order.update",
            "event": "status_updated",
            "order": payload,
            "courier_position": position,
        }
        await self.send_json({"type": "status_updated", "order": payload})
        await self.channel_layer.group_send(ADMINS_GROUP, {
            "type": "admin.event",
            "event": "status_updated",
            "order": payload,
            "courier_position": position,
        })
        await self.channel_layer.group_send(f"user_{order.created_by_id}", event)

    # ---- channel event handlers ----

    async def order_offered(self, event):
        await self.send_json({"type": "order_offered", "order": event["order"]})

    async def order_taken(self, event):
        # Accepting courier already received order_accepted; skip echo
        if self.scope["user"].id == event.get("accepted_by"):
            return
        await self.send_json({"type": "order_taken", "order_id": event["order_id"]})

    async def order_update(self, event):
        await self.send_json({
            "type": event.get("event", "order_update"),
            "order": event.get("order"),
            "courier_position": event.get("courier_position"),
        })

    async def admin_event(self, event):
        # Admins connected to /ws/orders/ also receive admin events
        await self.send_json({
            "type": event.get("event", "admin_event"),
            "order": event.get("order"),
            "courier_position": event.get("courier_position"),
        })

    # ---- DB helpers ----

    @database_sync_to_async
    def _create_order(self, user_id, item_id, target_position, role):
        user = User.objects.get(pk=user_id)
        item = Item.objects.select_related("owner").get(pk=item_id)
        if role == User.Role.FIRM and item.owner_id != user.id:
            raise PermissionError("You can only create orders for your own items.")
        return Order.objects.create(
            item=item,
            target_position=target_position,
            created_by=user,
            status=Order.Status.PENDING,
            status_description="Awaiting courier acceptance.",
        )

    @database_sync_to_async
    def _accept_order(self, order_id, user_id):
        user = User.objects.select_related("courier_profile").get(pk=user_id)
        if not hasattr(user, "courier_profile"):
            raise ValidationError("Courier profile is missing.")
        return Order.accept_by_courier(order_id, user.courier_profile)

    @database_sync_to_async
    def _update_status(self, order_id, user_id, new_status, description, position):
        from users.models import CourierProfile

        order = (
            Order.objects.select_related("item", "courier__user", "created_by")
            .get(pk=order_id)
        )
        user = User.objects.select_related("courier_profile").get(pk=user_id)
        if not order.courier_id or order.courier.user_id != user.id:
            raise PermissionError("You are not assigned to this order.")

        valid = {c.value for c in Order.Status}
        if new_status not in valid:
            raise ValidationError(f"Invalid status. Allowed: {sorted(valid)}")

        # Couriers cannot set PENDING/CANCELLED arbitrarily after accept
        if new_status == Order.Status.PENDING:
            raise ValidationError("Cannot revert to PENDING.")
        if new_status == Order.Status.ACCEPTED and order.status != Order.Status.ACCEPTED:
            raise ValidationError("Use accept_order to accept.")

        order.transition_to(new_status, description=description)

        if new_status in Order.TERMINAL_STATUSES:
            profile = user.courier_profile
            profile.current_status = CourierProfile.Status.AVAILABLE
            profile.save(update_fields=["current_status"])

        return order


class AdminMonitorConsumer(AuthenticatedConsumer):
    """Real-time admin dashboard of all order and courier activity."""

    required_roles = {User.Role.ADMIN}
    require_verified = False

    async def connect(self):
        await super().connect()
        if self.scope.get("user") is None or not self.scope["user"].is_authenticated:
            return
        await self.channel_layer.group_add(ADMINS_GROUP, self.channel_name)
        # Snapshot of active orders
        snapshot = await self._active_snapshot()
        await self.send_json({"type": "snapshot", "orders": snapshot})

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(ADMINS_GROUP, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Admins may request a fresh snapshot
        if content.get("action") == "snapshot":
            snapshot = await self._active_snapshot()
            await self.send_json({"type": "snapshot", "orders": snapshot})
        else:
            await self.send_error("Unknown action.", "invalid_action")

    async def admin_event(self, event):
        await self.send_json({
            "type": event.get("event", "admin_event"),
            "order": event.get("order"),
            "courier_position": event.get("courier_position"),
        })

    @database_sync_to_async
    def _active_snapshot(self):
        orders = (
            Order.objects.exclude(status__in=Order.TERMINAL_STATUSES)
            .select_related("item", "courier__user", "created_by")
        )
        return [_order_payload(o) for o in orders]
