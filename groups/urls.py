from django.urls import path

from .views import CreateExpense, DeleteExpense, UpdateExpense, group_home, expense_detail, GroupSettings, groups_index

app_name = "groups"

urlpatterns = [
    path("", groups_index, name="index"),
    path("<int:group_id>/", group_home, name="group"),
    path("<int:group_id>/settings/", GroupSettings.as_view(), name="group_settings"),
    path("<int:group_id>/settle_up/", CreateExpense.as_view(is_settle_up=True), name="settle_up"),
    path("expenses/<int:expense_id>/", expense_detail, name="expense"),
    path("expenses/<int:expense_id>/change/", UpdateExpense.as_view(), name="expense_change"),
    path("expenses/<int:expense_id>/delete/", DeleteExpense.as_view(), name="expense_delete"),
    path("<int:group_id>/expenses/", CreateExpense.as_view(), name="expense_create"),
]
