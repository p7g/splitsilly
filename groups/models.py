import enum

from django.db import models
from django.db.models import Exists, OuterRef
from django.urls import reverse

from identity.models import User

from .templatetags.money import to_dollars


class ExpenseGroupQuerySet(models.QuerySet):
    def for_user(self, user: User):
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

    def get_absolute_url(self):
        return reverse("groups:group", args=(self.id,))


class ExpenseGroupUser(models.Model):
    class Meta:
        unique_together = [("group", "user")]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    group = models.ForeignKey(ExpenseGroup, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)


class ExpenseQuerySet(models.QuerySet):
    def for_user(self, user: User):
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
        ADJUSTMENT = enum.auto()

    EXPENSE_TYPE_CHOICES = [
        (Type.EXACT, "Exact"),
        (Type.PERCENTAGE, "Percentage"),
        (Type.SHARES, "Shares"),
        (Type.ADJUSTMENT, "Adjustment"),
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

    objects = models.Manager.from_queryset(ExpenseQuerySet)()

    @property
    def split_method_friendly_name(self) -> str:
        if self.type == self.Type.EXACT:
            return "by exact amount"
        elif self.type == self.Type.PERCENTAGE:
            return "by percentage"
        elif self.type == self.Type.SHARES:
            return "by shares"
        elif self.type == self.Type.ADJUSTMENT:
            return "by adjustment"
        else:
            raise NotImplementedError(self.type)

    def get_absolute_url(self):
        return reverse("groups:expense", args=(self.id,))


class ExpenseSplit(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    expense = models.ForeignKey(Expense, on_delete=models.CASCADE)
    # FIXME: cascade?
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    shares = models.IntegerField()

    @property
    def formatted_shares(self) -> str:
        if self.expense.type == Expense.Type.EXACT:
            return to_dollars(self.shares)
        elif self.expense.type == Expense.Type.PERCENTAGE:
            return f"{self.shares}%"
        elif self.expense.type == Expense.Type.SHARES:
            return f"{self.shares} shares"
        elif self.expense.type == Expense.Type.ADJUSTMENT:
            if self.shares == 0:
                return f"N"
            dollars = to_dollars(abs(self.shares))
            if self.shares > 0:
                return f"N + {dollars}"
            else:
                return f"N - {dollars}"
        else:
            raise NotImplementedError(self.expense.type)
