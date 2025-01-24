from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from huey.contrib.djhuey import db_task

from groups.api import calculate_expense_debts
from groups.models import Expense, ExpenseGroupInvite
from groups.templatetags.money import to_dollars
from identity.models import User


@db_task()
def send_group_invite_email(invite_id: int) -> None:
    invite = ExpenseGroupInvite.objects.select_related("sender", "group").get(
        id=invite_id
    )
    assert invite.consumed_by_id is None

    context = {
        "invite": invite,
    }
    plaintext_message = render_to_string("email/group_invite.txt", context)
    html_message = render_to_string("email/group_invite.html", context)

    send_mail(
        subject=f"{invite.sender.username} invited you to {invite.group.name} on Splitsilly",
        message=plaintext_message,
        from_email=settings.EMAIL_FROM_ADDRESS,
        recipient_list=[invite.recipient],
        html_message=html_message,
    )


@db_task()
def send_group_invite_consumed_email(invite_id: int) -> None:
    invite = ExpenseGroupInvite.objects.select_related("sender", "group", "consumed_by").get(id=invite_id)
    assert invite.consumed_by is not None

    context = {
        "invite": invite,
    }

    plaintext_message = render_to_string("email/group_invite_consumed.txt", context)
    html_message = render_to_string("email/group_invite_consumed.html", context)

    send_mail(
        subject=f"{invite.consumed_by.username} accepted your invite to {invite.group.name} on Splitsilly",
        message=plaintext_message,
        from_email=settings.EMAIL_FROM_ADDRESS,
        recipient_list=[invite.sender.email],
        html_message=html_message,
    )


@db_task()
def send_expense_added_emails(expense_id: int, actor_user_id: int) -> None:
    actor = User.objects.get(id=actor_user_id)
    expense = Expense.objects.get(id=expense_id)
    debts = calculate_expense_debts(expense)

    for user, amount_owed in debts.items():
        if user == actor:
            continue
        if expense.is_settle_up:
            user.send_email(
                f"{expense.payer.username} settled up with you",
                f"They paid you {to_dollars(-amount_owed)}.",
            )
        elif user == expense.payer:
            user.send_email(
                f"{actor.username} added a new expense in {expense.group.name}",
                f"You paid {to_dollars(expense.amount, expense.currency_symbol)} for {expense.name} on {expense.date.isoformat()}. "
                f"You are owed {to_dollars(expense.amount - amount_owed)}.",
            )
        else:
            user.send_email(
                f"{actor.username} added a new expense in {expense.group.name}",
                f"You owe {to_dollars(amount_owed)} to {expense.payer.username} for {expense.name} on {expense.date.isoformat()}.",
            )


@db_task()
def send_expense_updated_emails(expense_id: int, actor_user_id: int) -> None:
    actor = User.objects.get(id=actor_user_id)
    expense = Expense.objects.get(id=expense_id)
    debts = calculate_expense_debts(expense)

    for user, amount_owed in debts.items():
        if user == actor:
            continue
        if expense.is_settle_up:
            user.send_email(
                f"{expense.payer.username} updated their settle up with you",
                f"They now paid you {to_dollars(amount_owed)}.",
            )
        elif user == expense.payer:
            user.send_email(
                f"{actor.username} updated an expense in {expense.group.name}",
                f"You paid {to_dollars(expense.amount, expense.currency_symbol)} for {expense.name} on {expense.date.isoformat()}. "
                f"You are now owed {to_dollars(expense.amount - amount_owed)}.",
            )
        else:
            user.send_email(
                f"{actor.username} updated an expense in {expense.group.name}",
                f"You now owe {to_dollars(amount_owed)} to {expense.payer.username} for {expense.name} on {expense.date.isoformat()}",
            )
