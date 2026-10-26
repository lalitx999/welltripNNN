from django.shortcuts import render, get_object_or_404
from apps.bookings.models import Booking


def payment_instruction_view(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    return render(request, 'payments/checkout.html', {'booking': booking})
