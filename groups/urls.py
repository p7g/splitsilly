from django.urls import path

from .views import group_home

urlpatterns = [
    path("<int:group_id>/", group_home),
]
