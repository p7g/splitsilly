from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import sentry_sdk
from ddtrace import tracer
from django.core.exceptions import ValidationError

from identity.models import User

from .models import Expense, ExpenseGroup, ExpenseGroupUser, ExpenseSplit
from .templatetags.money import to_dollars

# User: (shares, adjustment)
Split = dict[User, tuple[int, int]]
Debts = dict[tuple[User, User], int]


def create_expense_group(name: str) -> ExpenseGroup:
    return ExpenseGroup.objects.create(name=name)


def add_expense_group_user(group: ExpenseGroup, user: User) -> ExpenseGroupUser:
    return group.expensegroupuser_set.create(user=user)


def sync_expense_group_users(group: ExpenseGroup, users: Sequence[User]) -> None:
    new_users = set(users)
    existing_users = {
        gu.user for gu in group.expensegroupuser_set.select_related("user")
    }

    to_remove = existing_users - new_users
    group.expensegroupuser_set.filter(user__in=to_remove).delete()

    to_add = new_users - existing_users
    ExpenseGroupUser.objects.bulk_create(
        ExpenseGroupUser(group=group, user=user) for user in to_add
    )


def validate_expense_split(type_: Expense.Type, amount: int, split: Split):
    if type_ == Expense.Type.EXACT:
        total = sum(shares + adjustment for shares, adjustment in split.values())
        if amount != total:
            raise ValidationError(
                f"Split must add to {to_dollars(amount)}, got {to_dollars(total)}"
            )
    elif type_ == Expense.Type.PERCENTAGE:
        total = sum(shares for shares, _adjustment in split.values())
        if total != 100:
            raise ValidationError(f"Split percentages must add to 100, got {total}")
    elif type_ == Expense.Type.SHARES:
        if all(shares == 0 for shares, _adjustment in split.values()):
            raise ValidationError("The total number of shares must be at least 1")
        if any(shares < 0 for shares, _adjustment in split.values()):
            raise ValidationError("Shares must be positive of zero")


def create_expense(
    group: ExpenseGroup,
    name: str,
    type_: Expense.Type,
    payer: User,
    date: date,
    amount: int,
    split: Split,
    _is_settle_up: bool = False,
) -> Expense:
    validate_expense_split(type_, amount, split)
    expense = Expense.objects.create(
        group=group,
        name=name,
        type=type_,
        payer=payer,
        date=date,
        amount=amount,
        is_settle_up=_is_settle_up,
    )

    ExpenseSplit.objects.bulk_create(
        ExpenseSplit(expense=expense, user=user, shares=shares, adjustment=adjustment)
        for user, (shares, adjustment) in split.items()
    )

    return expense


def update_expense(
    expense: Expense,
    name: str,
    type_: Expense.Type,
    payer: User,
    date: date,
    amount: int,
    split: Split,
) -> None:
    expense.name = name
    expense.type = type_
    expense.payer = payer
    expense.date = date
    expense.amount = amount
    expense.save()

    old_split = {
        split.user: (split.shares, split.adjustment)
        for split in expense.expensesplit_set.select_related("user")
    }
    expense.expensesplit_set.filter(user__in=old_split.keys() - split.keys()).delete()
    existing_splits = expense.expensesplit_set.all()
    for existing_split in existing_splits:
        existing_split.shares, existing_split.adjustment = split[existing_split.user]
    ExpenseSplit.objects.bulk_update(
        existing_splits, ["adjustment", "shares", "updated_at"]
    )
    ExpenseSplit.objects.bulk_create(
        ExpenseSplit(
            expense=expense, user=user, shares=split[user][0], adjustment=split[user][1]
        )
        for user in split.keys() - old_split.keys()
    )


@tracer.wrap()
def calculate_debts(group: ExpenseGroup) -> Debts:
    debts = {}

    for expense in group.expense_set.prefetch_related(
        "payer", "expensesplit_set__user"
    ):
        expense_debts = calculate_expense_debts(expense)
        for borrower, debt in expense_debts.items():
            if borrower == expense.payer:
                continue
            if (borrower, expense.payer) not in debts:
                debts[borrower, expense.payer] = 0
            debts[borrower, expense.payer] += debt

    return debts


def shares_are_money(expense_type: Expense.Type) -> bool:
    return expense_type in (Expense.Type.EXACT, Expense.Type.ADJUSTMENT)


def float_to_money(value: Decimal) -> int:
    return int(value * 100)


def money_to_float(value: int) -> float:
    return float(value) / 100


@tracer.wrap()
def calculate_expense_debts(expense: Expense) -> dict[User, int]:
    debts = _calculate_expense_debts(expense)
    return {user: amount for user, amount in debts.items() if amount}


def _calculate_expense_debts(expense: Expense) -> dict[User, int]:
    splits = expense.expensesplit_set.select_related("user").all()

    if expense.type == Expense.Type.EXACT:
        return {split.user: split.shares + split.adjustment for split in splits}

    base_amount = expense.amount - sum(split.adjustment for split in splits)
    total_shares = sum(split.shares for split in splits)

    if expense.type in (Expense.Type.SHARES, Expense.Type.PERCENTAGE):
        debt = {
            split.user: int(base_amount * float(split.shares) / total_shares)
            for split in splits
        }
    else:
        raise NotImplementedError(expense.type)
    return {split.user: debt[split.user] + split.adjustment for split in splits}


@tracer.wrap()
def simplify_debts(debts: Debts) -> Debts:
    i = 0
    for i in range(1, 11):
        new_debts = simplify_mutual_owing(debts)
        new_debts = _simplify_transient_debts(new_debts)
        if new_debts == debts:
            break
        debts = new_debts
    else:
        sentry_sdk.capture_message(
            "Failed to simplify debts after 10 tries", level="error"
        )
    with tracer.current_span() as span:
        if span:
            span.set_tag("iterations", i)
    return debts


@tracer.wrap()
def simplify_mutual_owing(debts: Debts) -> Debts:
    all_users = {user for edge in debts.keys() for user in edge}
    new_debts = debts.copy()

    for a in all_users:
        for b in all_users:
            if a == b:
                assert (a, b) not in new_debts
                continue

            if (a, b) in new_debts and (b, a) in new_debts:
                a_owes_b = new_debts.pop((a, b))
                b_owes_a = new_debts.pop((b, a))

                diff = a_owes_b - b_owes_a
                if diff == 0:
                    continue
                elif diff > 0:
                    new_debts[a, b] = diff
                else:
                    new_debts[b, a] = -diff

    return new_debts


@tracer.wrap()
def _simplify_transient_debts(debts: Debts) -> Debts:
    all_users = {user for edge in debts.keys() for user in edge}
    new_debts = debts.copy()
    lenders_by_user = defaultdict(set)
    for ower, lender in debts:
        lenders_by_user[ower].add(lender)

    for a in all_users:
        for b in all_users:
            if a == b:
                assert (a, b) not in new_debts
                continue

            # Does A owe to B and B owe money to one person?
            # A -> B -> C
            # A -> C (and maybe A -> B or B -> C)
            lenders_to_b = lenders_by_user[b]
            if new_debts.get((a, b)) and len(lenders_to_b) == 1:
                (c,) = lenders_to_b
                if a == c:
                    continue

                a_owes_b = new_debts.pop((a, b))
                b_owes_c = new_debts.pop((b, c))
                lenders_by_user[a].discard(b)
                lenders_by_user[b].discard(c)

                # If A owes more to B than B owes to C, A owes C that amount
                # and B the remainder. Otherwise, A owes C the amount A owed to
                # B and B still owes the remainder to C.

                new_debts.setdefault((a, c), 0)
                if a_owes_b >= b_owes_c:
                    new_debts[a, c] += b_owes_c
                    lenders_by_user[a].add(c)
                    if a_owes_b != b_owes_c:
                        new_debts[a, b] = a_owes_b - b_owes_c
                        lenders_by_user[a].add(b)
                else:
                    new_debts[a, c] += a_owes_b
                    new_debts[b, c] = b_owes_c - a_owes_b
                    lenders_by_user[a].add(c)
                    lenders_by_user[b].add(c)

    return new_debts


def settle_up(
    group: ExpenseGroup, payer: User, date: date, payee: User, amount: int
) -> Expense:
    return create_expense(
        group,
        "Settling up",
        Expense.Type.SHARES,
        payer,
        date,
        amount,
        {payee: (1, 0)},
        _is_settle_up=True,
    )


def update_settle_up(
    expense: Expense, payer: User, date: date, payee: User, amount: int
) -> None:
    update_expense(
        expense,
        "Settling up",
        Expense.Type.SHARES,
        payer,
        date,
        amount,
        {payee: (1, 0)},
    )
