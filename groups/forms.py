import copy

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef
from django.utils import timezone

from identity.models import User

from .api import (
    create_expense,
    float_to_money,
    money_to_float,
    settle_up,
    shares_are_money,
    sync_expense_group_users,
    update_expense,
    update_settle_up,
    validate_expense_split,
)
from .models import Expense, ExpenseGroup


class ListField(forms.MultiValueField):
    def compress(self, data_list):
        return data_list


class MoneyField(forms.DecimalField):
    widget = forms.NumberInput(attrs={"type": "number"})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, decimal_places=2, min_value=0)

    def clean(self, value):
        return float_to_money(super().clean(value))

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        return attrs | {"type": "number"}


class SplitWidget(forms.MultiWidget):
    template_name = "groups/widgets/split_widget.html"

    def __init__(self):
        super().__init__(
            {
                "split": forms.NumberInput(attrs={"type": "number", "step": "any"}),
                "adjustment": copy.deepcopy(MoneyField().widget),
            }
        )

    def decompress(self, value):
        return value


class SplitField(forms.MultiValueField):
    widget = SplitWidget

    def __init__(self, **kwargs):
        fields = (
            forms.DecimalField(initial=0),
            MoneyField(initial=0),
        )
        super().__init__(fields=fields, **kwargs)

    def compress(self, data_list):
        return tuple(data_list)


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ("group", "date", "type", "name", "payer", "amount")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }

    name = forms.CharField()
    payer = forms.ModelChoiceField(queryset=User.objects.none())
    amount = MoneyField()

    def __init__(self, *, group: ExpenseGroup, **kwargs):
        self._group = group
        user_queryset = User.objects.filter(
            Exists(group.expensegroupuser_set.filter(user_id=OuterRef("pk")))
        ).order_by("date_joined")
        users = list(user_queryset)

        initial = kwargs.pop("initial", {})
        initial.setdefault("group", group.id)

        instance = kwargs.get("instance")
        if instance:
            initial["amount"] = money_to_float(instance.amount)

            for split in instance.expensesplit_set.select_related("user"):
                shares = split.shares
                if shares_are_money(instance.type):
                    shares = money_to_float(shares)
                adjustment = money_to_float(split.adjustment)
                initial[f"split_{split.user.username}"] = (shares, adjustment)
        else:
            initial.setdefault("date", timezone.now().date())

        super().__init__(**kwargs, initial=initial)

        self._users = users
        self.fields["payer"].queryset = user_queryset
        self.fields["group"].initial = group.id

        self.split_fields = []
        for user in users:
            field = SplitField(label=user.username, initial=(0, 0))
            field_key = f"split_{user.username}"
            self.fields[field_key] = field
            self.split_fields.append(self[field_key])

    def clean(self):
        super().clean()

        split_by_user = {}
        for user in self._users:
            shares, adjustment = self.cleaned_data[f"split_{user.username}"]
            if shares_are_money(self.cleaned_data["type"]):
                shares = float_to_money(shares)
            else:
                shares = int(shares)
            split_by_user[user] = (shares, adjustment)

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

    payer = forms.ModelChoiceField(queryset=User.objects.none())
    payee = forms.ModelChoiceField(queryset=User.objects.none())
    amount = MoneyField()

    def __init__(self, *, group: ExpenseGroup, **kwargs):
        self._group = group
        user_queryset = User.objects.filter(
            Exists(group.expensegroupuser_set.filter(user_id=OuterRef("pk")))
        ).order_by("date_joined")
        users = list(user_queryset)

        initial = kwargs.pop("initial", {})
        initial.setdefault("group", group.id)

        instance = kwargs.get("instance")
        if instance and instance.pk:
            initial["amount"] = money_to_float(instance.amount)
            initial["payee"] = (
                instance.expensesplit_set.select_related("user").get().user
            )
        else:
            initial.setdefault("date", timezone.now().date())

        super().__init__(**kwargs, initial=initial)
        self._users = users
        self.fields["payer"].queryset = user_queryset
        self.fields["payee"].queryset = user_queryset
        self.fields["group"].initial = group.id

    def save(self, *args, **kwargs):
        if self.instance.pk:
            update_settle_up(
                self.instance,
                self.cleaned_data["payer"],
                self.cleaned_data["date"],
                self.cleaned_data["payee"],
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
        if isinstance(value, str):
            return value
        return ", ".join(value)


class ExpenseGroupForm(forms.ModelForm):
    class Meta:
        model = ExpenseGroup
        fields = "__all__"
        widgets = {
            "name": forms.TextInput,
        }


class ExpenseGroupSettingsForm(forms.ModelForm):
    class Meta:
        model = ExpenseGroup
        fields = (
            "name",
            "simplify_debts",
        )
        widgets = {
            "name": forms.TextInput,
        }

    users = CommaSeparatedCharField()

    def __init__(self, instance=None, initial=None, **kwargs):
        initial = initial or {}

        if instance:
            initial.setdefault(
                "users",
                [
                    gu.user.username
                    for gu in instance.expensegroupuser_set.select_related(
                        "user"
                    ).order_by("created_at")
                ],
            )

        super().__init__(instance=instance, initial=initial, **kwargs)

        self.fields["simplify_debts"].label_suffix = ""

    def clean_users(self):
        value = {
            username.casefold(): username for username in self.cleaned_data["users"]
        }
        matching_users = User.objects.filter(
            is_active=True, username__in=value.values()
        )
        missing = value.keys() - {u.username.casefold() for u in matching_users}
        if missing:
            raise ValidationError(
                f"Unknown users: {', '.join(value[u] for u in missing)}"
            )
        return matching_users

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        sync_expense_group_users(instance, self.cleaned_data["users"])
        return instance
