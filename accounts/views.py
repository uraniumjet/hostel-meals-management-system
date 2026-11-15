from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from audit.services import record

from .access import hostels_for, is_admin, students_for
from .decorators import staff_required
from .forms import OrganizationSignupForm


@staff_required
def home(request):
    staff = request.staff
    context = {
        "staff": staff,
        "organization": staff.organization,
        "is_admin": is_admin(staff),
        "hostels": hostels_for(staff).order_by("name"),
        "student_count": students_for(staff).count(),
    }
    if context["is_admin"]:
        org = staff.organization
        context["setup"] = [
            ("Categories", org.categories.count(), "setup:lookups", "Students are grouped by category (for example National, International).", True),
            ("Diet types", org.diet_types.count(), "setup:lookups", "Veg, non-veg and so on.", True),
            ("Hostels", org.hostels.count(), "setup:hostels", "Buildings or blocks that students live in.", True),
            ("Meal types", org.meal_types.count(), "setup:meals", "Breakfast, lunch, dinner, with their serving times.", True),
            ("Counters", org.counters.count(), "setup:counters", "Serving points where wardens scan students.", True),
        ]
        context["setup_missing"] = any(item[1] == 0 for item in context["setup"])
    return render(request, "accounts/home.html", context)


class StaffLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["allow_signup"] = settings.ALLOW_ORG_SIGNUP
        return context


def signup(request):
    """Public page: register a new organisation together with its first admin."""
    if not settings.ALLOW_ORG_SIGNUP:
        raise Http404("Registration is switched off.")
    if request.user.is_authenticated:
        return redirect("accounts:home")
    form = OrganizationSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Your organisation is ready. Finish the setup below, then register students.")
        return redirect("setup:index")
    return render(request, "accounts/signup.html", {"form": form})


class StaffPasswordChangeView(PasswordChangeView):
    """Let any signed-in user change their own password (they stay signed in afterwards)."""

    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:home")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Your password has been changed.")
        record(self.request, "account.password_changed", f"{self.request.user.get_username()} changed their password.")
        return response
