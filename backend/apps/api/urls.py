from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("categories", views.CategoryViewSet, basename="category")
router.register("indicators", views.IndicatorViewSet, basename="indicator")
router.register("countries", views.CountryViewSet, basename="country")
router.register("incidents", views.IncidentViewSet, basename="incident")

urlpatterns = [
    path("", include(router.urls)),
    path("ranking/", views.ranking, name="ranking"),
    path("ranking.csv", views.ranking_csv, name="ranking-csv"),
    path("methodology/", views.methodology, name="methodology"),
    path("official-rankings/", views.official_rankings, name="official-rankings"),
    path("compare/", views.compare, name="compare"),
    path("config/", views.site_config, name="config"),
    path("health/", views.health, name="health"),
]
