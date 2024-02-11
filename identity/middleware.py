from django.utils import timezone


class ActivateUserTimeZoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_anonymous:
            timezone.activate(request.user.timezone)
        return self.get_response(request)
