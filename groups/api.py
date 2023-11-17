from collections import defaultdict
from datetime import date

from .models import ExpenseGroup, ExpenseGroupUser, Expense, ExpenseSplit


def create_expense_group(name: str) -> ExpenseGroup:
    return ExpenseGroup.objects.create(name=name)


def add_expense_group_user(group: ExpenseGroup, user: str) -> ExpenseGroupUser:
    return group.expensegroupuser_set.create(name=user)


def _validate_expense_split(type_: Expense.Type, amount: int, split: dict[str, int]):
    if type_ == Expense.Type.EXACT:
        if amount != sum(split.values()):
            raise ValueError("Split does not add to amount")
    elif type_ == Expense.Type.PERCENTAGE:
        if sum(split.values()) != 100:
            raise ValueError("Split percentages do not add to 100")


def create_expense(
    group: ExpenseGroup, type_: Expense.Type, payer: str, date: date, amount: int, split: dict[str, int]
) -> Expense:
    _validate_expense_split(type_, amount, split)
    expense = Expense.objects.create(group=group, type=type_, payer=payer, date=date, amount=amount)

    ExpenseSplit.objects.bulk_create(
        ExpenseSplit(expense=expense, user=user, shares=shares) for user, shares in split.items()
    )

    return expense


def calculate_debts(group: ExpenseGroup) -> dict[tuple[str, str], int]:
    debt_edges = {}

    for expense in group.expense_set.prefetch_related("expensesplit_set"):
        expense_debts = calculate_expense_debts(expense)
        for owee, debt in expense_debts.items():
            if owee == expense.payer:
                continue
            if (owee, expense.payer) not in debt_edges:
                debt_edges[owee, expense.payer] = 0
            debt_edges[owee, expense.payer] += debt

    return debt_edges


def calculate_expense_debts(expense: Expense) -> dict[str, int]:
    splits = expense.expensesplit_set.all()

    if expense.type == Expense.Type.EXACT:
        return {split.user: split.shares for split in splits}
    elif expense.type == Expense.Type.PERCENTAGE:
        return {
            split.user: int(expense.amount * (float(split.shares) / 100)) for split in splits
        }
    elif expense.type == Expense.Type.SHARES:
        total_shares = sum(split.shares for split in splits)
        return {
            split.user: int(expense.amount * float(split.shares) / total_shares)
            for split in splits
        }
    elif expense.type == Expense.Type.ADJUSTMENT:
        base_debt = int((expense.amount - sum(split.shares for split in splits)) / len(
            splits
        ))
        return {split.user: base_debt + split.shares for split in splits}
    else:
        raise NotImplementedError(expense.type)


def simplify_debts(debts: dict[tuple[str, str], int]) -> dict[tuple[str, str], int]:
    owers, lenders = map(set, zip(*debts))
    all_users = owers | lenders

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
                    print("mutual lending;", a, "and", b, "owed each other the same amount")
                    continue
                elif diff > 0:
                    new_debts[a, b] = diff
                    lenders_by_user[a].add(b)
                    print("mutual lending;", a, "owed", b, a_owes_b, "and", b, "owed", a, b_owes_a, "simplified to", a, "->", b, diff)
                else:
                    new_debts[b, a] = -diff
                    lenders_by_user[b].add(a)
                    print("mutual lending;", a, "owed", b, a_owes_b, "and", b, "owed", a, b_owes_a, "simplified to", b, "->", a, -diff)

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
                c, = lenders_to_b
                print(a, "owes", b, "and", b, "only owes to", c)
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
