from django.urls import path

from .views import CreateExpense, UpdateExpense, group_home, expense_detail, GroupSettings

app_name = "groups"

urlpatterns = [
    path("<int:group_id>/", group_home, name="group"),
    path("<int:group_id>/settings/", GroupSettings.as_view(), name="group_settings"),
    path("expenses/<int:expense_id>/", expense_detail, name="expense"),
    path("expenses/<int:expense_id>/change/", UpdateExpense.as_view(), name="expense_change"),
    path("<int:group_id>/expenses/", CreateExpense.as_view(), name="expense_create"),
]
