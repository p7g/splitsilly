from groups.api import simplify_debts


def test_transitive_debt_simple():
    debts = {
        ("a", "b"): 100,
        ("b", "c"): 100,
    }

    assert simplify_debts(debts) == {("a", "c"): 100}


def test_transitive_debt_owes_excess():
    debts = {
        ("a", "b"): 200,
        ("b", "c"): 100,
    }
    assert simplify_debts(debts) == {("a", "c"): 100, ("a", "b"): 100}


def test_transitive_debt_owes_less():
    debts = {
        ("a", "b"): 100,
        ("b", "c"): 200,
    }
    assert simplify_debts(debts) == {("a", "c"): 100, ("b", "c"): 100}


def test_mutual_debt_equal():
    debts = {
        ("a", "b"): 100,
        ("b", "a"): 100,
    }
    assert simplify_debts(debts) == {}


def test_mutual_debt_greater():
    debts = {
        ("a", "b"): 101,
        ("b", "a"): 100,
    }
    assert simplify_debts(debts) == {("a", "b"): 1}


def test_mutual_debt_less():
    debts = {
        ("a", "b"): 99,
        ("b", "a"): 100,
    }
    assert simplify_debts(debts) == {("b", "a"): 1}


def test_3_cycle():
    debts = {
        ("a", "b"): 1,
        ("b", "c"): 1,
        ("c", "a"): 1,
    }
    assert simplify_debts(debts) == {}
