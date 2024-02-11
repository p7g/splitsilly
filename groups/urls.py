from django.urls import path

from .views import (
    CreateExpense,
    CreateGroup,
    DeleteExpense,
    GroupInviteView,
    GroupSettings,
    UpdateExpense,
    consume_invite_view,
    expense_detail,
    group_home,
    groups_index,
    invite_detail_view,
)

app_name = "groups"

urlpatterns = [
    path("", groups_index, name="index"),
    path("create/", CreateGroup.as_view(), name="create"),
    path("<int:group_id>/", group_home, name="group"),
    path("<int:group_id>/settings/", GroupSettings.as_view(), name="group_settings"),
    path("<int:group_id>/invite/", GroupInviteView.as_view(), name="invite"),
    path(
        "<int:group_id>/settle_up/",
        CreateExpense.as_view(is_settle_up=True),
        name="settle_up",
    ),
    path("expenses/<int:expense_id>/", expense_detail, name="expense"),
    path(
        "expenses/<int:expense_id>/change/",
        UpdateExpense.as_view(),
        name="expense_change",
    ),
    path(
        "expenses/<int:expense_id>/delete/",
        DeleteExpense.as_view(),
        name="expense_delete",
    ),
    path("<int:group_id>/expenses/", CreateExpense.as_view(), name="expense_create"),
    path("invite/<uuid:invite_id>/", invite_detail_view, name="invite_detail"),
    path(
        "invite/<uuid:invite_id>/consume/", consume_invite_view, name="consume_invite"
    ),
]
