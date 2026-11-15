"""Public demo mode (DEMO_MODE=1): a safe, self-resetting copy of the app for showing it to people.

The demo database is filled with fictional data on every start (see the boot_demo command). Anything that could let
a stranger lock out other visitors, create accounts or upload files is switched off here.
"""
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

BLOCKED_VIEWS = {
    "accounts:signup",
    "accounts:password_change",
    "setup:staff_new",
    "setup:staff_edit",
    "residents:import",
    "residents:import_confirm",
}
MESSAGE = "That is switched off in the public demo. Everything else works; the data resets when the demo restarts."


def demo_context(request):
    return {"demo_mode": settings.DEMO_MODE, "demo_password": settings.DEMO_PASSWORD}


class DemoModeMiddleware:
    """In demo mode, refuse account changes and file uploads with a friendly message."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not settings.DEMO_MODE:
            return None
        match = request.resolver_match
        # Forms such as Setup are multipart even without a file, so look for actual uploaded files.
        upload = request.method == "POST" and bool(request.FILES)
        if (match and match.view_name in BLOCKED_VIEWS) or upload:
            messages.warning(request, MESSAGE)
            return redirect("accounts:home" if request.user.is_authenticated else "accounts:login")
        return None
