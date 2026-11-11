from .audit import set_current_user


class AuditUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_user(getattr(request, "user", None))
        try:
            return self.get_response(request)
        finally:
            set_current_user(None)


class AdminHostMiddleware:
    """Serve /admin/ and /reports/ drafts only on the research host (when ADMIN_HOSTS is set)."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        from django.http import Http404
        hosts = getattr(settings, "ADMIN_HOSTS", [])
        if hosts and request.path.startswith("/admin") and request.get_host().split(":")[0] not in hosts:
            raise Http404()
        return self.get_response(request)
