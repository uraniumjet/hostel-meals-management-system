from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .views import StaffPasswordChangeView

app_name = "accounts"

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.StaffLoginView.as_view(), name="login"),
    path("signup/", views.signup, name="signup"),
    path("password/", StaffPasswordChangeView.as_view(), name="password_change"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
