from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView

from .forms import SignupForm
from .models import User


class Login(LoginView):
    def get_default_redirect_url(self):
        return reverse("groups:index")


class Signup(CreateView):
    model = User
    form_class = SignupForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("groups:index")


class Logout(LogoutView):
    next_page = "home"
