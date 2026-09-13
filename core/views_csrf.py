# Purpose: Friendly CSRF failure handler — expired-form UX instead of Django's raw 403 page
# Used by: settings.CSRF_FAILURE_VIEW (Django calls csrf_failure on any CSRF validation failure)
# Notes: Self-healing — the 403 itself plants a fresh csrftoken cookie, so the retry works.
#        /accounts/ pages redirect back with a message; AJAX gets JSON 403; others render
#        core/csrf_failure.html.

import logging

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render

logger = logging.getLogger(__name__)


def csrf_failure(request, reason=""):
    logger.warning(
        "CSRF failure on %s (%s) user=%s",
        request.path,
        reason,
        request.user.pk if request.user.is_authenticated else "anonymous",
    )

    # "CSRF cookie not set" means the browser held no csrftoken at all — usually a
    # page served from a cache (service worker / bfcache / proxy) that never carried
    # the Set-Cookie header. Retrying can never succeed until a cookie exists, so
    # mint one here: get_token() flags the response and CsrfViewMiddleware's
    # process_response writes Set-Cookie onto this very 403.
    cookie_missing = "cookie not set" in (reason or "").lower()
    get_token(request)

    wants_json = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )
    if wants_json:
        return JsonResponse(
            {"error": "Your session expired. Please refresh the page and try again."},
            status=403,
        )

    if request.path.startswith("/accounts/"):
        # Stale login tab: already signed in elsewhere, token rotated on login
        if request.user.is_authenticated:
            return redirect(settings.LOGIN_REDIRECT_URL)
        messages.info(request, "This page had expired — please try again.")
        return redirect(request.path)

    # Referer only when same-origin, so the retry link never points off-site
    referer = request.headers.get("referer", "")
    back_url = referer if referer.startswith(f"https://{request.get_host()}") else ""

    # The retry must bypass every cache layer, otherwise the same stale page
    # (with the same dead token) is handed back and the driver loops forever.
    retry_url = back_url or request.path
    if retry_url:
        retry_url += ("&" if "?" in retry_url else "?") + "_r=1"

    response = render(
        request,
        "core/csrf_failure.html",
        {"back_url": back_url, "retry_url": retry_url, "cookie_missing": cookie_missing},
        status=403,
    )
    response["Cache-Control"] = "no-store"
    return response
