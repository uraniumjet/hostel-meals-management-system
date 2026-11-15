from datetime import timedelta
from urllib.parse import urlencode

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from accounts.decorators import staff_required
from audit.services import record

from .builders import REPORTS
from .exporters import to_csv, to_pdf, to_xlsx
from .forms import ReportFilterForm


def _logo(org):
    if not org.logo:
        return None
    try:
        with org.logo.open("rb") as handle:
            return handle.read()
    except FileNotFoundError:
        return None


def _period_text(start, end):
    return f"{start:%d %b %Y}" if start == end else f"{start:%d %b %Y} to {end:%d %b %Y}"


def _params(request, staff):
    """The filter values: from the query string, or sensible defaults on the first visit."""
    given = {k: v for k, v in request.GET.items() if k != "format" and v != ""}
    if given:
        return given
    return {"period": "day", "date": staff.organization.local_today().isoformat()}


def _index(request, form, params):
    staff = request.staff
    cards = []
    for kind, (title, blurb, _) in REPORTS.items():
        base = reverse("reports:report", args=[kind])

        def link(fmt, base=base):
            return f"{base}?{urlencode({**params, 'format': fmt})}"

        cards.append({"title": title, "blurb": blurb, "html": link("html"), "csv": link("csv"), "xlsx": link("xlsx"),
                      "pdf": link("pdf")})
    today = staff.organization.local_today()
    presets = [
        ("Today", {"period": "day", "date": today.isoformat()}),
        ("Yesterday", {"period": "day", "date": (today - timedelta(days=1)).isoformat()}),
        ("This week", {"period": "week", "date": today.isoformat()}),
        ("This month", {"period": "month", "date": today.isoformat()}),
    ]
    presets = [(label, "?" + urlencode({**data, **({"hostel": params["hostel"]} if "hostel" in params else {})}))
               for label, data in presets]
    return render(request, "reports/index.html", {"form": form, "cards": cards, "range": form.range, "presets": presets})


@staff_required
def index(request):
    params = _params(request, request.staff)
    form = ReportFilterForm(params, staff=request.staff)
    form.is_valid()
    return _index(request, form, params)


@staff_required
def report(request, kind):
    if kind not in REPORTS:
        raise Http404("Unknown report")
    staff = request.staff
    params = _params(request, staff)
    form = ReportFilterForm(params, staff=staff)
    if not form.is_valid():
        return _index(request, form, params)

    start, end = form.range
    table = REPORTS[kind][2](staff, start, end, form.cleaned_data["hostel"])
    output = request.GET.get("format", "html")
    stem = f"{kind}_{start.isoformat()}_{end.isoformat()}"

    if output in {"csv", "xlsx", "pdf"}:
        record(request, "report.downloaded", f"Downloaded {table.title} ({output.upper()}), {_period_text(start, end)}.")
    if output == "csv":
        response = HttpResponse(to_csv(table), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{stem}.csv"'
        return response
    if output == "xlsx":
        stamp = staff.organization.local_now().strftime("%d %b %Y %H:%M")
        content = to_xlsx(table, heading=f"Generated {stamp} by {request.user.get_username()}")
        response = HttpResponse(
            content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="{stem}.xlsx"'
        return response
    if output == "pdf":
        stamp = staff.organization.local_now().strftime("%d %b %Y %H:%M")
        heading = f"Generated {stamp} by {request.user.get_username()}"
        try:
            content = to_pdf(table, heading=heading, footer_note=staff.organization.name, logo=_logo(staff.organization))
        except ImportError:
            return HttpResponse("PDF export needs the reportlab package: pip install reportlab", status=501,
                                content_type="text/plain")
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{stem}.pdf"'
        return response

    base = reverse("reports:report", args=[kind])
    links = {fmt: f"{base}?{urlencode({**params, 'format': fmt})}" for fmt in ("csv", "xlsx", "pdf")}
    return render(request, "reports/report.html", {"table": table, "links": links})
