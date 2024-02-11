from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.forms import ModelForm
from timezone_field import TimeZoneFormField

from .models import User


class LoginForm(AuthenticationForm):
    pass


class SignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "email"]


class UserSettingsForm(ModelForm):
    class Meta:
        model = User
        fields = ("timezone", "email")

    timezone = TimeZoneFormField(choices_display="WITH_GMT_OFFSET")
