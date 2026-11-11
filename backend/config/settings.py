"""BNN Asia Country Intelligence Platform – Django settings.

All secrets and environment-specific values come from environment variables
(see deploy/.env.example). Development and production are separated by
DJANGO_ENV; production refuses to start with insecure defaults.
"""
from pathlib import Path
import os

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR, ".env"), overwrite=False)

DJANGO_ENV = env("DJANGO_ENV", default="development")
DEBUG = env.bool("DJANGO_DEBUG", default=DJANGO_ENV == "development")
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-only-insecure-key-change-me")
if DJANGO_ENV == "production" and (DEBUG or SECRET_KEY.startswith("dev-only")):
    raise RuntimeError("Production requires DJANGO_DEBUG=0 and a real DJANGO_SECRET_KEY")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "testserver"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "apps.core",
    "apps.catalog",
    "apps.sources",
    "apps.observations",
    "apps.incidents",
    "apps.rankings",
    "apps.reports",
    "apps.signals",
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.AuditUserMiddleware",
    "apps.core.middleware.AdminHostMiddleware",
]
ADMIN_HOSTS = env.list("ADMIN_HOSTS", default=[])  # e.g. research.bnnasia.org – admin is 404 on every other host

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": env.db("DATABASE_URL", default="postgres://bnn:bnn_dev_pw@localhost:5432/bnn_intel")}
DATABASES["default"]["CONN_MAX_AGE"] = 60

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.auth.ApiKeyAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend",
                                "rest_framework.filters.OrderingFilter"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "120/min"},
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SPECTACULAR_SETTINGS = {"TITLE": "BNN Asia Intelligence API", "VERSION": "1.0.0",
                        "SWAGGER_UI_DIST": "SIDECAR", "SWAGGER_UI_FAVICON_HREF": "SIDECAR", "REDOC_DIST": "SIDECAR"}

CACHES = {"default": {
    "BACKEND": "django.core.cache.backends.redis.RedisCache",
    "LOCATION": env("REDIS_URL", default="redis://localhost:6379/1"),
}} if env.bool("USE_REDIS_CACHE", default=True) else {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "sync-rss-hourly": {"task": "apps.sources.tasks.sync_due_sources", "schedule": 3600.0},
    "ingest-gdelt-daily": {"task": "apps.signals.tasks.ingest_yesterday", "schedule": crontab(hour=3, minute=30)},
    "refresh-index-weekly": {"task": "apps.signals.tasks_index.refresh_index_task",
                             "schedule": crontab(hour=4, minute=0, day_of_week=1)},
}

# Outbound HTTP for collectors
HTTP_USER_AGENT = env("HTTP_USER_AGENT", default="BNN-Asia-Intelligence/1.0 (+https://bnnasia.org; research@bnnasia.org)")
HTTP_TIMEOUT = env.int("HTTP_TIMEOUT", default=30)

# Optional AI assistance (Stage B). Never auto-publishes; output is advisory only.
AI_PROVIDER = env("AI_PROVIDER", default="")          # "anthropic" | "openai" | ""
AI_API_KEY = env("AI_API_KEY", default="")

if DJANGO_ENV == "production":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
