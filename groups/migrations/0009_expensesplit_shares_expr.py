# Generated by Django 4.2.7 on 2024-05-27 20:26

from django.db import migrations, models


def copy_shares_to_shares_expr(apps, schema_editor):
    ExpenseSplit = apps.get_model("groups", "expensesplit")

    ExpenseSplit.objects.all().update(shares_expr=models.F("shares"))


class Migration(migrations.Migration):
    dependencies = [
        ("groups", "0008_expense_currency_symbol"),
    ]

    operations = [
        migrations.AddField(
            model_name="expensesplit",
            name="shares_expr",
            field=models.TextField(default=""),
            preserve_default=False,
        ),
        migrations.RunPython(copy_shares_to_shares_expr, migrations.RunPython.noop),
    ]
