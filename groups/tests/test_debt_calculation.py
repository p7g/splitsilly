from datetime import date
from decimal import Decimal

import pytest

from groups import api
from groups.models import Expense

pytestmark = pytest.mark.django_db


def test_exact_split(expensegroup_with_users, users):
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
    )

    assert api.calculate_expense_debts(expense) == {
        a: 5000,
        b: 2500,
        c: 2500,
    }


def test_percentage_split(expensegroup_with_users, users):
    a, b, c = users["a"], users["b"], users["c"]

    expense = api.create_expense(
        expensegroup_with_users,
        "test",
        Expense.Type.PERCENTAGE,
        payer=a,
        date=date.today(),
        amount=200,
        split={
            a: ("50", 0),
            b: ("25", 0),
            c: ("25", 0),
        },
        exchange_rate=Decimal(1),
        currency_symbol="$",
    )

    assert api.calculate_expense_debts(expense) == {
        a: 100,
        b: 50,
        c: 50,
    }


def test_shares_split(expensegroup_with_users, users):
    a, b, c = users["a"], users["b"], users["c"]

    expense = api.create_expense(
        expensegroup_with_users,
        "test",
        Expense.Type.SHARES,
        payer=a,
        date=date.today(),
        amount=180,
        split={
            a: ("1", 0),
            b: ("1", 0),
            c: ("1", 0),
        },
        exchange_rate=Decimal(1),
        currency_symbol="$",
    )

    assert api.calculate_expense_debts(expense) == {
        a: 60,
        b: 60,
        c: 60,
    }

    expense = api.create_expense(
        expensegroup_with_users,
        "test",
        Expense.Type.SHARES,
        payer=a,
        date=date.today(),
        amount=200,
        split={
            a: ("1", 0),
            b: ("1", 0),
            c: ("1", 0),
        },
        exchange_rate=Decimal(1),
        currency_symbol="$",
    )

    assert api.calculate_expense_debts(expense) == {
        # Truncated
        a: 66,
        b: 66,
        c: 66,
    }

    expense = api.create_expense(
        expensegroup_with_users,
        "test",
        Expense.Type.SHARES,
        payer=a,
        date=date.today(),
        amount=200,
        split={
            a: ("1", 0),
            b: ("2", 0),
            c: ("1", 0),
        },
        exchange_rate=Decimal(1),
        currency_symbol="$",
    )

    assert api.calculate_expense_debts(expense) == {
        # Truncated
        a: 50,
        b: 100,
        c: 50,
    }


def test_adjustment_split(expensegroup_with_users, users):
    a, b, c = users["a"], users["b"], users["c"]

    expense = api.create_expense(
        expensegroup_with_users,
        "test",
        Expense.Type.SHARES,
        payer=a,
        date=date.today(),
        amount=30,
        split={
            a: ("1", 3),
            b: ("1", -2),
            c: ("1", 5),
        },
        exchange_rate=Decimal(1),
        currency_symbol="$",
    )

    assert api.calculate_expense_debts(expense) == {
        a: 11,
        b: 6,
        c: 13,
    }


def test_group_expenses(expensegroup_with_users, users):
    a, b, c = users["a"], users["b"], users["c"]

    assert not expensegroup_with_users.expense_set.exists()

    api.create_expense(
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
    )
    api.create_expense(
        expensegroup_with_users,
        "test",
        Expense.Type.SHARES,
        payer=b,
        date=date.today(),
        amount=20000,
        split={
            a: ("1", 0),
            b: ("1", 0),
            c: ("1", 0),
        },
        exchange_rate=Decimal(1),
        currency_symbol="$",
    )
    api.create_expense(
        expensegroup_with_users,
        "test",
        Expense.Type.SHARES,
        payer=c,
        date=date.today(),
        amount=3000,
        split={
            a: ("1", 3),
            b: ("1", -2),
            c: ("1", 5),
        },
        exchange_rate=Decimal(1),
        currency_symbol="$",
    )

    assert api.calculate_debts(expensegroup_with_users) == {
        (b, a): 2500,
        (c, a): 2500,
        (a, b): 6666,
        (c, b): 6666,
        (a, c): 1001,
        (b, c): 996,
    }

    assert api.simplify_debts(api.calculate_debts(expensegroup_with_users)) == {
        (a, b): 2667,
        (c, b): 7169,
    }
