# Purpose: Friendly CSRF failure handler — expired-form UX instead of Django's raw 403 page
# Used by: settings.CSRF_FAILURE_VIEW (Django calls csrf_failure on any CSRF validation failure)
# Notes: /accounts/ pages redirect back with a message; AJAX gets JSON 403; others render core/csrf_failure.html

import logging

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render

logger = logging.getLogger(__name__)


def csrf_failure(request, reason=""):
    logger.warning(
        "CSRF failure on %s (%s) user=%s",
        request.path,
        reason,
        request.user.pk if request.user.is_authenticated else "anonymous",
    )

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
    return render(request, "core/csrf_failure.html", {"back_url": back_url}, status=403)
