# ukay/orders/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Order # Import your Order model

@login_required # Ensure only logged-in users can see their orders
def order_detail_view(request, order_id):
    """
    Display the details of a specific order.
    """
    # Fetch the order, ensuring it belongs to the current user
    order = get_object_or_404(Order, id=order_id, buyer=request.user)

    # You'll likely want to fetch order items too
    # order_items = order.items.all() # Assuming related_name='items'

    context = {
        'order': order,
        # 'order_items': order_items,
    }
    # Create a template for this view at templates/orders/order_detail.html
    return render(request, 'orders/order_detail.html', context)

@login_required # Ensure only logged-in users can see their orders
def order_list_view(request):
    """
    Display a list of orders for the current user.
    """
    # Fetch all orders for the current user
    orders = Order.objects.filter(buyer=request.user).order_by('-created_at')

    context = {
        'orders': orders,
    }
    # Create a template for this view at templates/orders/order_list.html
    return render(request, 'orders/order_list.html', context)