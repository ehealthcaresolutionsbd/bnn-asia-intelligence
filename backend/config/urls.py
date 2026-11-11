from django.contrib import admin
from django.conf import settings
from django.shortcuts import redirect
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView

admin.site.site_header = "BNN Asia – Research & Administration"
admin.site.site_title = "BNN Asia Intelligence"
admin.site.index_title = "Country Intelligence & Asia Ranking Platform"


def home(request):
    """research host → admin, api host → API docs."""
    host = request.get_host().split(":")[0]
    return redirect("/admin/" if host in getattr(settings, "ADMIN_HOSTS", []) else "/api/docs/")


urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.api.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularRedocView.as_view(url_name="schema"), name="docs"),
    path("reports/", include("apps.reports.urls")),
]
