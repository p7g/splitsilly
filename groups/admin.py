from django.contrib import admin

from .models import (
    Expense,
    ExpenseGroup,
    ExpenseGroupInvite,
    ExpenseGroupUser,
    ExpenseSplit,
)


class ExpenseGroupInviteInline(admin.TabularInline[ExpenseGroupInvite, ExpenseGroup]):
    model = ExpenseGroupInvite


class ExpenseGroupUserInline(admin.TabularInline[ExpenseGroupUser, ExpenseGroup]):
    model = ExpenseGroupUser


@admin.register(ExpenseGroup)
class ExpenseGroupAdmin(admin.ModelAdmin[ExpenseGroup]):
    inlines = [
        ExpenseGroupUserInline,
        ExpenseGroupInviteInline,
    ]

    list_display = ["id", "name", "created_at", "updated_at"]


class ExpenseSplitInline(admin.TabularInline[ExpenseSplit, Expense]):
    model = ExpenseSplit


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin[Expense]):
    inlines = [ExpenseSplitInline]

    list_display = ["id", "group", "name", "type", "amount", "payer", "date"]


admin.site.register(ExpenseSplit)
admin.site.register(ExpenseGroupInvite)
