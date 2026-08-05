from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIRequestFactory
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .models import FirmProfile, CourierProfile
from .permissions import IsAdminUserRole, IsFirmUser, IsCourierUser
from .serializers import (
    FirmRegistrationSerializer,
    CourierRegistrationSerializer,
    CustomTokenObtainPairSerializer,
)

User = get_user_model()


class UserModelTests(TestCase):
    def test_create_user_defaults_to_firm_role(self):
        user = User.objects.create_user(
            username="firm1",
            password="pass12345",
            phone_number="+998901111111",
        )
        self.assertEqual(user.role, User.Role.FIRM)
        self.assertFalse(user.is_verified)

    def test_create_courier_user(self):
        user = User.objects.create_user(
            username="courier1",
            password="pass12345",
            phone_number="+998902222222",
            role=User.Role.COURIER,
        )
        self.assertEqual(user.role, User.Role.COURIER)

    def test_phone_number_unique(self):
        User.objects.create_user(
            username="a",
            password="pass12345",
            phone_number="+998903333333",
        )
        with self.assertRaises(Exception):
            User.objects.create_user(
                username="b",
                password="pass12345",
                phone_number="+998903333333",
            )

    def test_firm_profile_creation(self):
        user = User.objects.create_user(
            username="firm2",
            password="pass12345",
            phone_number="+998904444444",
            role=User.Role.FIRM,
        )
        profile = FirmProfile.objects.create(
            user=user,
            company_name="Acme",
            firm_type=FirmProfile.FirmType.FACTORY,
            tax_id="TAX001",
            address="Tashkent",
        )
        self.assertEqual(user.firm_profile.company_name, "Acme")
        self.assertEqual(profile.firm_type, FirmProfile.FirmType.FACTORY)

    def test_courier_profile_creation(self):
        user = User.objects.create_user(
            username="courier2",
            password="pass12345",
            phone_number="+998905555555",
            role=User.Role.COURIER,
        )
        profile = CourierProfile.objects.create(
            user=user,
            vehicle_type="van",
            license_plate="01A123BC",
        )
        self.assertEqual(user.courier_profile.license_plate, "01A123BC")
        self.assertEqual(profile.current_status, CourierProfile.Status.OFFLINE)
        self.assertEqual(profile.vehicle_type, "van")


class FirmRegistrationSerializerTests(TestCase):
    def test_firm_registration_creates_user_and_profile(self):
        data = {
            "username": "newfirm",
            "email": "firm@example.com",
            "phone_number": "+998906666666",
            "password": "securepass1",
            "company_name": "New Firm LLC",
            "firm_type": "MARKET",
            "tax_id": "TAX999",
            "address": "Samarkand",
        }
        serializer = FirmRegistrationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertEqual(user.role, User.Role.FIRM)
        self.assertFalse(user.is_verified)
        self.assertTrue(user.check_password("securepass1"))
        self.assertEqual(user.firm_profile.company_name, "New Firm LLC")
        self.assertEqual(user.firm_profile.tax_id, "TAX999")


class CourierRegistrationSerializerTests(TestCase):
    def test_courier_registration_creates_user_and_profile(self):
        data = {
            "username": "newcourier",
            "email": "courier@example.com",
            "phone_number": "+998907777777",
            "password": "securepass1",
            "vehicle_type": "motorcycle",
            "license_plate": "01B456DE",
        }
        serializer = CourierRegistrationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertEqual(user.role, User.Role.COURIER)
        self.assertFalse(user.is_verified)
        self.assertTrue(user.check_password("securepass1"))
        self.assertTrue(hasattr(user, "courier_profile"))
        self.assertEqual(user.courier_profile.license_plate, "01B456DE")


class PermissionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = User.objects.create_user(
            username="admin1",
            password="pass12345",
            phone_number="+998900000001",
            role=User.Role.ADMIN,
            is_verified=True,
        )
        self.firm = User.objects.create_user(
            username="firmperm",
            password="pass12345",
            phone_number="+998900000002",
            role=User.Role.FIRM,
            is_verified=True,
        )
        self.firm_unverified = User.objects.create_user(
            username="firmuv",
            password="pass12345",
            phone_number="+998900000003",
            role=User.Role.FIRM,
            is_verified=False,
        )
        self.courier = User.objects.create_user(
            username="courierperm",
            password="pass12345",
            phone_number="+998900000004",
            role=User.Role.COURIER,
            is_verified=True,
        )

    def _request(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def test_is_admin_user_role(self):
        perm = IsAdminUserRole()
        self.assertTrue(perm.has_permission(self._request(self.admin), None))
        self.assertFalse(perm.has_permission(self._request(self.firm), None))

    def test_is_firm_user_requires_verified(self):
        perm = IsFirmUser()
        self.assertTrue(perm.has_permission(self._request(self.firm), None))
        self.assertFalse(perm.has_permission(self._request(self.firm_unverified), None))
        self.assertFalse(perm.has_permission(self._request(self.courier), None))

    def test_is_courier_user(self):
        perm = IsCourierUser()
        self.assertTrue(perm.has_permission(self._request(self.courier), None))
        self.assertFalse(perm.has_permission(self._request(self.firm), None))


class AuthAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="loginuser",
            password="pass12345",
            phone_number="+998908888888",
            email="login@example.com",
            role=User.Role.FIRM,
            is_verified=True,
        )

    def test_token_obtain_pair(self):
        url = reverse("token_obtain_pair")
        response = self.client.post(
            url,
            {"username": "loginuser", "password": "pass12345"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["username"], "loginuser")
        self.assertEqual(response.data["user"]["role"], User.Role.FIRM)

    def test_token_obtain_invalid_credentials(self):
        url = reverse("token_obtain_pair")
        response = self.client.post(
            url,
            {"username": "loginuser", "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_refresh(self):
        refresh = RefreshToken.for_user(self.user)
        url = reverse("token_refresh")
        response = self.client.post(
            url, {"refresh": str(refresh)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_jwt_contains_custom_claims(self):
        refresh = CustomTokenObtainPairSerializer.get_token(self.user)
        self.assertEqual(refresh["role"], User.Role.FIRM)
        self.assertEqual(refresh["username"], "loginuser")
        self.assertTrue(refresh["is_verified"])


class FirmRegisterAPITests(APITestCase):
    def test_register_firm_success(self):
        url = reverse("register_firm")
        payload = {
            "username": "apifirm",
            "email": "apifirm@example.com",
            "phone_number": "+998909999001",
            "password": "securepass1",
            "company_name": "API Firm",
            "firm_type": "FACTORY",
            "tax_id": "TAXAPI1",
            "address": "Bukhara",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="apifirm")
        self.assertEqual(user.role, User.Role.FIRM)
        self.assertEqual(user.firm_profile.company_name, "API Firm")

    def test_register_firm_duplicate_username(self):
        User.objects.create_user(
            username="apifirm",
            password="pass12345",
            phone_number="+998909999002",
        )
        url = reverse("register_firm")
        payload = {
            "username": "apifirm",
            "email": "x@example.com",
            "phone_number": "+998909999003",
            "password": "securepass1",
            "company_name": "Dup",
            "firm_type": "MARKET",
            "tax_id": "TAXAPI2",
            "address": "Addr",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CourierRegisterAPITests(APITestCase):
    def test_register_courier_success(self):
        url = reverse("register_courier")
        payload = {
            "username": "apicourier",
            "email": "apicourier@example.com",
            "phone_number": "+998909999010",
            "password": "securepass1",
            "vehicle_type": "bike",
            "license_plate": "01C789FG",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            getattr(response, "data", response.content),
        )
        user = User.objects.get(username="apicourier")
        self.assertEqual(user.role, User.Role.COURIER)
        self.assertTrue(hasattr(user, "courier_profile"))

    def test_register_courier_missing_fields(self):
        url = reverse("register_courier")
        response = self.client.post(
            url, {"username": "incomplete"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class URLAndDocsSmokeTests(APITestCase):
    def test_swagger_ui_loads(self):
        response = self.client.get(reverse("swagger-ui"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_redoc_loads(self):
        response = self.client.get(reverse("redoc"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_schema_loads(self):
        response = self.client.get(reverse("schema"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_login_page(self):
        client = Client()
        response = client.get("/admin/login/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
