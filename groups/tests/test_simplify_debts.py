import pytest

from groups.api import simplify_debts

pytestmark = pytest.mark.django_db


def test_transitive_debt_simple(users):
    a, b, c = users["a"], users["b"], users["c"]

    debts = {
        (a, b): 100,
        (b, c): 100,
    }

    assert simplify_debts(debts) == {(a, c): 100}


def test_transitive_debt_owes_excess(users):
    a, b, c = users["a"], users["b"], users["c"]

    debts = {
        (a, b): 200,
        (b, c): 100,
    }
    assert simplify_debts(debts) == {(a, c): 100, (a, b): 100}


def test_transitive_debt_owes_less(users):
    a, b, c = users["a"], users["b"], users["c"]

    debts = {
        (a, b): 100,
        (b, c): 200,
    }
    assert simplify_debts(debts) == {(a, c): 100, (b, c): 100}


def test_mutual_debt_equal(users):
    a, b, c = users["a"], users["b"], users["c"]

    debts = {
        (a, b): 100,
        (b, a): 100,
    }
    assert simplify_debts(debts) == {}


def test_mutual_debt_greater(users):
    a, b, c = users["a"], users["b"], users["c"]

    debts = {
        (a, b): 101,
        (b, a): 100,
    }
    assert simplify_debts(debts) == {(a, b): 1}


def test_mutual_debt_less(users):
    a, b, c = users["a"], users["b"], users["c"]

    debts = {
        (a, b): 99,
        (b, a): 100,
    }
    assert simplify_debts(debts) == {(b, a): 1}


def test_3_cycle(users):
    a, b, c = users["a"], users["b"], users["c"]

    debts = {
        (a, b): 1,
        (b, c): 1,
        (c, a): 1,
    }
    assert simplify_debts(debts) == {}


def test_bug(users):
    a, b, c = users["a"], users["b"], users["c"]

    debts = {
        (a, b): 4102,
        (c, b): 113591,
        (b, a): 5819,
        (c, a): 103234,
        (a, c): 108420,
        (b, c): 111874,
    }

    assert simplify_debts(debts) == {(a, c): 3469}
