from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError
from urllib.parse import parse_qs

User = get_user_model()


@database_sync_to_async
def _user_from_token(token: str):
    try:
        access = AccessToken(token)
        user_id = access.get("user_id")
        if not user_id:
            return AnonymousUser()
        return User.objects.get(pk=user_id, is_active=True)
    except (TokenError, User.DoesNotExist, KeyError):
        return AnonymousUser()


class JwtAuthMiddleware(BaseMiddleware):
    """
    Authenticate WebSocket connections with a JWT access token.

    Pass token as query parameter: ws://host/ws/...?token=<access>
    Do not log full URLs containing tokens in production reverse proxies.
    """

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            query = parse_qs(scope.get("query_string", b"").decode())
            raw = query.get("token", [None])[0]
            if raw:
                scope["user"] = await _user_from_token(raw)
            else:
                scope["user"] = AnonymousUser()
        return await super().__call__(scope, receive, send)


def JwtAuthMiddlewareStack(inner):
    return JwtAuthMiddleware(inner)
