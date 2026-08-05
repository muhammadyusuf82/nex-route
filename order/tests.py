from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken

from users.models import CourierProfile, FirmProfile
from order.models import Item, Order
from core.asgi import application

User = get_user_model()


class ItemModelTests(TestCase):
    def setUp(self):
        self.firm = User.objects.create_user(
            username="firm_item",
            password="securepass1",
            phone_number="+998910000001",
            role=User.Role.FIRM,
            is_verified=True,
        )

    def test_create_item(self):
        item = Item.objects.create(
            name="Parcel A",
            position="41.3,69.2",
            owner=self.firm,
        )
        self.assertEqual(str(item), "Parcel A")
        self.assertEqual(item.owner, self.firm)


class OrderModelTests(TestCase):
    def setUp(self):
        self.firm = User.objects.create_user(
            username="firm_ord",
            password="securepass1",
            phone_number="+998910000002",
            role=User.Role.FIRM,
            is_verified=True,
        )
        self.courier_user = User.objects.create_user(
            username="cour_ord",
            password="securepass1",
            phone_number="+998910000003",
            role=User.Role.COURIER,
            is_verified=True,
        )
        self.courier = CourierProfile.objects.create(
            user=self.courier_user,
            vehicle_type="van",
            license_plate="01X111AA",
            current_status=CourierProfile.Status.AVAILABLE,
        )
        self.item = Item.objects.create(
            name="Box",
            position="Warehouse 1",
            owner=self.firm,
        )

    def test_accept_order(self):
        order = Order.objects.create(
            item=self.item,
            target_position="Client HQ",
            created_by=self.firm,
        )
        accepted = Order.accept_by_courier(order.id, self.courier)
        self.assertEqual(accepted.status, Order.Status.ACCEPTED)
        self.assertEqual(accepted.courier_id, self.courier.id)
        self.courier.refresh_from_db()
        self.assertEqual(self.courier.current_status, CourierProfile.Status.ON_DELIVERY)

    def test_invalid_transition(self):
        order = Order.objects.create(
            item=self.item,
            target_position="Client HQ",
            created_by=self.firm,
        )
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            order.transition_to(Order.Status.DELIVERED)


class ItemAPITests(APITestCase):
    def setUp(self):
        self.firm = User.objects.create_user(
            username="firm_api",
            password="securepass1",
            phone_number="+998910000010",
            role=User.Role.FIRM,
            is_verified=True,
        )
        self.other = User.objects.create_user(
            username="firm_other",
            password="securepass1",
            phone_number="+998910000011",
            role=User.Role.FIRM,
            is_verified=True,
        )
        self.admin = User.objects.create_user(
            username="admin_api",
            password="securepass1",
            phone_number="+998910000012",
            role=User.Role.ADMIN,
            is_verified=True,
        )

    def test_firm_crud_own_items(self):
        self.client.force_authenticate(self.firm)
        create = self.client.post(
            "/api/items/",
            {"name": "Laptop", "position": "Office A"},
            format="json",
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        item_id = create.data["id"]

        listing = self.client.get("/api/items/")
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listing.data), 1)

        self.client.force_authenticate(self.other)
        forbidden = self.client.patch(
            f"/api/items/{item_id}/",
            {"name": "Hacked"},
            format="json",
        )
        self.assertEqual(forbidden.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_denied(self):
        response = self.client.get("/api/items/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserCourierAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin_crud",
            password="securepass1",
            phone_number="+998910000020",
            role=User.Role.ADMIN,
        )
        self.user = User.objects.create_user(
            username="normal_user",
            password="securepass1",
            phone_number="+998910000021",
            role=User.Role.FIRM,
            is_verified=True,
        )

    def test_user_cannot_list_others(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/users/accounts/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["username"], "normal_user")

    def test_admin_creates_courier(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/users/couriers/",
            {
                "username": "newcour",
                "phone_number": "+998910000022",
                "password": "securepass1",
                "vehicle_type": "bike",
                "license_plate": "01Y222BB",
                "is_verified": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="newcour", role=User.Role.COURIER).exists())

    def test_non_admin_cannot_create_courier(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/users/couriers/",
            {
                "username": "x",
                "phone_number": "+998910000023",
                "password": "securepass1",
                "vehicle_type": "bike",
                "license_plate": "01Z",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class OrderWebSocketTests(TransactionTestCase):
    def setUp(self):
        self.firm = User.objects.create_user(
            username="ws_firm",
            password="securepass1",
            phone_number="+998910000030",
            role=User.Role.FIRM,
            is_verified=True,
        )
        self.courier_user = User.objects.create_user(
            username="ws_cour",
            password="securepass1",
            phone_number="+998910000031",
            role=User.Role.COURIER,
            is_verified=True,
        )
        self.courier = CourierProfile.objects.create(
            user=self.courier_user,
            vehicle_type="van",
            license_plate="01W333CC",
            current_status=CourierProfile.Status.AVAILABLE,
        )
        self.admin = User.objects.create_user(
            username="ws_admin",
            password="securepass1",
            phone_number="+998910000032",
            role=User.Role.ADMIN,
        )
        self.item = Item.objects.create(
            name="WS Item",
            position="Pickup Point",
            owner=self.firm,
        )

    def _token(self, user):
        return str(AccessToken.for_user(user))

    async def test_order_flow(self):
        firm_token = self._token(self.firm)
        courier_token = self._token(self.courier_user)
        admin_token = self._token(self.admin)

        firm_ws = WebsocketCommunicator(application, f"/ws/orders/?token={firm_token}")
        courier_ws = WebsocketCommunicator(application, f"/ws/orders/?token={courier_token}")
        admin_ws = WebsocketCommunicator(application, f"/ws/admin/?token={admin_token}")

        self.assertTrue((await firm_ws.connect())[0])
        self.assertTrue((await courier_ws.connect())[0])
        connected, _ = await admin_ws.connect()
        self.assertTrue(connected)

        # admin snapshot
        snap = await admin_ws.receive_json_from()
        self.assertEqual(snap["type"], "snapshot")

        await firm_ws.send_json_to(
            {
                "action": "create_order",
                "item_id": self.item.id,
                "target_position": "Delivery Gate",
            }
        )
        created = await firm_ws.receive_json_from()
        self.assertEqual(created["type"], "order_created")
        order_id = created["order"]["id"]

        offered = await courier_ws.receive_json_from()
        self.assertEqual(offered["type"], "order_offered")

        admin_created = await admin_ws.receive_json_from()
        self.assertEqual(admin_created["type"], "order_created")

        await courier_ws.send_json_to({"action": "accept_order", "order_id": order_id})
        accepted = await courier_ws.receive_json_from()
        self.assertEqual(accepted["type"], "order_accepted")
        self.assertEqual(accepted["directions"]["pickup"], "Pickup Point")
        self.assertEqual(accepted["directions"]["destination"], "Delivery Gate")

        await courier_ws.send_json_to(
            {
                "action": "update_status",
                "order_id": order_id,
                "status": "PICKED_UP",
                "status_description": "Package collected",
                "position": "Warehouse exit",
            }
        )
        updated = await courier_ws.receive_json_from()
        self.assertEqual(updated["type"], "status_updated")
        self.assertEqual(updated["order"]["status"], "PICKED_UP")

        admin_status = await admin_ws.receive_json_from()
        # may receive order_accepted first if buffered; drain until status
        while admin_status.get("type") != "status_updated":
            admin_status = await admin_ws.receive_json_from()
        self.assertEqual(admin_status["order"]["status"], "PICKED_UP")

        await firm_ws.disconnect()
        await courier_ws.disconnect()
        await admin_ws.disconnect()

    async def test_unauthenticated_ws_rejected(self):
        ws = WebsocketCommunicator(application, "/ws/orders/")
        connected, code = await ws.connect()
        self.assertFalse(connected)

    async def test_courier_cannot_create_order(self):
        token = self._token(self.courier_user)
        ws = WebsocketCommunicator(application, f"/ws/orders/?token={token}")
        self.assertTrue((await ws.connect())[0])
        await ws.send_json_to(
            {
                "action": "create_order",
                "item_id": self.item.id,
                "target_position": "X",
            }
        )
        err = await ws.receive_json_from()
        self.assertEqual(err["type"], "error")
        self.assertEqual(err["code"], "forbidden")
        await ws.disconnect()
