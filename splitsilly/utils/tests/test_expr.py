from decimal import Decimal

from splitsilly.utils.expr import evaluate


def test_number():
    assert evaluate("1") == Decimal(1)


def test_binop():
    assert evaluate("1 + 1") == Decimal(2)
    assert evaluate("1 - 1") == Decimal(0)
    assert evaluate("2 * 4") == Decimal(8)
    assert evaluate("4 / 3") == Decimal(4) / Decimal(3)


def test_unop():
    assert evaluate("-1") == -Decimal(1)


def test_precedence():
    assert evaluate("2 + 3 * 4") == Decimal(14)
    assert evaluate("(2 + 3) * 4") == Decimal(20)


def test_env():
    assert evaluate("hello", {"hello": Decimal(123)}) == Decimal(123)
