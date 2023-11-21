from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from django.core.exceptions import ValidationError

from identity.models import User

from .models import Expense, ExpenseGroup, ExpenseGroupUser, ExpenseSplit


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


def validate_expense_split(type_: Expense.Type, amount: int, split: dict[User, int]):
    if type_ == Expense.Type.EXACT:
        if amount != sum(split.values()):
            raise ValidationError("Split does not add to amount")
    elif type_ == Expense.Type.PERCENTAGE:
        if sum(split.values()) != 100:
            raise ValidationError("Split percentages do not add to 100")
    elif type_ == Expense.Type.SHARES:
        if all(shares == 0 for shares in split.values()):
            raise ValidationError("The total number of shares must be at least 1")
        if any(shares < 0 for shares in split.values()):
            raise ValidationError("Shares must be positive of zero")


def create_expense(
    group: ExpenseGroup,
    name: str,
    type_: Expense.Type,
    payer: User,
    date: date,
    amount: int,
    split: dict[User, int],
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
        ExpenseSplit(expense=expense, user=user, shares=shares)
        for user, shares in split.items()
    )

    return expense


def update_expense(
    expense: Expense,
    name: str,
    type_: Expense.Type,
    payer: User,
    date: date,
    amount: int,
    split: dict[User, int],
) -> None:
    expense.name = name
    expense.type = type_
    expense.payer = payer
    expense.date = date
    expense.amount = amount
    expense.save()

    old_split = {
        split.user: split.shares
        for split in expense.expensesplit_set.select_related("user")
    }
    expense.expensesplit_set.filter(user__in=old_split.keys() - split.keys()).delete()
    existing_splits = expense.expensesplit_set.all()
    for existing_split in existing_splits:
        existing_split.shares = split[existing_split.user]
    ExpenseSplit.objects.bulk_update(existing_splits, ["shares"])
    ExpenseSplit.objects.bulk_create(
        ExpenseSplit(expense=expense, user=user, shares=split[user])
        for user in split.keys() - old_split.keys()
    )


def calculate_debts(group: ExpenseGroup) -> dict[tuple[User, User], int]:
    debts = {}

    for expense in group.expense_set.prefetch_related(
        "payer", "expensesplit_set__user"
    ):
        expense_debts = calculate_expense_debts(expense)
        for owee, debt in expense_debts.items():
            if owee == expense.payer:
                continue
            if (owee, expense.payer) not in debts:
                debts[owee, expense.payer] = 0
            debts[owee, expense.payer] += debt

    return debts


def shares_are_money(expense_type: Expense.Type) -> bool:
    return expense_type in (Expense.Type.EXACT, Expense.Type.ADJUSTMENT)


def float_to_money(value: float) -> int:
    return int(value * 100)


def money_to_float(value: int) -> float:
    return float(value) / 100


def calculate_expense_debts(expense: Expense) -> dict[User, int]:
    debts = _calculate_expense_debts(expense)
    return {user: amount for user, amount in debts.items() if amount}


def _calculate_expense_debts(expense: Expense) -> dict[User, int]:
    splits = expense.expensesplit_set.select_related("user").all()

    if expense.type == Expense.Type.EXACT:
        return {split.user: split.shares for split in splits}
    elif expense.type == Expense.Type.PERCENTAGE:
        return {
            split.user: int(expense.amount * (float(split.shares) / 100))
            for split in splits
        }
    elif expense.type == Expense.Type.SHARES:
        total_shares = sum(split.shares for split in splits)
        return {
            split.user: int(expense.amount * float(split.shares) / total_shares)
            for split in splits
        }
    elif expense.type == Expense.Type.ADJUSTMENT:
        base_debt = int(
            (expense.amount - sum(split.shares for split in splits)) / len(splits)
        )
        return {split.user: base_debt + split.shares for split in splits}
    else:
        raise NotImplementedError(expense.type)


def simplify_debts(debts: dict[tuple[User, User], int]) -> dict[tuple[User, User], int]:
    all_users = {user for edge in debts.keys() for user in edge}

    lenders_by_user = defaultdict(set)
    for ower, lender in debts:
        lenders_by_user[ower].add(lender)

    new_debts = debts.copy()

    # Mutual owing
    for a in all_users:
        for b in all_users:
            if a == b:
                assert (a, b) not in new_debts
                continue

            if (a, b) in new_debts and (b, a) in new_debts:
                a_owes_b = new_debts.pop((a, b))
                b_owes_a = new_debts.pop((b, a))
                lenders_by_user[a].discard(b)
                lenders_by_user[b].discard(a)

                diff = a_owes_b - b_owes_a
                if diff == 0:
                    continue
                elif diff > 0:
                    new_debts[a, b] = diff
                    lenders_by_user[a].add(b)
                else:
                    new_debts[b, a] = -diff
                    lenders_by_user[b].add(a)

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
                a_owes_b = new_debts.pop((a, b))
                b_owes_c = new_debts.pop((b, c))
                lenders_by_user[a].discard(b)
                lenders_by_user[b].discard(c)

                if a == c:
                    continue

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
        {payee: 1},
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
        {payee: 1},
    )
