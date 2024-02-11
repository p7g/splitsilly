import calendar

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import CreateView, DeleteView, UpdateView

from .api import (
    calculate_debts,
    calculate_expense_debts,
    simplify_debts,
    simplify_mutual_owing,
)
from .forms import ExpenseForm, ExpenseGroupSettingsForm, SettleUpForm
from .models import Expense, ExpenseGroup
from .templatetags.money import to_dollars


@login_required
def groups_index(request):
    group = get_object_or_404(ExpenseGroup.objects.for_user(request.user))
    return redirect(group)


@login_required
def group_home(request, group_id: int):
    try:
        group = (
            ExpenseGroup.objects.for_user(request.user)
            .prefetch_related(
                "expense_set__payer", "expense_set__expensesplit_set__user"
            )
            .get(pk=group_id)
        )
    except ExpenseGroup.DoesNotExist:
        raise Http404()

    debts = calculate_debts(group)
    if group.simplify_debts:
        debts = simplify_debts(debts)
    else:
        debts = simplify_mutual_owing(debts)

    expenses_by_year_month = []
    for expense in group.expense_set.prefetch_related("payer").order_by(
        "-date", "-created_at"
    ):
        y_mo = (expense.date.year, calendar.month_name[expense.date.month])
        if not expenses_by_year_month or y_mo != expenses_by_year_month[-1][:2]:
            expenses_by_year_month.append((*y_mo, []))
        expenses_by_year_month[-1][-1].append(expense)

    return render(
        request,
        "groups/group_home.html",
        {
            "group": group,
            "expenses": expenses_by_year_month,
            "debts": debts,
            "user": request.user,
        },
    )


@login_required
def expense_detail(request, expense_id: int):
    try:
        expense = (
            Expense.objects.for_user(request.user)
            .prefetch_related("expensesplit_set")
            .get(pk=expense_id)
        )
    except ExpenseGroup.DoesNotExist:
        raise Http404()

    debts = calculate_expense_debts(expense)

    return render(
        request, "groups/expense_detail.html", {"expense": expense, "debts": debts}
    )


class ExpenseFormViewMixin(LoginRequiredMixin):
    model = Expense

    def __init__(self, *args, is_settle_up: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._is_settle_up = is_settle_up

    def get_queryset(self):
        return super().get_queryset().for_user(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["group"] = self._get_group()
        return kwargs

    def is_settle_up(self):
        return self._is_settle_up or (self.object and self.object.is_settle_up)

    def get_form_class(self):
        if self.is_settle_up():
            return SettleUpForm
        else:
            return ExpenseForm

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["group"] = data["form"]._group
        return data

    def get_template_names(self):
        if self.is_settle_up():
            return ["groups/settle_up.html"]
        else:
            return ["groups/expense_form.html"]


class CreateExpense(ExpenseFormViewMixin, CreateView):
    def _get_group(self):
        return get_object_or_404(
            ExpenseGroup.objects.for_user(self.request.user), pk=self.kwargs["group_id"]
        )

    def get_initial(self):
        initial = super().get_initial()
        initial["payer"] = self.request.user
        return initial

    def form_valid(self, form):
        result = super().form_valid(form)

        # Email everyone except the creator
        expense = self.object
        assert isinstance(expense, Expense)
        debts = calculate_expense_debts(expense)

        for user, amount_owed in debts.items():
            if user == self.request.user:
                continue
            if expense.is_settle_up:
                user.send_email(
                    f"{expense.payer.username} settled up with you",
                    f"They paid you {to_dollars(-amount_owed)}.",
                )
            elif user == expense.payer:
                user.send_email(
                    f"{self.request.user.username} added a new expense in {expense.group.name}",
                    f"You paid {to_dollars(expense.amount)} for {expense.name} on {expense.date.isoformat()}. "
                    f"You are owed {to_dollars(expense.amount - amount_owed)}.",
                )
            else:
                user.send_email(
                    f"{self.request.user.username} added a new expense in {expense.group.name}",
                    f"You owe {to_dollars(amount_owed)} to {expense.payer.username} for {expense.name} on {expense.date.isoformat()}.",
                )

        return result


class UpdateExpense(ExpenseFormViewMixin, UpdateView):
    pk_url_kwarg = "expense_id"
    context_object_name = "expense"

    def _get_group(self):
        return get_object_or_404(
            Expense.objects.for_user(self.request.user), pk=self.kwargs["expense_id"]
        ).group

    def form_valid(self, form):
        result = super().form_valid(form)

        # Email everyone except the creator
        expense = self.object
        assert isinstance(expense, Expense)
        debts = calculate_expense_debts(expense)

        for user, amount_owed in debts.items():
            if user == self.request.user:
                continue
            if expense.is_settle_up:
                user.send_email(
                    f"{expense.payer.username} updated their settle up with you",
                    f"They now paid you {to_dollars(amount_owed)}.",
                )
            elif user == expense.payer:
                user.send_email(
                    f"{self.request.user.username} updated an expense in {expense.group.name}",
                    f"You paid {to_dollars(expense.amount)} for {expense.name} on {expense.date.isoformat()}. "
                    f"You are now owed {to_dollars(expense.amount - amount_owed)}.",
                )
            else:
                user.send_email(
                    f"{self.request.user.username} updated an expense in {expense.group.name}",
                    f"You now owe {to_dollars(amount_owed)} to {expense.payer.username} for {expense.name} on {expense.date.isoformat()}",
                )

        return result


class DeleteExpense(DeleteView):
    pk_url_kwarg = "expense_id"
    context_object_name = "expense"
    model = Expense

    def get_success_url(self):
        return self.object.group.get_absolute_url()


class GroupSettings(LoginRequiredMixin, UpdateView):
    model = ExpenseGroup
    context_object_name = "group"
    form_class = ExpenseGroupSettingsForm
    pk_url_kwarg = "group_id"
    template_name = "groups/settings.html"

    def get_queryset(self):
        return super().get_queryset().for_user(self.request.user)
