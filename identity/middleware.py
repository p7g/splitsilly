from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.utils import timezone


class ActivateUserTimeZoneMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not request.user.is_anonymous:
            timezone.activate(request.user.timezone)
        return self.get_response(request)
