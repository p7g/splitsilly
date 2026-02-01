import enum
from urllib.parse import urljoin
from typing import Self
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models import Exists, OuterRef
from django.urls import reverse

from identity.models import User

from .templatetags.money import to_dollars


class ExpenseGroupQuerySet(models.QuerySet["ExpenseGroup"]):
    def for_user(self, user: User) -> Self:
        return self.filter(
            Exists(
                ExpenseGroupUser.objects.filter(user=user, group=OuterRef("pk")).values(
                    "id"
                )
            )
        )


class ExpenseGroup(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    name = models.TextField()
    simplify_debts = models.BooleanField(default=False)

    objects = models.Manager.from_queryset(ExpenseGroupQuerySet)()

    def get_absolute_url(self) -> str:
        return reverse("groups:group", args=(self.id,))


class ExpenseGroupUser(models.Model):
    class Meta:
        unique_together = [("group", "user")]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    group = models.ForeignKey(ExpenseGroup, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)


class ExpenseQuerySet(models.QuerySet["Expense"]):
    def for_user(self, user: User) -> Self:
        return self.filter(
            Exists(
                ExpenseGroup.objects.for_user(user)
                .filter(id=OuterRef("group_id"))
                .values("id")
            )
        )


class Expense(models.Model):
    class Type(enum.IntEnum):
        EXACT = enum.auto()
        PERCENTAGE = enum.auto()
        SHARES = enum.auto()

        # Removed
        ADJUSTMENT = enum.auto()

    EXPENSE_TYPE_CHOICES = [
        (Type.EXACT, "Exact"),
        (Type.PERCENTAGE, "Percentage"),
        (Type.SHARES, "Shares"),
    ]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    group = models.ForeignKey(ExpenseGroup, on_delete=models.CASCADE)
    name = models.TextField()
    date = models.DateField()
    amount = models.IntegerField()
    # FIXME: cascade?
    payer = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.IntegerField(choices=EXPENSE_TYPE_CHOICES)
    is_settle_up = models.BooleanField(default=False)
    exchange_rate = models.DecimalField(max_digits=20, decimal_places=10, default=1)
    currency_symbol = models.TextField(default="$")
    note = models.TextField(default="", blank=True)

    objects = models.Manager.from_queryset(ExpenseQuerySet)()

    @property
    def split_method_friendly_name(self) -> str:
        if self.type == self.Type.EXACT:
            return "by exact amount"
        elif self.type == self.Type.PERCENTAGE:
            return "by percentage"
        elif self.type == self.Type.SHARES:
            return "by shares"
        else:
            raise NotImplementedError(self.type)

    def get_absolute_url(self) -> str:
        return reverse("groups:expense", args=(self.id,))


class ExpenseSplit(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    expense = models.ForeignKey(Expense, on_delete=models.CASCADE)
    # FIXME: cascade?
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    shares_expr = models.TextField()
    shares = models.IntegerField()
    adjustment = models.IntegerField(default=0)

    @property
    def formatted_shares(self) -> str:
        if self.expense.type == Expense.Type.EXACT:
            return to_dollars(
                self.shares + self.adjustment, self.expense.currency_symbol
            )
        elif self.expense.type == Expense.Type.PERCENTAGE:
            formatted_shares = f"{self.shares}%"
        elif self.expense.type == Expense.Type.SHARES:
            formatted_shares = f"{self.shares} shares"
        else:
            raise NotImplementedError(self.expense.type)

        if not self.adjustment:
            return formatted_shares

        adjustment = to_dollars(abs(self.adjustment), self.expense.currency_symbol)
        if self.adjustment > 0:
            return f"{formatted_shares} + {adjustment}"
        else:
            return f"{formatted_shares} - {adjustment}"


class ExpenseGroupInvite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    group = models.ForeignKey(ExpenseGroup, on_delete=models.CASCADE)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    recipient = models.EmailField()
    consumed_by = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )

    def get_absolute_url(self) -> str:
        return urljoin(
            settings.ROOT_URL, reverse("groups:invite_detail", args=(str(self.id),))
        )
