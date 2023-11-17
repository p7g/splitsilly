from django.shortcuts import render, get_object_or_404

from .models import ExpenseGroup


def group_home(request, group_id: int):
    group = get_object_or_404(ExpenseGroup, pk=group_id)

    return render(request, "groups/home.html", {"group": group})
