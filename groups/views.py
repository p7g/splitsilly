import calendar

from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import CreateView, TemplateView, UpdateView
from django.urls import reverse

from .api import calculate_debts, calculate_expense_debts, simplify_debts, shares_are_money, money_to_float
from .forms import ExpenseForm, ExpenseGroupSettingsForm, SettleUpForm
from .models import Expense, ExpenseGroup


def group_home(request, group_id: int):
    try:
        group = ExpenseGroup.objects.prefetch_related("expense_set", "expense_set__expensesplit_set").get(pk=group_id)
    except ExpenseGroup.DoesNotExist:
        raise Http404()

    debts = calculate_debts(group)
    if group.simplify_debts:
        debts = simplify_debts(debts)

    expenses_by_year_month = []
    for expense in group.expense_set.order_by("-date", "-created_at"):
        y_mo = (expense.date.year, calendar.month_name[expense.date.month])
        if not expenses_by_year_month or y_mo != expenses_by_year_month[-1][:2]:
            expenses_by_year_month.append((*y_mo, []))
        expenses_by_year_month[-1][-1].append(expense)

    return render(request, "groups/home.html", {"group": group, "expenses": expenses_by_year_month, "debts": debts})


def expense_detail(request, expense_id: int):
    try:
        expense = Expense.objects.prefetch_related("expensesplit_set").get(pk=expense_id)
    except ExpenseGroup.DoesNotExist:
        raise Http404()

    debts = calculate_expense_debts(expense)

    return render(request, "groups/expense_detail.html", {"expense": expense, "debts": debts})


class CreateExpense2(TemplateView):
    template_name = "groups/expense_form.html"

    def get_context_data(self, group_id, **kwargs):
        try:
            group = ExpenseGroup.objects.prefetch_related("expensegroupuser_set").get(pk=group_id)
        except ExpenseGroup.DoesNotExist:
            raise Http404

        data = super().get_context_data(group_id=group_id, **kwargs)
        if "form" not in data:
            data["form"] = ExpenseForm(group=group)
        data["group"] = group
        return data

    def post(self, request, group_id, **kwargs):
        try:
            group = ExpenseGroup.objects.prefetch_related("expensegroupuser_set").get(pk=group_id)
        except ExpenseGroup.DoesNotExist:
            raise Http404()

        form = ExpenseForm(group=group, data=request.POST)

        if form.is_valid():
            expense = form.save()
            return redirect("groups:expense", expense.id)

        return self.render_to_response({
            **self.get_context_data(group_id=group_id, **kwargs),
            "form": form,
        })


class ExpenseFormViewMixin:
    model = Expense

    def __init__(self, *args, is_settle_up: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._is_settle_up = is_settle_up

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
            return[ "groups/expense_form.html"]


class CreateExpense(ExpenseFormViewMixin, CreateView):
    def _get_group(self):
        return get_object_or_404(ExpenseGroup, pk=self.kwargs["group_id"])


class UpdateExpense(ExpenseFormViewMixin, UpdateView):
    pk_url_kwarg = "expense_id"
    context_object_name = "expense"

    def _get_group(self):
        return get_object_or_404(Expense, pk=self.kwargs["expense_id"]).group


class GroupSettings(UpdateView):
    model = ExpenseGroup
    context_object_name = "group"
    form_class = ExpenseGroupSettingsForm
    pk_url_kwarg = "group_id"
    template_name = "groups/settings.html"
