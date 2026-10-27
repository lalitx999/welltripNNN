from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.accounts.permissions import can_view_object
from apps.bookings.models import Booking, BookingItem, BookingStatus, BookingItemType
from apps.bookings.services.checkout import process_checkout, StockUnavailableError


def get_cart(request):
    """Retrieves session-based shopping cart."""
    return request.session.get('cart', [])


def save_cart(request, cart):
    """Saves cart back into user session."""
    request.session['cart'] = cart
    request.session.modified = True


@require_http_methods(["GET"])
def cart_view(request):
    """Displays cart items and checkout preview."""
    cart = get_cart(request)
    total_amount = sum(Decimal(str(item.get('price', 0))) * int(item.get('quantity', 1)) for item in cart)

    return render(request, 'bookings/cart.html', {
        'cart': cart,
        'total_amount': total_amount,
        'item_count': len(cart),
    })


@require_http_methods(["POST"])
def cart_add_view(request):
    """Adds a multi-vendor item to session cart via standard form or HTMX."""
    cart = get_cart(request)

    item_type = request.POST.get('item_type')
    entity_id = request.POST.get('entity_id')
    title = request.POST.get('title', 'สินค้า/บริการ')
    price = request.POST.get('price', '0.00')
    quantity = int(request.POST.get('quantity', 1))
    item_date = request.POST.get('date', '') or request.POST.get('check_in', '')

    # Check if duplicate item already in cart (for non-dated items)
    found = False
    for item in cart:
        if item.get('entity_id') == entity_id and item.get('item_type') == item_type and item.get('date') == item_date:
            item['quantity'] = int(item.get('quantity', 1)) + quantity
            found = True
            break

    if not found:
        cart.append({
            'item_type': item_type,
            'entity_id': entity_id,
            'title': title,
            'price': str(price),
            'quantity': quantity,
            'date': item_date,
        })

    save_cart(request, cart)
    messages.success(request, f"เพิ่ม '{title}' ลงตะกร้าเรียบร้อยแล้ว")

    if request.headers.get('HX-Request'):
        total_amount = sum(Decimal(str(item.get('price', 0))) * int(item.get('quantity', 1)) for item in cart)
        return render(request, 'bookings/partials/cart_drawer.html', {
            'cart': cart,
            'total_amount': total_amount,
        })

    return redirect('bookings:cart')


@require_http_methods(["POST"])
def cart_remove_view(request, index):
    """Removes an item by index from the session cart."""
    cart = get_cart(request)
    if 0 <= index < len(cart):
        removed = cart.pop(index)
        save_cart(request, cart)
        messages.success(request, f"นำ '{removed.get('title')}' ออกจากตะกร้าแล้ว")

    return redirect('bookings:cart')


@login_required
@require_http_methods(["GET", "POST"])
def checkout_view(request):
    """
    Checkout View:
    Locks inventories and creates booking. Redirects to payment instructions.
    """
    cart = get_cart(request)
    if not cart:
        messages.warning(request, "ตะกร้าสินค้าว่างเปล่า กรุณาเลือกบริการก่อนดำเนินการสั่งซื้อ")
        return redirect('accommodations:list')

    total_amount = sum(Decimal(str(item.get('price', 0))) * int(item.get('quantity', 1)) for item in cart)

    if request.method == "POST":
        customer_notes = request.POST.get('customer_notes', '').strip()
        try:
            booking = process_checkout(
                user=request.user,
                cart_items=cart,
                customer_notes=customer_notes,
                request=request,
            )
            # Empty cart after successful order placement
            save_cart(request, [])
            messages.success(request, f"สร้างคำสั่งซื้อสำเร็จ รหัส: {booking.booking_code}")
            return redirect('payments:payment_instruction', booking_id=booking.id)
        except StockUnavailableError as e:
            messages.error(request, f"ไม่สามารถดำเนินการได้: {str(e)}")
            return redirect('bookings:cart')
        except Exception as e:
            messages.error(request, f"เกิดข้อผิดพลาดในระบบ: {str(e)}")
            return redirect('bookings:cart')

    return render(request, 'bookings/checkout.html', {
        'cart': cart,
        'total_amount': total_amount,
    })


@login_required
def my_bookings_view(request):
    """
    Lists current tourist's bookings with 4 status tabs and countdowns:
    1. all: ทั้งหมด
    2. active: กำลังดำเนินการ (AWAITING_PAYMENT, CONFIRMED)
    3. completed: สำเร็จแล้ว (COMPLETED)
    4. cancelled: ยกเลิก / คืนเงิน (CANCELLED, PAYMENT_EXPIRED)
    """
    user = request.user
    active_tab = request.GET.get('tab', 'all').strip().lower()

    base_qs = Booking.objects.filter(customer=user).prefetch_related('items').order_by('-created_at')

    # Tab counts
    all_count = base_qs.count()
    active_count = base_qs.filter(status__in=[BookingStatus.AWAITING_PAYMENT, BookingStatus.CONFIRMED]).count()
    completed_count = base_qs.filter(status=BookingStatus.COMPLETED).count()
    cancelled_count = base_qs.filter(status__in=[BookingStatus.CANCELLED, BookingStatus.PAYMENT_EXPIRED]).count()

    # Filtered queryset based on tab
    if active_tab == 'active':
        bookings = base_qs.filter(status__in=[BookingStatus.AWAITING_PAYMENT, BookingStatus.CONFIRMED])
    elif active_tab == 'completed':
        bookings = base_qs.filter(status=BookingStatus.COMPLETED)
    elif active_tab == 'cancelled':
        bookings = base_qs.filter(status__in=[BookingStatus.CANCELLED, BookingStatus.PAYMENT_EXPIRED])
    else:
        active_tab = 'all'
        bookings = base_qs

    return render(request, 'bookings/my_bookings.html', {
        'bookings': bookings,
        'active_tab': active_tab,
        'all_count': all_count,
        'active_count': active_count,
        'completed_count': completed_count,
        'cancelled_count': cancelled_count,
    })


@login_required
def booking_detail_view(request, booking_id):
    """
    Details of a specific booking.
    Strictly verifies ownership: customer=request.user or admin.
    """
    booking = get_object_or_404(Booking, id=booking_id)
    if not can_view_object(request.user, booking):
        messages.error(request, "คุณไม่มีสิทธิ์เข้าถึงข้อมูลการจองนี้")
        return redirect('bookings:my_bookings')

    items = booking.items.all().select_related('vendor')
    return render(request, 'bookings/booking_detail.html', {
        'booking': booking,
        'items': items,
        'remaining_seconds': booking.remaining_seconds,
    })
