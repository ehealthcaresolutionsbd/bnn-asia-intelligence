"""GET /api/v1/photocard.png?image=<url>&title=<text>&country=<text>

Public on purpose (n8n calls it without a key), so it only fetches images hosted on BNN Asia's own site
(PHOTOCARD_IMAGE_HOSTS) and caches every result for a day.
"""
import hashlib
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_GET

from .photocard import render

MAX_BYTES = 10 * 1024 * 1024


def _allowed(url: str) -> bool:
    p = urlparse(url)
    hosts = getattr(settings, "PHOTOCARD_IMAGE_HOSTS", ["bnnasia.org", "www.bnnasia.org"])
    return p.scheme == "https" and (p.hostname or "").lower() in hosts


def _fetch(url: str) -> bytes:
    with requests.get(url, timeout=20, stream=True, headers={"User-Agent": "BNN-Photocard/1.0"}) as r:
        r.raise_for_status()
        data = b""
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) > MAX_BYTES:
                raise ValueError("image too large")
        return data


@require_GET
def photocard(request):
    title = (request.GET.get("title") or "").strip()
    country = (request.GET.get("country") or "").strip()
    image = (request.GET.get("image") or "").strip()
    if not title:
        return HttpResponseBadRequest("title is required")
    if image and not _allowed(image):
        return HttpResponseBadRequest("image must be an https URL on bnnasia.org")
    key = "photocard:" + hashlib.sha256(f"{image}|{title}|{country}".encode()).hexdigest()
    png = cache.get(key)
    if png is None:
        try:
            img = _fetch(image) if image else None
        except (requests.RequestException, ValueError) as exc:
            return HttpResponseBadRequest(f"could not load image: {exc}")
        png = render(img, title[:180], country[:40])
        cache.set(key, png, 86400)
    resp = HttpResponse(png, content_type="image/png")
    resp["Cache-Control"] = "public, max-age=86400"
    resp["Content-Disposition"] = 'inline; filename="bnn-asia-card.png"'
    return resp
