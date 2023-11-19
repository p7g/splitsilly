from django.contrib.auth import authenticate, login
from django.core.exceptions import BadRequest
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.views.generic import FormView, TemplateView
from django.contrib.auth.views import LoginView
from django.views.generic import CreateView
from django.urls import reverse, reverse_lazy

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
