from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async, close_old_connections
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
    except (TokenError, User.DoesNotExist):
        return AnonymousUser()


class JwtAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        # Закрываем "протухшие" соединения к БД перед каждой новой сессией
        close_old_connections()

        if scope["type"] == "websocket":
            query = parse_qs(scope.get("query_string", b"").decode())
            raw = query.get("token", [None])[0]
            scope["user"] = await _user_from_token(raw) if raw else AnonymousUser()
        else:
            scope.setdefault("user", AnonymousUser())
        return await super().__call__(scope, receive, send)


def JwtAuthMiddlewareStack(inner):
    return JwtAuthMiddleware(inner)
