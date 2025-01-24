from django.contrib import admin

from .models import Expense, ExpenseGroup, ExpenseGroupInvite, ExpenseGroupUser, ExpenseGroupUser, ExpenseSplit


class ExpenseGroupInviteInline(admin.TabularInline):
    model = ExpenseGroupInvite


class ExpenseGroupUserInline(admin.TabularInline):
    model = ExpenseGroupUser


@admin.register(ExpenseGroup)
class ExpenseGroupAdmin(admin.ModelAdmin):
    inlines = [
        ExpenseGroupUserInline,
        ExpenseGroupInviteInline,
    ]

    list_display = ["id", "name", "created_at", "updated_at"]


class ExpenseSplitInline(admin.TabularInline):
    model = ExpenseSplit


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    inlines = [ExpenseSplitInline]

    list_display = ["id", "group", "name", "type", "amount", "payer", "date"]


admin.site.register(ExpenseSplit)
admin.site.register(ExpenseGroupInvite)
