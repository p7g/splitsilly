from datetime import date

import pytest

from groups import api
from groups.models import Expense, ExpenseGroup, ExpenseGroupUser, ExpenseSplit

pytestmark = pytest.mark.django_db


@pytest.fixture
def expense_group():
    group = api.create_expense_group("test")
    api.add_expense_group_user(group, "A")
    api.add_expense_group_user(group, "B")
    api.add_expense_group_user(group, "C")
    return group


def test_exact_split(expense_group):
    expense = api.create_expense(
        expense_group,
        Expense.Type.EXACT,
        payer="A",
        date=date.today(),
        amount=100,
        split={
            "A": 50,
            "B": 25,
            "C": 25,
        },
    )

    assert api.calculate_expense_debts(expense) == {
        "A": 50,
        "B": 25,
        "C": 25,
    }


def test_percentage_split(expense_group):
    expense = api.create_expense(
        expense_group,
        Expense.Type.PERCENTAGE,
        payer="A",
        date=date.today(),
        amount=200,
        split={
            "A": 50,
            "B": 25,
            "C": 25,
        },
    )

    assert api.calculate_expense_debts(expense) == {
        "A": 100,
        "B": 50,
        "C": 50,
    }


def test_shares_split(expense_group):
    expense = api.create_expense(
        expense_group,
        Expense.Type.SHARES,
        payer="A",
        date=date.today(),
        amount=180,
        split={
            "A": 1,
            "B": 1,
            "C": 1,
        },
    )

    assert api.calculate_expense_debts(expense) == {
        "A": 60,
        "B": 60,
        "C": 60,
    }

    expense = api.create_expense(
        expense_group,
        Expense.Type.SHARES,
        payer="A",
        date=date.today(),
        amount=200,
        split={
            "A": 1,
            "B": 1,
            "C": 1,
        },
    )

    assert api.calculate_expense_debts(expense) == {
        # Truncated
        "A": 66,
        "B": 66,
        "C": 66,
    }

    expense = api.create_expense(
        expense_group,
        Expense.Type.SHARES,
        payer="A",
        date=date.today(),
        amount=200,
        split={
            "A": 1,
            "B": 2,
            "C": 1,
        },
    )

    assert api.calculate_expense_debts(expense) == {
        # Truncated
        "A": 50,
        "B": 100,
        "C": 50,
    }


def test_adjustment_split(expense_group):
    expense = api.create_expense(
        expense_group,
        Expense.Type.ADJUSTMENT,
        payer="A",
        date=date.today(),
        amount=30,
        split={
            "A": 3,
            "B": -2,
            "C": 5,
        },
    )

    assert api.calculate_expense_debts(expense) == {
        "A": 11,
        "B": 6,
        "C": 13,
    }


def test_group_expenses(expense_group):
    assert not expense_group.expense_set.exists()

    api.create_expense(
        expense_group,
        Expense.Type.EXACT,
        payer="A",
        date=date.today(),
        amount=100,
        split={
            "A": 50,
            "B": 25,
            "C": 25,
        },
    )
    api.create_expense(
        expense_group,
        Expense.Type.SHARES,
        payer="B",
        date=date.today(),
        amount=200,
        split={
            "A": 1,
            "B": 1,
            "C": 1,
        },
    )
    api.create_expense(
        expense_group,
        Expense.Type.ADJUSTMENT,
        payer="C",
        date=date.today(),
        amount=30,
        split={
            "A": 3,
            "B": -2,
            "C": 5,
        },
    )

    assert api.calculate_debts(expense_group) == {
        ("B", "A"): 25,
        ("C", "A"): 25,
        ("A", "B"): 66,
        ("C", "B"): 66,
        ("A", "C"): 11,
        ("B", "C"): 6,
    }

    assert api.simplify_debts(api.calculate_debts(expense_group)) == {
        ("A", "B"): 27,
        ("C", "B"): 74,
    }
