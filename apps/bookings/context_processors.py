def cart_context(request):
    """Provides cart item count across all templates for navbar badge."""
    cart = request.session.get('cart', []) if hasattr(request, 'session') else []
    return {
        'cart_item_count': sum(int(item.get('quantity', 1)) for item in cart),
    }
