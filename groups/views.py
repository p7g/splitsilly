import calendar
from typing import Any, cast

import yarl
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.forms import ModelForm
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import CreateView, DeleteView, FormView, UpdateView

from splitsilly.utils.lock import Lock

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
from .tasks import (
    send_expense_added_emails,
    send_expense_updated_emails,
    send_group_invite_consumed_email,
)


@login_required
def groups_index(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        raise Http404
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
def group_home(request: HttpRequest, group_id: int) -> HttpResponse:
    assert request.user.is_authenticated
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

    expenses_by_year_month: list[tuple[int, str, list[Expense]]] = []
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
def expense_detail(request: HttpRequest, expense_id: int) -> HttpResponse:
    assert request.user.is_authenticated
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

    def __init__(self, *args: Any, is_settle_up: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._is_settle_up = is_settle_up

    def get_queryset(self) -> QuerySet[Expense]:
        return super().get_queryset().for_user(self.request.user)  # type: ignore

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()  # type: ignore
        kwargs["group"] = self._get_group()  # type: ignore
        return kwargs  # type: ignore

    def is_settle_up(self) -> bool:
        expense = cast(Expense | None, self.object)  # type: ignore
        return self._is_settle_up or (expense is not None and expense.is_settle_up)

    def get_form_class(self) -> type[ModelForm[Expense]]:
        if self.is_settle_up():
            return SettleUpForm
        else:
            return ExpenseForm

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        data = super().get_context_data(**kwargs)  # type: ignore
        data["group"] = data["form"]._group
        return data  # type: ignore

    def get_template_names(self) -> list[str]:
        if self.is_settle_up():
            return ["groups/settle_up.html"]
        else:
            return ["groups/expense_form.html"]


class CreateExpense(ExpenseFormViewMixin, CreateView[Expense, ModelForm[Expense]]):
    def _get_group(self) -> ExpenseGroup:
        assert self.request.user.is_authenticated
        return get_object_or_404(
            ExpenseGroup.objects.for_user(self.request.user), pk=self.kwargs["group_id"]
        )

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        initial["payer"] = self.request.user
        return initial

    def form_valid(self, form: ModelForm[Expense]) -> HttpResponse:
        result = super().form_valid(form)

        # Email everyone except the creator
        expense = self.object
        assert isinstance(expense, Expense)
        send_expense_added_emails(expense.id, self.request.user.id)

        return result


class UpdateExpense(ExpenseFormViewMixin, UpdateView[Expense, ModelForm[Expense]]):
    pk_url_kwarg = "expense_id"
    context_object_name = "expense"

    def _get_group(self) -> ExpenseGroup:
        assert self.request.user.is_authenticated
        return get_object_or_404(
            Expense.objects.for_user(self.request.user), pk=self.kwargs["expense_id"]
        ).group

    def form_valid(self, form: ModelForm[Expense]) -> HttpResponse:
        result = super().form_valid(form)

        # Email everyone except the creator
        expense = self.object
        assert isinstance(expense, Expense)
        send_expense_updated_emails(expense.id, self.request.user.id)

        return result


class DeleteExpense(DeleteView[Expense, ModelForm[Expense]]):
    pk_url_kwarg = "expense_id"
    context_object_name = "expense"
    model = Expense

    def get_queryset(self) -> QuerySet[Expense]:
        return super().get_queryset().for_user(self.request.user)  # type: ignore

    def get_success_url(self) -> str:
        return self.object.group.get_absolute_url()


class CreateGroup(LoginRequiredMixin, CreateView[ExpenseGroup, ExpenseGroupForm]):
    model = ExpenseGroup
    form_class = ExpenseGroupForm
    context_object_name = "group"
    template_name = "groups/create.html"

    def form_valid(self, form: ExpenseGroupForm) -> HttpResponse:
        resp = super().form_valid(form)
        assert self.object is not None
        assert self.request.user.is_authenticated
        add_expense_group_user(self.object, self.request.user)
        return resp


class GroupSettings(
    LoginRequiredMixin, UpdateView[ExpenseGroup, ModelForm[ExpenseGroup]]
):
    model = ExpenseGroup
    context_object_name = "group"
    form_class = ExpenseGroupSettingsForm
    pk_url_kwarg = "group_id"
    template_name = "groups/settings.html"

    def get_queryset(self) -> QuerySet[ExpenseGroup]:
        return super().get_queryset().for_user(self.request.user)  # type: ignore

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {
            **super().get_context_data(**kwargs),
            "pending_invites": self.object.expensegroupinvite_set.filter(
                consumed_by=None
            ),
        }


def get_valid_invite(invite_id: str) -> ExpenseGroupInvite | None:
    try:
        return ExpenseGroupInvite.objects.get(id=invite_id, consumed_by=None)
    except ExpenseGroupInvite.DoesNotExist:
        return None


def invite_detail_view(request: HttpRequest, invite_id: str) -> HttpResponse:
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
def consume_invite_view(request: HttpRequest, invite_id: str) -> HttpResponse:
    with Lock(str(invite_id)):
        invite = get_valid_invite(invite_id)
        if not invite:
            return render(request, "groups/invite_invalid.html")

        assert request.user.is_authenticated
        if not invite.group.expensegroupuser_set.filter(user=request.user).exists():
            add_expense_group_user(invite.group, request.user)
        invite.consumed_by = request.user
        invite.save(update_fields=["updated_at", "consumed_by"])

    send_group_invite_consumed_email(invite.id)

    return redirect(invite.group)


class GroupInviteView(LoginRequiredMixin, FormView[GroupInviteForm]):
    form_class = GroupInviteForm
    template_name = "groups/invite_form.html"

    def _get_group(self) -> ExpenseGroup:
        assert self.request.user.is_authenticated
        if self.request.resolver_match is None:
            raise Http404
        return get_object_or_404(
            ExpenseGroup.objects.for_user(self.request.user).filter(
                id=self.request.resolver_match.kwargs["group_id"]
            )
        )

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        # This will 404 if the user doesn't have access to the group
        self._get_group()
        return super().get(request, *args, **kwargs)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        # This will 404 if the user doesn't have access to the group
        self._get_group()
        return super().post(request, *args, **kwargs)

    def get_initial(self) -> dict[str, Any]:
        return {
            **super().get_initial(),
            "emails": [],
        }

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {
            **super().get_context_data(**kwargs),
            "group": self._get_group(),
        }

    def form_valid(self, form: GroupInviteForm) -> HttpResponse:
        assert self.request.user.is_authenticated
        emails = form.cleaned_data["emails"]
        group = self._get_group()

        for email in emails:
            send_group_invite(group, self.request.user, email)

        return redirect("groups:group_settings", group_id=group.id)
