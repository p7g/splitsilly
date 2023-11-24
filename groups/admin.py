from django.contrib import admin

from .models import Expense, ExpenseGroup, ExpenseGroupUser, ExpenseSplit

admin.site.register(ExpenseGroup)
admin.site.register(ExpenseGroupUser)
admin.site.register(Expense)
admin.site.register(ExpenseSplit)
