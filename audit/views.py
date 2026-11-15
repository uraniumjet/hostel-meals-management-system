from datetime import date

from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.shortcuts import render

from accounts.decorators import admin_required

from .models import AuditEntry

PAGE_SIZE = 50
AREAS = {"student": "Students", "setup": "Setup", "account": "Accounts", "report": "Reports"}


def _date(value):
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@admin_required
def activity(request):
    """The organisation's activity log, newest first, for admins only."""
    org = request.staff.organization
    entries = AuditEntry.objects.filter(organization=org)
    area = request.GET.get("area", "")
    if area in AREAS:
        entries = entries.filter(action__startswith=f"{area}.")
    who = request.GET.get("who", "")
    if who.isdigit():
        entries = entries.filter(actor_id=int(who))
    q = request.GET.get("q", "").strip()
    if q:
        entries = entries.filter(summary__icontains=q)
    start, end = _date(request.GET.get("from", "")), _date(request.GET.get("to", ""))
    if start:
        entries = entries.filter(created_at__date__gte=start)
    if end:
        entries = entries.filter(created_at__date__lte=end)
    page = Paginator(entries.select_related("actor"), PAGE_SIZE).get_page(request.GET.get("page"))
    people = User.objects.filter(staff_profile__organization=org).order_by("username")
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "audit/activity.html", {
        "page": page, "areas": AREAS, "area": area, "who": who, "q": q,
        "start": request.GET.get("from", ""), "end": request.GET.get("to", ""), "people": people,
        "organization": org, "query": params.urlencode(),
    })
