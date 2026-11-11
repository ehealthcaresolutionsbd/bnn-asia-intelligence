import hashlib
import secrets

from django.db import models


class ApiClient(models.Model):
    """Server-to-server client (e.g. the WordPress plugin). Only a hash of the key is stored."""
    name = models.CharField(max_length=100, unique=True)
    key_prefix = models.CharField(max_length=8, editable=False)
    key_hash = models.CharField(max_length=64, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.key_prefix}…)"

    @staticmethod
    def hash(key):
        return hashlib.sha256(key.encode()).hexdigest()

    @classmethod
    def issue(cls, name):
        key = "bnn_" + secrets.token_urlsafe(32)
        obj = cls.objects.create(name=name, key_prefix=key[:8], key_hash=cls.hash(key))
        return obj, key
