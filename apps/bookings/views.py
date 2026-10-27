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


def get_shipping_addresses(request):
    """Retrieves list of user shipping addresses from session (max 3)."""
    addresses = request.session.get('shipping_addresses', None)
    if addresses is None:
        if request.user.is_authenticated:
            # Prepopulate with user default info if available
            default_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email.split('@')[0]
            addresses = [{
                'recipient_name': default_name,
                'phone_number': request.user.phone_number or "081-234-5678",
                'address_line': "123 หมู่ 4 ต.เมืองใต้",
                'district': "เมืองศรีสะเกษ",
                'province': "ศรีสะเกษ",
                'postal_code': "33000",
                'label': "ที่อยู่หลัก (Default)",
            }]
        else:
            addresses = []
        request.session['shipping_addresses'] = addresses
        request.session['selected_address_idx'] = 0
        request.session.modified = True
    return addresses


def get_selected_address(request):
    addresses = get_shipping_addresses(request)
    if not addresses:
        return None
    idx = request.session.get('selected_address_idx', 0)
    if 0 <= idx < len(addresses):
        return addresses[idx]
    return addresses[0]


@require_http_methods(["GET"])
def cart_view(request):
    """
    Step 1: Displays cart items, +/- quantity controls, and shipping address manager (max 3).
    """
    cart = get_cart(request)
    total_amount = sum(Decimal(str(item.get('price', 0))) * int(item.get('quantity', 1)) for item in cart)
    shipping_addresses = get_shipping_addresses(request)
    selected_idx = request.session.get('selected_address_idx', 0)

    return render(request, 'bookings/cart.html', {
        'cart': cart,
        'total_amount': total_amount,
        'item_count': len(cart),
        'shipping_addresses': shipping_addresses,
        'selected_idx': selected_idx,
        'selected_address': get_selected_address(request),
        'can_add_address': len(shipping_addresses) < 3,
    })


@require_http_methods(["POST"])
def cart_update_quantity_view(request, index):
    """Increases or decreases item quantity in the cart."""
    cart = get_cart(request)
    if 0 <= index < len(cart):
        action = request.POST.get('action')
        qty = request.POST.get('quantity')
        if action == 'increase':
            cart[index]['quantity'] = int(cart[index].get('quantity', 1)) + 1
        elif action == 'decrease':
            new_qty = int(cart[index].get('quantity', 1)) - 1
            if new_qty > 0:
                cart[index]['quantity'] = new_qty
            else:
                cart.pop(index)
        elif qty and qty.isdigit():
            val = int(qty)
            if val > 0:
                cart[index]['quantity'] = val
            else:
                cart.pop(index)
        save_cart(request, cart)
    return redirect('bookings:cart')


@require_http_methods(["POST"])
def shipping_address_add_view(request):
    """Adds a new shipping address (strictly max 3)."""
    addresses = list(get_shipping_addresses(request))
    if len(addresses) >= 3:
        messages.error(request, "สามารถบันทึกที่อยู่จัดส่งได้สูงสุด 3 รายการเท่านั้น")
        return redirect('bookings:cart')

    recipient_name = request.POST.get('recipient_name', '').strip()
    phone_number = request.POST.get('phone_number', '').strip()
    address_line = request.POST.get('address_line', '').strip()
    district = request.POST.get('district', 'เมืองศรีสะเกษ').strip()
    province = request.POST.get('province', 'ศรีสะเกษ').strip()
    postal_code = request.POST.get('postal_code', '33000').strip()
    label = request.POST.get('label', f'ที่อยู่จัดส่ง {len(addresses)+1}').strip()

    if not recipient_name or not address_line or not phone_number:
        messages.error(request, "กรุณากรอกข้อมูลชื่อผู้รับ เบอร์โทรศัพท์ และที่อยู่ให้ครบถ้วน")
        return redirect('bookings:cart')

    addresses.append({
        'recipient_name': recipient_name,
        'phone_number': phone_number,
        'address_line': address_line,
        'district': district,
        'province': province,
        'postal_code': postal_code,
        'label': label,
    })
    request.session['shipping_addresses'] = addresses
    request.session['selected_address_idx'] = len(addresses) - 1
    request.session.modified = True
    messages.success(request, f"เพิ่มที่อยู่จัดส่ง '{label}' สำเร็จ")
    return redirect('bookings:cart')


@require_http_methods(["POST"])
def shipping_address_delete_view(request, index):
    """Deletes a shipping address by index."""
    addresses = list(get_shipping_addresses(request))
    if 0 <= index < len(addresses):
        removed = addresses.pop(index)
        request.session['shipping_addresses'] = addresses
        request.session['selected_address_idx'] = max(0, min(request.session.get('selected_address_idx', 0), len(addresses) - 1))
        request.session.modified = True
        messages.success(request, f"ลบที่อยู่จัดส่ง '{removed.get('label', 'ที่อยู่')}' เรียบร้อยแล้ว")
    return redirect('bookings:cart')


@require_http_methods(["POST"])
def shipping_address_select_view(request, index):
    """Sets active selected shipping address."""
    addresses = get_shipping_addresses(request)
    if 0 <= index < len(addresses):
        request.session['selected_address_idx'] = index
        request.session.modified = True
        messages.success(request, f"เลือกที่อยู่จัดส่ง: {addresses[index].get('recipient_name')}")
    return redirect('bookings:cart')


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
@require_http_methods(["GET"])
def review_view(request):
    """
    Step 2: Order Review & Summary (หน้าทวนรายละเอียดคำสั่งซื้อก่อนสั่ง).
    """
    cart = get_cart(request)
    if not cart:
        messages.warning(request, "ตะกร้าสินค้าว่างเปล่า กรุณาเลือกบริการก่อนดำเนินการสั่งซื้อ")
        return redirect('accommodations:list')

    total_amount = sum(Decimal(str(item.get('price', 0))) * int(item.get('quantity', 1)) for item in cart)
    shipping_address = get_selected_address(request)

    return render(request, 'bookings/review.html', {
        'cart': cart,
        'total_amount': total_amount,
        'item_count': len(cart),
        'shipping_address': shipping_address,
    })


@login_required
@require_http_methods(["GET", "POST"])
def checkout_view(request):
    """
    Step 3: Locks inventories, attaches shipping address, creates booking, and redirects to payment instructions.
    """
    cart = get_cart(request)
    if not cart:
        messages.warning(request, "ตะกร้าสินค้าว่างเปล่า กรุณาเลือกบริการก่อนดำเนินการสั่งซื้อ")
        return redirect('accommodations:list')

    total_amount = sum(Decimal(str(item.get('price', 0))) * int(item.get('quantity', 1)) for item in cart)
    shipping_address = get_selected_address(request)

    if request.method == "POST":
        customer_notes = request.POST.get('customer_notes', '').strip()
        if shipping_address:
            addr_str = f"ที่อยู่จัดส่ง: {shipping_address.get('recipient_name')} ({shipping_address.get('phone_number')}) {shipping_address.get('address_line')} อ.{shipping_address.get('district')} จ.{shipping_address.get('province')} {shipping_address.get('postal_code')}"
            customer_notes = f"{customer_notes}\n{addr_str}".strip() if customer_notes else addr_str

        try:
            booking = process_checkout(
                user=request.user,
                cart_items=cart,
                customer_notes=customer_notes,
                request=request,
            )
            # Empty cart after successful order placement
            save_cart(request, [])
            request.session['last_order_shipping_address'] = shipping_address
            request.session.modified = True
            messages.success(request, f"สร้างคำสั่งซื้อสำเร็จ รหัส: {booking.booking_code}")
            return redirect('payments:payment_instruction', booking_id=booking.id)
        except StockUnavailableError as e:
            messages.error(request, f"ไม่สามารถดำเนินการได้: {str(e)}")
            return redirect('bookings:cart')
        except Exception as e:
            messages.error(request, f"เกิดข้อผิดพลาดในระบบ: {str(e)}")
            return redirect('bookings:cart')

    return redirect('bookings:review')


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
