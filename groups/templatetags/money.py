from django import template

register = template.Library()


@register.filter
def to_dollars(value: int, currency_symbol: str = "$") -> str:
    assert isinstance(value, int)

    dollars = value // 100
    cents = value % 100

    return f"{currency_symbol}{dollars}.{cents:02d}"
