from django.urls import path

from .views import Login, Signup

app_name = "identity"

urlpatterns = [
    path("login/", Login.as_view(), name="login"),
    path("signup/", Signup.as_view(), name="signup"),
]
