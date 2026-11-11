from django.utils import timezone
from rest_framework import authentication, exceptions


class ApiClientUser:
    is_authenticated = True
    is_staff = False
    is_api_client = True

    def __init__(self, client):
        self.client = client
        self.username = f"api:{client.name}"


class ApiKeyAuthentication(authentication.BaseAuthentication):
    """Header: Authorization: Api-Key <key>. Gives read access identical to public, plus higher throttle."""

    def authenticate(self, request):
        h = request.headers.get("Authorization", "")
        if not h.startswith("Api-Key "):
            return None
        from .models import ApiClient
        c = ApiClient.objects.filter(key_hash=ApiClient.hash(h[8:].strip()), is_active=True).first()
        if not c:
            raise exceptions.AuthenticationFailed("Invalid API key")
        ApiClient.objects.filter(pk=c.pk).update(last_used_at=timezone.now())
        return ApiClientUser(c), None

    def authenticate_header(self, request):
        return "Api-Key"
