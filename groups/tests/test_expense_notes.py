from datetime import date
from decimal import Decimal

import pytest

from groups import api
from groups.forms import ExpenseForm
from groups.models import Expense

pytestmark = pytest.mark.django_db


def test_create_expense_persists_note(expensegroup_with_users, users):
    a, b, c = users["a"], users["b"], users["c"]

    expense = api.create_expense(
        expensegroup_with_users,
        "test",
        Expense.Type.EXACT,
        payer=a,
        date=date.today(),
        amount=10000,
        split={
            a: ("50", 0),
            b: ("25", 0),
            c: ("25", 0),
        },
        exchange_rate=Decimal(1),
        currency_symbol="$",
        note="Paid back in cash",
    )

    expense.refresh_from_db()

    assert expense.note == "Paid back in cash"


def test_expense_form_preloads_existing_note(expensegroup_with_users, users):
    a, b, c = users["a"], users["b"], users["c"]

    expense = api.create_expense(
        expensegroup_with_users,
        "test",
        Expense.Type.EXACT,
        payer=a,
        date=date.today(),
        amount=10000,
        split={
            a: ("50", 0),
            b: ("25", 0),
            c: ("25", 0),
        },
        exchange_rate=Decimal(1),
        currency_symbol="$",
        note="Need reimbursement by Friday",
    )

    form = ExpenseForm(group=expensegroup_with_users, instance=expense)

    assert form.initial["note"] == "Need reimbursement by Friday"
