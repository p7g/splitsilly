from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, UpdateView

from .forms import SignupForm, UserSettingsForm
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


class UserSettingsView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserSettingsForm
    template_name = "identity/settings.html"
    success_url = reverse_lazy("groups:index")

    def get_object(self):
        return self.request.user
