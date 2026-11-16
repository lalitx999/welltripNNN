from apps.core.services.visits import count_visit


class VisitCounterMiddleware:
    """Counts visits to public pages for the admin dashboard (see apps.core.services.visits)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        count_visit(request, response)
        return response
