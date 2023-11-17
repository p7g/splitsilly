import enum

from django.db import models


class ExpenseGroup(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    name = models.TextField()
    simplify_debts = models.BooleanField(default=False)


class ExpenseGroupUser(models.Model):
    class Meta:
        unique_together = [("group", "name")]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    group = models.ForeignKey(ExpenseGroup, on_delete=models.CASCADE)
    name = models.TextField()


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
    date = models.DateField()
    amount = models.IntegerField()
    payer = models.TextField()
    type = models.IntegerField(choices=EXPENSE_TYPE_CHOICES)


class ExpenseSplit(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    expense = models.ForeignKey(Expense, on_delete=models.CASCADE)
    user = models.TextField()
    shares = models.IntegerField()
