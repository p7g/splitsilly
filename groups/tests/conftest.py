import pytest

from groups import api as groups_api
from groups.models import ExpenseGroup
from identity.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def expensegroup():
    return ExpenseGroup.objects.create(name="test")


@pytest.fixture
def users():
    return {
        "a": User.objects.create_user("a", "a@example.com", "x"),
        "b": User.objects.create_user("b", "b@example.com", "x"),
        "c": User.objects.create_user("c", "c@example.com", "x"),
    }


@pytest.fixture
def expensegroup_with_users(expensegroup, users):
    for user in users.values():
        groups_api.add_expense_group_user(expensegroup, user)
    return expensegroup
