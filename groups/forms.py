from django.forms import ModelForm

from .models import ExpensesGroup


class ExpensesGroupForm(ModelForm):
    class Meta:
        model = ExpensesGroup
        fields = ("name",)
