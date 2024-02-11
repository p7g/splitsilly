from django.urls import path

from .views import Login, Logout, Signup, UserSettingsView

app_name = "identity"

urlpatterns = [
    path("login/", Login.as_view(), name="login"),
    path("signup/", Signup.as_view(), name="signup"),
    path("logout/", Logout.as_view(), name="logout"),
    path("settings/", UserSettingsView.as_view(), name="settings"),
]
