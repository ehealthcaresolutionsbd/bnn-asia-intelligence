from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView

admin.site.site_header = "BNN Asia – Research & Administration"
admin.site.site_title = "BNN Asia Intelligence"
admin.site.index_title = "Country Intelligence & Asia Ranking Platform"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.api.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularRedocView.as_view(url_name="schema"), name="docs"),
    path("reports/", include("apps.reports.urls")),
]
