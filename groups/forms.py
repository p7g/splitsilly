from django import forms
from django.core import validators
from django.utils import timezone

from .api import (
    create_expense,
    shares_are_money,
    money_to_float,
    float_to_money,
    update_expense,
    update_settle_up,
    settle_up,
    validate_expense_split,
    sync_expense_group_users,
)
from .models import Expense, ExpenseGroup


class ListField(forms.MultiValueField):
    def compress(self, data_list):
        return data_list


class MoneyField(forms.FloatField):
    widget = forms.NumberInput(attrs={"type": "number"})

    def clean(self, value):
        return float_to_money(super().clean(value))


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ("group", "date", "type", "name", "payer", "amount")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }

    name = forms.CharField()
    payer = forms.ChoiceField(choices=[])
    amount = MoneyField()

    def __init__(self, *, group: ExpenseGroup, **kwargs):
        self._group = group
        users = list(group.expensegroupuser_set.order_by("created_at"))

        initial = kwargs.pop("initial", {})
        initial.setdefault("group", group.id)
        initial.setdefault("date", timezone.now().date())

        instance = kwargs.get("instance")
        if instance:
            initial["amount"] = money_to_float(instance.amount)

            for split in instance.expensesplit_set.all():
                shares = split.shares
                if shares_are_money(instance.type):
                    shares = money_to_float(shares)
                initial[f"split_{split.user}"] = shares

        super().__init__(**kwargs, initial=initial)
        self._users = users
        self.fields["payer"] = forms.ChoiceField(
            choices=[(u.name, u.name) for u in users]
        )
        self.fields["group"].initial = group.id

        self.split_fields = []
        for user in users:
            field = forms.FloatField(label=user.name, initial=0)
            field_key = f"split_{user.name}"
            self.fields[field_key] = field
            self.split_fields.append(self[field_key])

    def clean(self):
        super().clean()

        split_by_user = {}
        for user in self._users:
            shares = self.cleaned_data[f"split_{user.name}"]
            if shares_are_money(self.cleaned_data["type"]):
                shares = float_to_money(shares)
            else:
                shares = int(shares)
            split_by_user[user.name] = shares

        validate_expense_split(
            self.cleaned_data["type"], self.cleaned_data["amount"], split_by_user
        )
        self.cleaned_data["split"] = split_by_user

    def save(self, commit=True):
        if not commit:
            raise NotImplementedError

        expense_data = {
            "type_": self.cleaned_data["type"],
            "name": self.cleaned_data["name"],
            "payer": self.cleaned_data["payer"],
            "date": self.cleaned_data["date"],
            "amount": self.cleaned_data["amount"],
            "split": self.cleaned_data["split"],
        }

        if self.instance.pk:
            update_expense(self.instance, **expense_data)
            return self.instance
        else:
            return create_expense(self.cleaned_data["group"], **expense_data)


class SettleUpForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ("group", "date", "payer", "amount")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }

    payer = forms.ChoiceField(choices=[])
    payee = forms.ChoiceField(choices=[])
    amount = MoneyField()

    def __init__(self, *, group: ExpenseGroup, **kwargs):
        self._group = group
        users = list(group.expensegroupuser_set.order_by("created_at"))

        initial = kwargs.pop("initial", {})
        initial.setdefault("group", group.id)
        initial.setdefault("date", timezone.now().date())

        instance = kwargs.get("instance")
        if instance and instance.pk:
            initial["amount"] = money_to_float(instance.amount)
            initial["payee"] = instance.expensesplit_set.get().user

        super().__init__(**kwargs, initial=initial)
        self._users = users
        self.fields["payer"] = forms.ChoiceField(
            choices=[(u.name, u.name) for u in users]
        )
        self.fields["payee"] = forms.ChoiceField(
            choices=[(u.name, u.name) for u in users]
        )
        self.fields["group"].initial = group.id

    def save(self, *args, **kwargs):
        if self.instance.pk:
            update_settle_up(
                self.instance,
                self.cleaned_data["payer"],
                self.cleaned_data["payee"],
                self.cleaned_data["date"],
                self.cleaned_data["amount"],
            )
            return self.instance
        else:
            return settle_up(
                self.cleaned_data["group"],
                self.cleaned_data["payer"],
                self.cleaned_data["date"],
                self.cleaned_data["payee"],
                self.cleaned_data["amount"],
            )


class CommaSeparatedCharField(forms.Field):
    def to_python(self, value):
        if value in self.empty_values:
            return []
        value = str(value).strip()
        if value in self.empty_values:
            return []

        value = (item.strip() for item in value.split(","))
        return list(set(filter(None, value)))

    def prepare_value(self, value):
        return ", ".join(value)


class ExpenseGroupSettingsForm(forms.ModelForm):
    class Meta:
        model = ExpenseGroup
        fields = ("simplify_debts",)

    def __init__(self, instance=None, initial=None, **kwargs):
        initial = initial or {}

        if instance:
            initial.setdefault(
                "users",
                [
                    user.name
                    for user in instance.expensegroupuser_set.order_by("created_at")
                ],
            )

        super().__init__(instance=instance, initial=initial, **kwargs)

        self.fields["simplify_debts"].label_suffix = ""

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        sync_expense_group_users(instance, self.cleaned_data["users"])
        return instance

    users = CommaSeparatedCharField()
