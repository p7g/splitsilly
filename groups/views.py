import calendar

import yarl
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import CreateView, DeleteView, FormView, UpdateView

from .api import (
    add_expense_group_user,
    calculate_debts,
    calculate_expense_debts,
    send_group_invite,
    simplify_debts,
    simplify_mutual_owing,
)
from .forms import (
    ExpenseForm,
    ExpenseGroupForm,
    ExpenseGroupSettingsForm,
    GroupInviteForm,
    SettleUpForm,
)
from .models import Expense, ExpenseGroup, ExpenseGroupInvite
from .tasks import send_expense_added_emails, send_expense_updated_emails, send_group_invite_consumed_email


@login_required
def groups_index(request):
    groups = ExpenseGroup.objects.for_user(request.user).prefetch_related(
        "expense_set__payer", "expense_set__expensesplit_set__user"
    )

    groups_and_amount_owed = []
    for group in groups:
        debts = calculate_debts(group)
        if group.simplify_debts:
            debts = simplify_debts(debts)
        else:
            debts = simplify_mutual_owing(debts)

        viewer_owes = 0
        for borrower, lender in debts:
            if borrower == request.user:
                viewer_owes += debts[borrower, lender]
            elif lender == request.user:
                viewer_owes -= debts[borrower, lender]

        groups_and_amount_owed.append((group, viewer_owes))

    return render(
        request,
        "groups/home.html",
        {
            "groups_and_amount_owed": groups_and_amount_owed,
        },
    )


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
        send_expense_added_emails(expense.id, self.request.user.id)

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
        send_expense_updated_emails(expense.id, self.request.user.id)

        return result


class DeleteExpense(DeleteView):
    pk_url_kwarg = "expense_id"
    context_object_name = "expense"
    model = Expense

    def get_queryset(self):
        return super().get_queryset().for_user(self.request.user)

    def get_success_url(self):
        return self.object.group.get_absolute_url()


class CreateGroup(LoginRequiredMixin, CreateView):
    model = ExpenseGroup
    form_class = ExpenseGroupForm
    context_object_name = "group"
    template_name = "groups/create.html"

    def form_valid(self, form):
        resp = super().form_valid(form)
        assert self.object is not None
        add_expense_group_user(self.object, self.request.user)
        return resp


class GroupSettings(LoginRequiredMixin, UpdateView):
    model = ExpenseGroup
    context_object_name = "group"
    form_class = ExpenseGroupSettingsForm
    pk_url_kwarg = "group_id"
    template_name = "groups/settings.html"

    def get_queryset(self):
        return super().get_queryset().for_user(self.request.user)

    def get_context_data(self):
        return {
            **super().get_context_data(),
            "pending_invites": self.object.expensegroupinvite_set.filter(
                consumed_by=None
            ),
        }


def get_valid_invite(invite_id):
    return ExpenseGroupInvite.objects.get(id=invite_id, consumed_by=None)


def invite_detail_view(request, invite_id):
    if request.user.is_authenticated:
        return redirect("groups:consume_invite", invite_id=invite_id)

    invite = get_valid_invite(invite_id)
    if not invite:
        return render(request, "groups/invite_invalid.html")

    context = {
        "invite": invite,
        "login_url": yarl.URL(reverse("identity:login")).with_query(next=request.path),
        "signup_url": yarl.URL(reverse("identity:signup")).with_query(
            invite_id=str(invite_id)
        ),
    }
    return render(request, "groups/invite_detail.html", context)


@login_required
def consume_invite_view(request, invite_id):
    invite = get_valid_invite(invite_id)
    if not invite:
        return render(request, "groups/invite_invalid.html")

    # FIXME: race condition
    if not invite.group.expensegroupuser_set.filter(user=request.user).exists():
        add_expense_group_user(invite.group, request.user)
    invite.consumed_by = request.user
    invite.save(update_fields=["updated_at", "consumed_by"])

    send_group_invite_consumed_email(invite.id)

    return redirect(invite.group)


class GroupInviteView(LoginRequiredMixin, FormView):
    form_class = GroupInviteForm
    template_name = "groups/invite_form.html"

    def _get_group(self):
        return get_object_or_404(
            ExpenseGroup.objects.for_user(self.request.user).filter(
                id=self.request.resolver_match.kwargs["group_id"]
            )
        )

    def get(self, request, *args, **kwargs):
        # This will 404 if the user doesn't have access to the group
        self._get_group()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        # This will 404 if the user doesn't have access to the group
        self._get_group()
        return super().post(request, *args, **kwargs)

    def get_initial(self):
        return {
            **super().get_initial(),
            "emails": [],
        }

    def get_context_data(self):
        return {
            **super().get_context_data(),
            "group": self._get_group(),
        }

    def form_valid(self, form):
        emails = form.cleaned_data["emails"]
        group = self._get_group()

        for email in emails:
            send_group_invite(group, self.request.user, email)

        return redirect("groups:group_settings", group_id=group.id)
