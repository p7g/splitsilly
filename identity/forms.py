from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.forms import ModelForm

from .models import User


class LoginForm(AuthenticationForm):
    pass


class SignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "email"]
