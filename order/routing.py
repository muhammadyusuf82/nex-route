from django.urls import re_path
from .consumers import OrderConsumer, AdminMonitorConsumer

websocket_urlpatterns = [
    re_path(r"ws/orders/$", OrderConsumer.as_asgi()),
    re_path(r"ws/admin/$", AdminMonitorConsumer.as_asgi()),
]
