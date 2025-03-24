from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from marketplace.models import Product
from .models import Cart, CartItem, SavedItem
from .forms import CartItemForm

def initialize_cart(user):
    """
    Utility function: If the user doesn't have a cart, create it.
    Returns the user's cart.
    """
    if not hasattr(user, 'cart'):
        cart = Cart.objects.create(user=user)
    else:
        cart = user.cart
    return cart

@login_required
def cart_list(request):
    """Show all items in the current user's cart."""
    cart = initialize_cart(request.user)
    cart_items = cart.cart_items.select_related('product')
    
    # Attach computed subtotal for each item
    for item in cart_items:
        if item.product.price is not None:
            item.subtotal = item.product.price * item.quantity
        else:
            item.subtotal = 0

    if request.method == 'POST':
        # User is updating an item's quantity
        item_id = request.POST.get('item_id')
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
        form = CartItemForm(request.POST, instance=cart_item)
        if form.is_valid():
            form.save()
            messages.success(request, "Cart updated.")
        return redirect('cart:cart_list')
    else:
        # Generate a form for each item
        item_forms = []
        for item in cart_items:
            form = CartItemForm(instance=item)
            item_forms.append((item, form))
        
        context = {
            'cart': cart,
            'item_forms': item_forms,
        }
        return render(request, 'cart/cart_list.html', context)

@login_required
def add_to_cart(request, product_id):
    """Add the given product to the user's cart (or increment quantity)."""
    cart = initialize_cart(request.user)
    product = get_object_or_404(Product, id=product_id)
    
    # Check if cart item already exists
    cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
    if not created:
        # If item already in cart, increment quantity
        cart_item.quantity += 1
        cart_item.save()
    
    messages.success(request, f"Added {product.title} to cart.")
    return redirect('cart:cart_list')

@login_required
def remove_from_cart(request, item_id):
    """Remove a CartItem from the user's cart entirely."""
    cart = initialize_cart(request.user)
    cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
    cart_item.delete()
    messages.success(request, "Item removed from cart.")
    return redirect('cart:cart_list')

@login_required
def saved_list(request):
    """Display all 'saved' (wishlist) items for the current user."""
    saved_items = SavedItem.objects.filter(user=request.user).select_related('product')
    return render(request, 'cart/saved_list.html', {'saved_items': saved_items})

@login_required
def add_to_saved(request, product_id):
    """Add product to the user's saved list."""
    product = get_object_or_404(Product, id=product_id)
    SavedItem.objects.get_or_create(user=request.user, product=product)
    messages.success(request, f"Saved {product.title}.")
    return redirect('cart:saved_list')

@login_required
def remove_from_saved(request, saved_item_id):
    """Remove a product from the user's saved list."""
    saved_item = get_object_or_404(SavedItem, id=saved_item_id, user=request.user)
    saved_item.delete()
    messages.success(request, "Removed from saved items.")
    return redirect('cart:saved_list')

@login_required
def checkout_view(request):
    """
    Display a summary of all items in the cart
    with a 'Pay Now' button for future payment integration.
    """
    cart = initialize_cart(request.user)
    cart_items = cart.cart_items.select_related('product')
    
    # Attach computed subtotal for each item
    for item in cart_items:
        if item.product.price is not None:
            item.subtotal = item.product.price * item.quantity
        else:
            item.subtotal = 0

    if request.method == 'POST':
        # Placeholder for future payment logic (e.g., integration with Xendit)
        messages.success(request, "Pretend we're redirecting to a payment gateway now...")
        return redirect('cart:cart_list')

    context = {
        'cart': cart,
        'cart_items': cart_items,
    }
    return render(request, 'cart/checkout.html', context)
