# ukay/cart/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction, models # Import models for F expression
from django.urls import reverse # Import reverse
from decimal import Decimal
import logging

from marketplace.models import Product
from .models import Cart, CartItem, SavedItem
from .forms import CartItemForm
from orders.models import Order, OrderItem
from wallet.models import Wallet
# Assuming wallet functions are in wallet/models.py or moved to wallet/services.py
from wallet.models import deduct_funds, add_funds
# Or from wallet.services import deduct_funds, add_funds
# Import the Xendit service function
from payments.services import create_xendit_payment_request

logger = logging.getLogger(__name__)

# --- initialize_cart, cart_list, add_to_cart, remove_from_cart ---
# --- saved_list, add_to_saved, remove_from_saved ---
# --- distribute_payment ---
def initialize_cart(user):
    """
    Utility function: If the user doesn't have a cart, create it.
    Returns the user's cart.
    """
    cart, created = Cart.objects.get_or_create(user=user)
    if created:
        logger.info(f"Created cart for user {user.email}")
    return cart

@login_required
def cart_list(request):
    """Show all items in the current user's cart."""
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
                if requested_quantity > product.quantity:
                    messages.error(request, f"Only {product.quantity} available for {product.title}.")
                else:
                    form.save()
                    messages.success(request, f"Quantity for {product.title} updated.")
            else:
                error_msg = "Invalid quantity."
                if form.errors:
                    error_msg += " " + " ".join([f"{field}: {', '.join(errors)}" for field, errors in form.errors.items()])
                messages.error(request, error_msg)
        except CartItem.DoesNotExist:
            messages.error(request, "Item not found in your cart.")
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
    """Add the given product to the user's cart (or increment quantity)."""
    cart = initialize_cart(request.user)
    product = get_object_or_404(Product, id=product_id, is_public=True, is_sold=False)

    if product.seller == request.user:
        messages.warning(request, "You cannot add your own product to the cart.")
        return redirect(request.META.get('HTTP_REFERER', 'marketplace:home'))

    if product.quantity <= 0:
         messages.error(request, f"Sorry, '{product.title}' is out of stock.")
         return redirect(request.META.get('HTTP_REFERER', 'marketplace:home'))

    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={'quantity': 1}
    )

    if not created:
        if cart_item.quantity < product.quantity:
            cart_item.quantity += 1
            cart_item.save()
            messages.success(request, f"Increased quantity for {product.title} in cart.")
        else:
            messages.warning(request, f"Cannot add more of '{product.title}'. Max quantity ({product.quantity}) reached in cart.")
    else:
        messages.success(request, f"Added {product.title} to cart.")

    return redirect(request.META.get('HTTP_REFERER', 'marketplace:home'))

@login_required
def remove_from_cart(request, item_id):
    """Remove a CartItem from the user's cart entirely."""
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
    """Display all 'saved' (wishlist) items for the current user."""
    saved_items = SavedItem.objects.filter(user=request.user).select_related('product').prefetch_related('product__images').all()
    for item in saved_items:
        primary_image = item.product.images.filter(is_primary=True).first()
        item.primary_image_url = primary_image.image.url if primary_image else None
    return render(request, 'cart/saved_list.html', {'saved_items': saved_items})

@login_required
def add_to_saved(request, product_id):
    """Add product to the user's saved list."""
    product = get_object_or_404(Product, id=product_id, is_public=True)
    if product.seller == request.user:
        messages.warning(request, "You cannot save your own product.")
        return redirect(request.META.get('HTTP_REFERER', 'marketplace:home'))

    _, created = SavedItem.objects.get_or_create(user=request.user, product=product)
    if created:
        messages.success(request, f"Saved {product.title}.")
    else:
        messages.info(request, f"{product.title} is already in your saved items.")
    return redirect(request.META.get('HTTP_REFERER', reverse('cart:saved_list')))

@login_required
def remove_from_saved(request, saved_item_id):
    """Remove a product from the user's saved list."""
    try:
        saved_item = SavedItem.objects.get(id=saved_item_id, user=request.user)
        product_title = saved_item.product.title
        saved_item.delete()
        messages.success(request, f"Removed {product_title} from saved items.")
    except SavedItem.DoesNotExist:
        messages.error(request, "Item not found in your saved list.")
    except Exception as e:
        logger.error(f"Error removing saved item {saved_item_id}: {e}", exc_info=True)
        messages.error(request, "Could not remove saved item.")
    return redirect('cart:saved_list')

# --- Fund Distribution (Keep as is, or move to orders/services.py) ---
def distribute_payment(order: Order):
    """Distributes funds to sellers' wallets for a PAID order."""
    if order.status != 'PAID':
        logger.warning(f"Attempted to distribute payment for Order {order.id} with status {order.status}. Skipping.")
        return False

    order_items = order.items.select_related('product', 'seller').all()
    logger.info(f"Distributing payment for Order {order.id} ({len(order_items)} items).")

    platform_fee_percentage = Decimal('0.00') # Example: 0% fee
    distribution_successful = True

    try:
        with transaction.atomic():
            for item in order_items:
                if item.seller:
                    item_subtotal = item.subtotal
                    platform_fee = item_subtotal * platform_fee_percentage
                    amount_to_seller = item_subtotal - platform_fee

                    if amount_to_seller > 0:
                        try:
                            add_funds(
                                user=item.seller,
                                amount=amount_to_seller,
                                transaction_type='SALE',
                                description=f"Sale: {item.quantity}x '{item.product.title if item.product else 'N/A'}' (Order #{str(order.id)[:8]})",
                                related_order_id=str(order.id)
                            )
                            logger.info(f"Credited {amount_to_seller} to seller {item.seller.email} for OrderItem {item.id}")
                        except Exception as e:
                            logger.error(f"Failed to credit seller {item.seller.email} for OrderItem {item.id} (Order {order.id}): {e}", exc_info=True)
                            distribution_successful = False
                            raise ValueError(f"Distribution failed for seller {item.seller.email}.") from e
                    else:
                        logger.warning(f"Calculated amount for seller {item.seller.email} is zero or less for OrderItem {item.id}. Skipping credit.")
                else:
                    logger.warning(f"No seller linked to OrderItem {item.id} in Order {order.id}. Cannot distribute funds.")

            if not distribution_successful: # Should be caught by the raise above, but belt-and-suspenders
                 raise ValueError("Fund distribution failed within the loop.")

    except Exception as e:
        logger.error(f"Fund distribution failed for Order {order.id}. Error: {e}", exc_info=True)
        # Mark order as needing manual review?
        # order.status = 'DISTRIBUTION_FAILED' # Add this status if needed
        # order.failure_reason = f"Distribution Error: {e}"[:255]
        # order.save(update_fields=['status', 'failure_reason'])
        return False # Indicate overall failure

    logger.info(f"Successfully distributed funds for Order {order.id}")
    return True


# --- Checkout View (Updated) ---
@login_required
def checkout_view(request):
    cart = initialize_cart(request.user)
    cart_items = cart.cart_items.select_related('product', 'product__seller').all()

    if not cart_items:
        messages.warning(request, "Your cart is empty.")
        return redirect('marketplace:home')

    total_price = sum((item.product.price or 0) * item.quantity for item in cart_items)
    buyer_wallet, _ = Wallet.objects.get_or_create(user=request.user)

    # --- POST Request Handling ---
    if request.method == 'POST':
        payment_method_choice = request.POST.get('payment_method')
        selected_xendit_channel = request.POST.get('xendit_channel') # The key, e.g., EWALLET_GCASH

        # --- Basic Validation ---
        if not payment_method_choice:
            messages.error(request, "Please select a payment method.")
            return redirect('cart:checkout')

        if payment_method_choice == 'XENDIT' and not selected_xendit_channel:
            messages.error(request, "Please select a specific external payment channel.")
            return redirect('cart:checkout')

        # --- Wallet Balance Check (Server-side) ---
        if payment_method_choice == 'WALLET' and buyer_wallet.balance < total_price:
            messages.error(request, "Insufficient wallet balance.")
            return redirect('cart:checkout')

        # --- Stock Availability Check ---
        # (Keep the stock check loop as is)
        for item in cart_items:
            try:
                product = Product.objects.select_for_update().get(id=item.product.id) # Lock product row
                if item.quantity > product.quantity:
                    messages.error(request, f"Not enough stock for '{product.title}'. Only {product.quantity} available.")
                    return redirect('cart:cart_list')
                if product.is_sold:
                    messages.error(request, f"Sorry, '{product.title}' has already been sold.")
                    return redirect('cart:cart_list')
            except Product.DoesNotExist:
                messages.error(request, f"Product '{item.product.title}' is no longer available.")
                return redirect('cart:cart_list')

        # --- Create Order and OrderItems ---
        # (Keep the order creation logic within transaction.atomic as is)
        order = None
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    buyer=request.user,
                    total_amount=total_price,
                    status='PENDING',
                    payment_method=payment_method_choice,
                    currency='PHP', # Or get dynamically
                    country='PH',   # Or get dynamically
                    payment_channel=selected_xendit_channel if payment_method_choice == 'XENDIT' else None,
                )
                order_items_to_create = []
                for item in cart_items:
                    order_items_to_create.append(
                        OrderItem(
                            order=order,
                            product=item.product,
                            seller=item.product.seller,
                            quantity=item.quantity,
                            price=item.product.price
                        )
                    )
                OrderItem.objects.bulk_create(order_items_to_create)
                logger.info(f"Created Order {order.id} with status PENDING for user {request.user.email}.")
        except Exception as e:
            logger.error(f"Failed to create order structure for user {request.user.email}: {e}", exc_info=True)
            messages.error(request, "Could not create your order structure. Please try again.")
            return redirect('cart:cart_list')

        if not order:
            messages.error(request, "Failed to initialize the order. Please try again.")
            return redirect('cart:cart_list')

        # --- Process Payment ---
        if payment_method_choice == 'WALLET':
            # --- Wallet Payment Logic ---
            # (Keep the existing atomic wallet logic: deduct funds, update order, deduct stock, distribute, clear cart)
            try:
                with transaction.atomic():
                    # 1. Deduct from buyer
                    deduct_funds(
                        user=request.user, amount=total_price, transaction_type='PURCHASE',
                        description=f"Purchase (Order #{str(order.id)[:8]})", related_order_id=str(order.id)
                    )
                    # 2. Mark order PAID
                    order.status = 'PAID'
                    order.save(update_fields=['status'])
                    logger.info(f"Order {order.id} paid via WALLET.")

                    # 3. Deduct stock
                    stock_deducted_successfully = True
                    for item in order.items.all():
                        prod = item.product
                        if prod:
                            try:
                                updated_rows = Product.objects.filter(id=prod.id, quantity__gte=item.quantity).update(quantity=models.F('quantity') - item.quantity)
                                if updated_rows == 0: raise ValueError(f"Stock unavailable for Product {prod.id} during final check.")
                                logger.info(f"Deducted {item.quantity} from stock for Product {prod.id}.")
                                prod.refresh_from_db()
                                if prod.quantity <= 0 and not prod.is_sold:
                                    prod.is_sold = True
                                    prod.save(update_fields=['is_sold'])
                                    logger.info(f"Marked Product {prod.id} as sold.")
                            except Exception as stock_e:
                                logger.error(f"Error updating stock for Product {prod.id} (Order {order.id}): {stock_e}", exc_info=True)
                                stock_deducted_successfully = False
                                raise # Rollback transaction
                        else: logger.warning(f"Product not found for OrderItem {item.id} during stock deduction.")

                    # 4. Distribute funds
                    if not stock_deducted_successfully: raise ValueError("Stock deduction failed.")
                    distribution_ok = distribute_payment(order)
                    if not distribution_ok: raise ValueError("Fund distribution failed.")

                    # 5. Clear cart
                    cart.cart_items.all().delete()
                    logger.info(f"Cleared cart for user {request.user.email} after successful wallet payment.")

                messages.success(request, "Payment successful using wallet!")
                return redirect(reverse('orders:order_detail', kwargs={'order_id': order.id}))

            except ValueError as e:
                logger.warning(f"Wallet payment transaction failed for Order {order.id}: {e}")
                if order.status == 'PENDING': # Check if it's still pending before marking failed
                    order.status = 'FAILED'
                    order.failure_reason = str(e)[:255]
                    order.save(update_fields=['status', 'failure_reason'])
                messages.error(request, f"Wallet payment failed: {e}")
                return redirect('cart:checkout')
            except Exception as e:
                logger.error(f"Unexpected error during wallet payment processing for Order {order.id}: {e}", exc_info=True)
                if order.status == 'PENDING':
                    order.status = 'FAILED'
                    order.failure_reason = "Unexpected server error."[:255]
                    order.save(update_fields=['status', 'failure_reason'])
                messages.error(request, "An unexpected error occurred during wallet payment.")
                return redirect('cart:checkout')

        elif payment_method_choice == 'XENDIT':
            logger.info(f"Initiating Xendit payment for Order {order.id} with channel key: {selected_xendit_channel}")
            xendit_response = create_xendit_payment_request(order, request, selected_xendit_channel)

            response_status = xendit_response.get('status')
            response_type = xendit_response.get('type')

            # --- Handle Xendit Response ---
            if response_status in ['PENDING', 'REQUIRES_ACTION']:
                # Clear cart for off-site payment methods
                cart.cart_items.all().delete()
                logger.info(f"Cleared cart for user {request.user.email} after initiating Xendit payment for Order {order.id}.")

                # *** REDIRECT IF URL IS PROVIDED ***
                if response_type == 'REDIRECT' and 'payment_url' in xendit_response:
                    payment_url = xendit_response['payment_url']
                    logger.info(f"Redirecting user {request.user.email} to Xendit URL: {payment_url} for Order {order.id}")
                    return redirect(payment_url) # <<< THE ACTUAL REDIRECT

                # --- Display Info for Non-Redirect Methods ---
                elif response_type == 'VIRTUAL_ACCOUNT':
                    logger.info(f"Displaying VA details for Order {order.id} to user {request.user.email}")
                    context = {'order': order, 'va_details': xendit_response.get('details')}
                    return render(request, 'payments/virtual_account_details.html', context)
                elif response_type == 'QR_CODE':
                    logger.info(f"Displaying QR Code for Order {order.id} to user {request.user.email}")
                    context = {'order': order, 'qr_string': xendit_response.get('qr_string')}
                    return render(request, 'payments/qr_code_details.html', context)
                elif response_type == 'OTC':
                    logger.info(f"Displaying OTC details for Order {order.id} to user {request.user.email}")
                    context = {'order': order, 'otc_details': xendit_response.get('details')}
                    return render(request, 'payments/otc_details.html', context)
                else: # Fallback for PENDING/REQUIRES_ACTION without specific instructions/redirect
                    logger.warning(f"Xendit returned {response_status} status but unknown type '{response_type}' or no redirect URL for Order {order.id}")
                    channel_name = selected_xendit_channel.replace('_', ' ').title()
                    messages.info(request, f"Your payment via {channel_name} is {response_status.lower()}. Please follow instructions or check for updates.")
                    return redirect(reverse('orders:order_detail', kwargs={'order_id': order.id}))

            elif response_status == 'SUCCEEDED':
                # (Keep the instant success handling - though rare, ensure atomicity)
                 logger.info(f"Xendit payment for Order {order.id} succeeded instantly during creation.")
                 try:
                     with transaction.atomic():
                         # 1. Mark Order Paid
                         order.status = 'PAID'
                         order.xendit_payment_id = xendit_response.get('xendit_id') # Store the Payment Request ID or payment ID if available
                         order.save(update_fields=['status', 'xendit_payment_id']) # Update correct field
                         # 2. Deduct Stock
                         for item in order.items.all():
                            prod = item.product
                            if prod:
                                updated_rows = Product.objects.filter(id=prod.id, quantity__gte=item.quantity).update(quantity=models.F('quantity') - item.quantity)
                                if updated_rows == 0: raise ValueError(f"Stock unavailable for Product {prod.id} during instant success processing.")
                                prod.refresh_from_db()
                                if prod.quantity <= 0 and not prod.is_sold:
                                    prod.is_sold = True
                                    prod.save(update_fields=['is_sold'])
                         # 3. Distribute Funds
                         distribution_ok = distribute_payment(order)
                         if not distribution_ok: raise ValueError("Fund distribution failed during instant success processing.")
                         # 4. Clear Cart
                         cart.cart_items.all().delete()

                     channel_name = selected_xendit_channel.replace('_', ' ').title()
                     messages.success(request, f"Payment via {channel_name} successful!")
                     return redirect(reverse('orders:order_detail', kwargs={'order_id': order.id}))
                 except Exception as instant_e:
                     logger.error(f"Error processing instant success for Order {order.id}: {instant_e}", exc_info=True)
                     messages.error(request, "Payment was confirmed, but there was an error finalizing the order. Please contact support.")
                     return redirect(reverse('orders:order_detail', kwargs={'order_id': order.id}))

            else: # FAILED or UNEXPECTED status from service
                error_message = xendit_response.get('error', 'Unknown payment initiation error.')
                logger.error(f"Failed to initiate Xendit payment for Order {order.id}. Service Response: {xendit_response}")
                order.status = 'FAILED'
                order.failure_reason = error_message[:255]
                order.save(update_fields=['status', 'failure_reason'])
                messages.error(request, f"Payment initiation failed: {error_message}")
                return redirect('cart:checkout')

    # --- GET Request Handling ---
    else: # GET
        # (Keep the GET request logic as is, preparing context for the template)
        xendit_channels = {
             "EWALLET_GCASH": "GCash", "EWALLET_GRABPAY": "GrabPay", "EWALLET_PAYMAYA": "Maya",
             "EWALLET_SHOPEEPAY": "ShopeePay",
             "DIRECT_DEBIT_BPI": "BPI Direct Debit", "DIRECT_DEBIT_UBP": "Unionbank Direct Debit",
             "VIRTUAL_ACCOUNT_BPI": "BPI Virtual Account", "VIRTUAL_ACCOUNT_BDO": "BDO Virtual Account",
             "VIRTUAL_ACCOUNT_UNIONBANK": "Unionbank Virtual Account", "VIRTUAL_ACCOUNT_METROBANK": "Metrobank Virtual Account",
             "VIRTUAL_ACCOUNT_RCBC": "RCBC Virtual Account", "VIRTUAL_ACCOUNT_CHINABANK": "Chinabank Virtual Account",
             "OTC_7ELEVEN": "7-Eleven", "OTC_CEBUANA": "Cebuana Lhuillier", "OTC_ECPAY": "ECPay",
             "OTC_MLHUILLIER": "M Lhuillier", "OTC_PALAWAN": "Palawan Pawnshop", "OTC_LBC": "LBC",
             "QR_CODE_QRPH": "QRPh",
             "CARD_CARD": "Credit/Debit Card",
         }
        context = {
            'cart': cart, 'cart_items': cart_items, 'total_price': total_price,
            'buyer_wallet_balance': buyer_wallet.balance,
            'can_afford_with_wallet': buyer_wallet.balance >= total_price,
            'xendit_channels': xendit_channels,
        }
        for item in cart_items: item.subtotal = (item.product.price or 0) * item.quantity
        return render(request, 'cart/checkout.html', context)