# ukay/cart/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
# Import transaction directly from django.db
from django.db import transaction, models # Import models for F expression
from django.urls import reverse
from decimal import Decimal
import logging

from marketplace.models import Product
from .models import Cart, CartItem, SavedItem
from .forms import CartItemForm
from orders.models import Order, OrderItem
from wallet.models import Wallet
# Assuming wallet functions are in wallet/models.py or moved to wallet/services.py
from wallet.models import deduct_funds, add_funds
# Import the Xendit service function
from payments.services import create_xendit_payment_request

logger = logging.getLogger(__name__)

# --- initialize_cart, cart_list, add_to_cart, remove_from_cart ---
# --- saved_list, add_to_saved, remove_from_saved ---
# --- distribute_payment ---
# (Keep these functions as they were in your previous code)
def initialize_cart(user):
    cart, created = Cart.objects.get_or_create(user=user)
    if created: logger.info(f"Created cart for user {user.email}")
    return cart

@login_required
def cart_list(request):
    cart = initialize_cart(request.user)
    cart_items = cart.cart_items.select_related('product').prefetch_related('product__images').all()
    total_price = sum((item.product.price or 0) * item.quantity for item in cart_items)

    for item in cart_items:
        item.subtotal = (item.product.price or 0) * item.quantity
        primary_image = item.product.images.filter(is_primary=True).first()
        item.primary_image_url = primary_image.image.url if primary_image else None

    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        try:
            cart_item = CartItem.objects.get(id=item_id, cart=cart)
            form = CartItemForm(request.POST, instance=cart_item)
            if form.is_valid():
                product = cart_item.product
                requested_quantity = form.cleaned_data['quantity']
                # Re-fetch product to check current stock before saving form
                # No need to lock here, just get latest data
                current_product_stock = Product.objects.get(id=product.id).quantity
                if requested_quantity > current_product_stock:
                     messages.error(request, f"Only {current_product_stock} available for {product.title}.")
                else:
                     form.save()
                     messages.success(request, f"Quantity for {product.title} updated.")
            else:
                error_msg = "Invalid quantity. " + " ".join([f"{field}: {', '.join(errors)}" for field, errors in form.errors.items()])
                messages.error(request, error_msg)
        except CartItem.DoesNotExist:
            messages.error(request, "Item not found in your cart.")
        except Product.DoesNotExist:
             messages.error(request, "Product associated with cart item not found.")
        except Exception as e:
            logger.error(f"Error updating cart item {item_id}: {e}", exc_info=True)
            messages.error(request, "Could not update cart item.")
        return redirect('cart:cart_list')
    else:
        item_forms = [(item, CartItemForm(instance=item)) for item in cart_items]
        context = {
            'cart': cart,
            'item_forms': item_forms,
            'total_price': total_price,
        }
        return render(request, 'cart/cart_list.html', context)

@login_required
def add_to_cart(request, product_id):
    cart = initialize_cart(request.user)
    product = get_object_or_404(Product, id=product_id, is_public=True, is_sold=False)

    if product.seller == request.user:
        messages.warning(request, "You cannot add your own product to the cart.")
        return redirect(request.META.get('HTTP_REFERER', 'marketplace:home'))

    if product.quantity <= 0:
        messages.error(request, f"Sorry, '{product.title}' is out of stock.")
        return redirect(request.META.get('HTTP_REFERER', 'marketplace:home'))

    cart_item, created = CartItem.objects.get_or_create(
        cart=cart, product=product, defaults={'quantity': 1}
    )

    if not created:
        # Use atomic transaction for incrementing quantity to prevent race conditions
        try:
            with transaction.atomic():
                # Lock the cart item and product row
                cart_item_locked = CartItem.objects.select_for_update().get(id=cart_item.id)
                product_locked = Product.objects.select_for_update().get(id=product.id)
                if cart_item_locked.quantity < product_locked.quantity:
                    cart_item_locked.quantity = models.F('quantity') + 1
                    cart_item_locked.save()
                    messages.success(request, f"Increased quantity for {product.title} in cart.")
                else:
                    messages.warning(request, f"Cannot add more of '{product.title}'. Max available stock ({product_locked.quantity}) reached.")
        except Exception as e:
             logger.error(f"Error incrementing cart item {cart_item.id}: {e}", exc_info=True)
             messages.error(request, "Could not update item quantity. Please try again.")

    else: # Item was newly created
        messages.success(request, f"Added {product.title} to cart.")

    return redirect(request.META.get('HTTP_REFERER', 'marketplace:home'))


@login_required
def remove_from_cart(request, item_id):
    cart = initialize_cart(request.user)
    try:
        cart_item = CartItem.objects.get(id=item_id, cart=cart)
        product_title = cart_item.product.title
        cart_item.delete()
        messages.success(request, f"Removed {product_title} from cart.")
    except CartItem.DoesNotExist:
        messages.error(request, "Item not found in your cart.")
    except Exception as e:
        logger.error(f"Error removing cart item {item_id}: {e}", exc_info=True)
        messages.error(request, "Could not remove item from cart.")
    return redirect('cart:cart_list')

# --- Saved Items Views (Keep as is) ---
@login_required
def saved_list(request):
    saved_items = SavedItem.objects.filter(user=request.user).select_related('product').prefetch_related('product__images').all()
    for item in saved_items:
        primary_image = item.product.images.filter(is_primary=True).first()
        item.primary_image_url = primary_image.image.url if primary_image else None
    return render(request, 'cart/saved_list.html', {'saved_items': saved_items})

@login_required
def add_to_saved(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_public=True)
    if product.seller == request.user:
        messages.warning(request, "You cannot save your own product.")
        return redirect(request.META.get('HTTP_REFERER', 'marketplace:home'))
    _, created = SavedItem.objects.get_or_create(user=request.user, product=product)
    if created: messages.success(request, f"Saved {product.title}.")
    else: messages.info(request, f"{product.title} is already saved.")
    return redirect(request.META.get('HTTP_REFERER', reverse('cart:saved_list')))

@login_required
def remove_from_saved(request, saved_item_id):
    try:
        saved_item = SavedItem.objects.get(id=saved_item_id, user=request.user)
        product_title = saved_item.product.title
        saved_item.delete()
        messages.success(request, f"Removed {product_title} from saved items.")
    except SavedItem.DoesNotExist: messages.error(request, "Item not found in your saved list.")
    except Exception as e: logger.error(f"Error removing saved item {saved_item_id}: {e}", exc_info=True); messages.error(request, "Could not remove saved item.")
    return redirect('cart:saved_list')

# --- Fund Distribution (Keep as is, or move to orders/services.py) ---
def distribute_payment(order: Order):
    if order.status != 'PAID':
        logger.warning(f"Attempted distribute payment for non-PAID Order {order.id} (Status: {order.status}).")
        return False # Explicitly return False, don't raise error here

    order_items = order.items.select_related('product', 'seller').all()
    logger.info(f"Distributing payment for Order {order.id} ({len(order_items)} items).")
    platform_fee_percentage = Decimal('0.00') # Example: 0% fee

    # This function is called within an existing transaction (either wallet checkout or webhook)
    # No need for an additional transaction.atomic() here unless making external calls
    # that need independent rollback capability.
    for item in order_items:
        if item.seller:
            item_subtotal = item.subtotal # Use property
            platform_fee = item_subtotal * platform_fee_percentage
            amount_to_seller = item_subtotal - platform_fee

            if amount_to_seller > 0:
                try:
                    add_funds(
                        user=item.seller, amount=amount_to_seller, transaction_type='SALE',
                        description=f"Sale: {item.quantity}x '{item.product.title if item.product else 'N/A'}' (Order #{str(order.id)[:8]})",
                        related_order_id=str(order.id)
                    )
                    logger.info(f"Credited {amount_to_seller} to seller {item.seller.email} for OrderItem {item.id}")
                except Exception as e:
                    # If add_funds fails (e.g., ValueError, DB error within its transaction), log and raise to rollback outer transaction
                    logger.error(f"Failed to credit seller {item.seller.email} for OrderItem {item.id} (Order {order.id}): {e}", exc_info=True)
                    # Raise an error to ensure the calling transaction (webhook/wallet checkout) rolls back
                    raise ValueError(f"Distribution failed for seller {item.seller.email} on Order {order.id}.") from e
            else:
                logger.warning(f"Amount for seller {item.seller.email} is zero/less for OrderItem {item.id}.")
        else:
            logger.warning(f"No seller linked to OrderItem {item.id} in Order {order.id}.")

    logger.info(f"Successfully distributed funds for Order {order.id}")
    return True


# --- Checkout View (Updated) ---
@login_required
def checkout_view(request):
    cart = initialize_cart(request.user)
    # Pre-fetch products and sellers for efficiency
    cart_items = cart.cart_items.select_related('product', 'product__seller').all()

    if not cart_items:
        messages.warning(request, "Your cart is empty.")
        return redirect('marketplace:home')

    total_price = sum((item.product.price or 0) * item.quantity for item in cart_items)
    buyer_wallet, _ = Wallet.objects.get_or_create(user=request.user)

    # --- POST Request Handling ---
    if request.method == 'POST':
        payment_method_choice = request.POST.get('payment_method')
        selected_xendit_channel = request.POST.get('xendit_channel') # e.g., EWALLET_GCASH

        # --- Basic Validation ---
        if not payment_method_choice:
            messages.error(request, "Please select a payment method.")
            return redirect('cart:checkout')
        if payment_method_choice == 'XENDIT' and not selected_xendit_channel:
            messages.error(request, "Please select a specific external payment channel.")
            return redirect('cart:checkout')
        # --- Wallet Balance Check (Client-side check is good, server-side is essential) ---
        if payment_method_choice == 'WALLET' and buyer_wallet.balance < total_price:
            messages.error(request, "Insufficient wallet balance.")
            return redirect('cart:checkout')

        # --- !! START ATOMIC TRANSACTION FOR CHECKOUT !! ---
        # Wrap stock check, order creation, and payment processing/initiation
        try:
            with transaction.atomic():
                logger.info(f"Starting checkout transaction for Cart of user {request.user.email}")

                # --- 1. Stock Availability Check (Inside Transaction) ---
                # Lock product rows during check
                products_locked = {} # Keep track of locked products
                for item in cart_items:
                    try:
                        # Lock the product row for update
                        product = Product.objects.select_for_update().get(id=item.product.id)
                        products_locked[product.id] = product # Store locked instance

                        logger.debug(f"Checking stock for Product {product.id} (Need: {item.quantity}, Have: {product.quantity})")
                        if item.quantity > product.quantity:
                            raise ValueError(f"Not enough stock for '{product.title}'. Only {product.quantity} available.")
                        if product.is_sold:
                            raise ValueError(f"Sorry, '{product.title}' has already been sold.")

                    except Product.DoesNotExist:
                         raise ValueError(f"Product '{item.product.title}' is no longer available.")
                logger.info("Stock availability check passed for all items.")

                # --- 2. Create Order and OrderItems (Inside Transaction) ---
                order = Order.objects.create(
                    buyer=request.user,
                    total_amount=total_price,
                    status='PENDING', # Start as PENDING
                    payment_method=payment_method_choice,
                    currency='PHP', # Or get dynamically
                    country='PH',   # Or get dynamically
                    # Save selected Xendit channel if applicable (can be updated later by service if needed)
                    payment_channel=selected_xendit_channel if payment_method_choice == 'XENDIT' else None,
                )
                order_items_to_create = []
                for item in cart_items:
                    # Use the product instance we already retrieved and locked
                    product = products_locked[item.product.id]
                    order_items_to_create.append(
                        OrderItem(
                            order=order,
                            product=product,
                            seller=product.seller, # Get seller from locked product
                            quantity=item.quantity,
                            price=product.price # Use price from locked product at time of checkout
                        )
                    )
                OrderItem.objects.bulk_create(order_items_to_create)
                logger.info(f"Created Order {order.id} with status PENDING for user {request.user.email}.")

                # --- 3. Process Payment (Inside Transaction for Wallet, Outside for Xendit) ---
                if payment_method_choice == 'WALLET':
                    logger.info(f"Processing WALLET payment for Order {order.id}")
                    # Wallet logic needs its own nested transaction or careful handling if add/deduct aren't atomic
                    # Assuming deduct_funds handles its own locking/atomicity or relies on this outer one:

                    # 3a. Deduct from buyer wallet
                    deduct_funds(
                        user=request.user, amount=total_price, transaction_type='PURCHASE',
                        description=f"Purchase (Order #{str(order.id)[:8]})", related_order_id=str(order.id)
                    )
                    # 3b. Mark order PAID *immediately* for wallet payments
                    order.status = 'PAID'
                    order.save(update_fields=['status'])
                    logger.info(f"Order {order.id} status updated to PAID (Wallet).")

                    # 3c. Deduct stock (Already locked, now perform update)
                    # NOTE: This repeats logic from webhook, consider refactoring to a common function
                    logger.info(f"--- Final Stock Deduction (Wallet Payment) for Order {order.id} ---")
                    for item in order.items.all(): # Iterate through newly created order items
                         prod = products_locked[item.product.id] # Use already locked product
                         try:
                             updated_rows = Product.objects.filter(id=prod.id).update(quantity=models.F('quantity') - item.quantity)
                             # No need to check gte again as it was checked under lock
                             if updated_rows == 0: # Should not happen if lock worked
                                 raise RuntimeError(f"Stock update failed unexpectedly for locked Product {prod.id}")
                             logger.info(f"Stock deducted for Product {prod.id}.")
                             prod.refresh_from_db() # Get the new quantity
                             if prod.quantity <= 0 and not prod.is_sold:
                                 prod.is_sold = True
                                 prod.save(update_fields=['is_sold'])
                                 logger.info(f"Marked Product {prod.id} as sold.")
                         except Exception as stock_e:
                             logger.error(f"Stock update/sold status error during Wallet checkout for Product {prod.id}: {stock_e}", exc_info=True)
                             raise # Rollback transaction

                    # 3d. Distribute funds
                    distribution_ok = distribute_payment(order) # Order status is now PAID
                    if not distribution_ok:
                        raise ValueError("Fund distribution failed for Wallet payment.")

                    # 3e. Clear cart (safe to do now)
                    cart.cart_items.all().delete()
                    logger.info(f"Cleared cart for user {request.user.email} after successful wallet payment.")

                    # If we reach here, wallet payment and post-processing succeeded
                    messages.success(request, "Payment successful using wallet!")
                    # Redirect *after* transaction commits
                    return redirect(reverse('orders:order_detail', kwargs={'order_id': order.id}))

                elif payment_method_choice == 'XENDIT':
                    # For Xendit, we commit the PENDING order here.
                    # Payment processing happens off-site via redirect/webhook.
                    # Stock is deducted only when the success webhook arrives.
                    logger.info(f"Order {order.id} created. Initiating Xendit payment process...")
                    # Clear cart now, as user will be redirected
                    cart.cart_items.all().delete()
                    logger.info(f"Cleared cart for user {request.user.email} before Xendit redirect/display.")
                    # The transaction commits here, saving the PENDING order

            # --- Transaction finished successfully (either committed Wallet payment or committed PENDING order for Xendit) ---

            # --- Initiate Xendit Payment (AFTER committing the PENDING order) ---
            if payment_method_choice == 'XENDIT':
                # Now call Xendit service outside the main transaction
                # Pass the committed order object
                xendit_response = create_xendit_payment_request(order, request, selected_xendit_channel)
                response_status = xendit_response.get('status')
                response_type = xendit_response.get('type')

                # Handle Xendit Response (Redirect user or show details)
                if response_status in ['PENDING', 'REQUIRES_ACTION']:
                    if response_type == 'REDIRECT' and 'payment_url' in xendit_response:
                        payment_url = xendit_response['payment_url']
                        logger.info(f"Redirecting user {request.user.email} to Xendit URL: {payment_url} for Order {order.id}")
                        return redirect(payment_url)
                    elif response_type == 'VIRTUAL_ACCOUNT':
                        logger.info(f"Displaying VA details for Order {order.id} to user {request.user.email}")
                        context = {'order': order, 'va_details': xendit_response.get('details')}
                        return render(request, 'payments/virtual_account_details.html', context)
                    # ... (add similar blocks for QR_CODE, OTC if needed) ...
                    else:
                        logger.warning(f"Xendit requires action but no redirect/display instructions for Order {order.id}. Type: {response_type}")
                        messages.info(request, f"Your payment is {response_status.lower()}. Please follow instructions from the payment provider.")
                        return redirect(reverse('orders:order_detail', kwargs={'order_id': order.id}))
                elif response_status == 'SUCCEEDED': # Rare immediate success
                     logger.warning(f"Xendit payment SUCCEEDED immediately for Order {order.id}. Webhook should confirm.")
                     messages.success(request, "Payment processing initiated successfully!")
                     return redirect(reverse('orders:order_detail', kwargs={'order_id': order.id}))
                else: # FAILED initiation
                    error_message = xendit_response.get('error', 'Unknown payment initiation error.')
                    logger.error(f"Xendit payment initiation FAILED for Order {order.id}. Service Response: {xendit_response}")
                    # Mark the already committed order as FAILED
                    order.status = 'FAILED'
                    order.failure_reason = f"Initiation Failed: {error_message}"[:255]
                    order.save(update_fields=['status', 'failure_reason'])
                    messages.error(request, f"Payment initiation failed: {error_message}")
                    # Don't redirect back to checkout, maybe order list or cart?
                    return redirect('cart:cart_list') # Or order list if preferred

        # --- Handle Errors During the Main Transaction ---
        except ValueError as e: # Catch specific errors like insufficient stock/funds/distribution failure
             logger.warning(f"Checkout transaction failed for Cart of user {request.user.email}: {e}")
             messages.error(request, f"Checkout failed: {e}")
             return redirect('cart:checkout') # Back to checkout page
        except Exception as e: # Catch unexpected errors during transaction
             logger.error(f"Unexpected error during checkout transaction for user {request.user.email}: {e}", exc_info=True)
             messages.error(request, "An unexpected error occurred during checkout. Please try again.")
             return redirect('cart:checkout')

    # --- GET Request Handling (Show Checkout Page) ---
    else: # GET
        xendit_channels = { # Define available channels
            "EWALLET_GCASH": "GCash", "EWALLET_GRABPAY": "GrabPay", "EWALLET_PAYMAYA": "Maya",
            "VIRTUAL_ACCOUNT_BPI": "BPI Virtual Account", "VIRTUAL_ACCOUNT_BDO": "BDO Virtual Account",
            "CARD_CARD": "Credit/Debit Card",
            # Add other channels as needed
        }
        context = {
            'cart': cart, 'cart_items': cart_items, 'total_price': total_price,
            'buyer_wallet_balance': buyer_wallet.balance,
            'can_afford_with_wallet': buyer_wallet.balance >= total_price,
            'xendit_channels': xendit_channels,
        }
        for item in cart_items: item.subtotal = (item.product.price or 0) * item.quantity
        return render(request, 'cart/checkout.html', context)