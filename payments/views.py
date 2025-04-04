# payments/views.py

from django.shortcuts import render, HttpResponse, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.db import transaction, models # Import models for F expression
from django.contrib import messages
from django.conf import settings # For webhook token verification
import json
import logging

from orders.models import Order, Product, OrderItem # Import Product and OrderItem
# Use the function from cart.views or move it to a shared location
# Make sure the path is correct based on your project structure
# If you moved distribute_payment to orders/services.py, import from there.
from cart.views import distribute_payment, initialize_cart

logger = logging.getLogger(__name__)

# --- Webhook Verification (Implement this properly!) ---
def verify_xendit_webhook(request):
    """Verifies the callback token from Xendit."""
    callback_token = request.headers.get('x-callback-token')
    expected_token = getattr(settings, 'XENDIT_CALLBACK_VERIFICATION_TOKEN', None)

    if not expected_token:
        logger.critical("XENDIT_CALLBACK_VERIFICATION_TOKEN is not set in settings! Webhook verification skipped.")
        # In production, you might want to return False here unless explicitly allowing unverified webhooks during setup.
        return True # Allow during development if token isn't set

    if not callback_token or callback_token != expected_token:
        logger.warning(f"Invalid or missing Xendit callback token. Received: '{callback_token}'")
        return False

    logger.info("Xendit callback token verified.")
    return True

# --- Webhook Handler ---
@csrf_exempt
@require_POST
def xendit_webhook(request):
    if not verify_xendit_webhook(request):
        return HttpResponse("Verification failed.", status=403)

    try:
        payload = json.loads(request.body)
        event_type = payload.get('event')
        data = payload.get('data')

        logger.info(f"Received Xendit Webhook: Event='{event_type}'")
        # logger.debug(f"Webhook Payload: {json.dumps(payload, indent=2)}") # Optional: Debug logging

        # --- Extract Order ID ---
        # Adapt based on which Xendit product (Payment Request, Invoice, etc.) sends the webhook
        order_id_from_ref = data.get('reference_id') if data else None         # Common for Payment Request
        order_id_from_pr_id = data.get('payment_request_id') if data else None # Alternate for Payment Request
        order_id_from_invoice = data.get('external_id') if data else None      # Common for Invoice

        order_id = order_id_from_ref or order_id_from_pr_id or order_id_from_invoice
        xendit_payment_id = data.get('id') if data else None # Xendit's ID for the payment/invoice/request

        if not order_id:
            logger.error("Webhook payload missing expected order reference ('reference_id', 'payment_request_id', or 'external_id').")
            return HttpResponse("Missing order reference", status=400)

        # --- Retrieve Order ---
        try:

            order = Order.objects.get(id=order_id)
            logger.info(f"Found Order {order.id} for webhook processing. Current status: {order.status}")
        except Order.DoesNotExist:
            logger.error(f"Order with ID {order_id} not found for webhook event '{event_type}'.")
            return HttpResponse("Order not found, webhook acknowledged.", status=200) # Acknowledge
        except ValueError:
            logger.error(f"Invalid Order ID format received: {order_id}")
            return HttpResponse("Invalid order ID format", status=400)

        # --- Idempotency Check ---
        # Check if the final state we are about to transition to is already set
        if event_type in ['payment.succeeded', 'payment_request.succeeded', 'invoice.paid'] and order.status == 'PAID':
             logger.info(f"Order {order_id} is already PAID. Ignoring duplicate success webhook.")
             return HttpResponse("Webhook acknowledged (already processed)", status=200)
        if event_type in ['payment.failed', 'payment_request.failed', 'invoice.expired'] and order.status == 'FAILED':
             logger.info(f"Order {order_id} is already FAILED. Ignoring duplicate failure webhook.")
             return HttpResponse("Webhook acknowledged (already processed)", status=200)

        # Allow processing only if the order is currently PENDING
        if order.status != 'PENDING':
            logger.warning(f"Received webhook for Order {order_id} which is not PENDING (Status: {order.status}). Event: {event_type}. Ignoring.")
            return HttpResponse("Webhook acknowledged (order not pending)", status=200)

        # --- Process based on event type ---
        try:
            with transaction.atomic():
                # Re-fetch and lock the order row *inside* the transaction
                order_locked = Order.objects.select_for_update().get(id=order_id)

                # Double-check status *after* locking to prevent race conditions
                if order_locked.status != 'PENDING':
                    logger.warning(f"Order {order_id} status changed between check and lock (Now: {order_locked.status}). Ignoring webhook.")
                    return HttpResponse("Webhook acknowledged (status changed)", status=200)

                # --- SUCCESSFUL PAYMENT ---
                if event_type in ['payment.succeeded', 'payment_request.succeeded', 'invoice.paid']:
                    logger.info(f"Processing successful payment webhook for locked Order {order_locked.id}")

                    # 1. Update Order Status and Payment ID
                    order_locked.status = 'PAID'
                    if xendit_payment_id:

                        order_locked.xendit_payment_id = xendit_payment_id
                        update_fields = ['status', 'xendit_payment_id']
                    else:
                        update_fields = ['status']
                    order_locked.save(update_fields=update_fields)
                    logger.info(f"Order {order_locked.id} status updated to PAID.")

                    # 2. Deduct Stock
                    logger.info(f"Deducting stock for Order {order_locked.id}")
                    order_items = OrderItem.objects.filter(order=order_locked).select_related('product') # Fetch items linked to the order
                    for item in order_items:
                        prod = item.product
                        if not prod:
                            logger.warning(f"Product for OrderItem {item.id} (Order {order_locked.id}) not found, skipping stock deduction.")
                            continue # Or raise error depending on policy

                        try:
                            # Atomic update using F() expression
                            updated_rows = Product.objects.filter(id=prod.id, quantity__gte=item.quantity).update(quantity=models.F('quantity') - item.quantity)
                            if updated_rows == 0:
                                logger.error(f"Stock update failed for Product {prod.id} (Order {order_locked.id}). Stock likely changed or product gone.")
                                # Rollback the entire transaction
                                raise ValueError(f"Insufficient stock or product missing during webhook processing for Product {prod.id}")
                            else:
                                logger.info(f"Deducted {item.quantity} from stock for Product {prod.id}.")
                                # Refresh and check if sold out
                                prod.refresh_from_db(fields=['quantity', 'is_sold'])
                                if prod.quantity <= 0 and not prod.is_sold:
                                    prod.is_sold = True
                                    prod.save(update_fields=['is_sold'])
                                    logger.info(f"Marked Product {prod.id} as sold.")
                        except Exception as stock_e:
                            logger.error(f"Error updating stock for Product {prod.id} (Order {order_locked.id}): {stock_e}", exc_info=True)
                            raise # Rollback transaction

                    # 3. Distribute Funds (Pass the locked order)
                    logger.info(f"Initiating fund distribution for Order {order_locked.id}")
                    distribution_successful = distribute_payment(order_locked) # Call the function
                    if not distribution_successful:
                        # distribute_payment should ideally raise error on failure, but check return just in case
                        logger.error(f"Fund distribution function returned false for Order {order_locked.id}. Rolling back.")
                        raise ValueError("Fund distribution failed.")

                    # 4. Clear the Buyer's Cart
                    if order_locked.buyer:
                        try:
                            cart = initialize_cart(order_locked.buyer)
                            deleted_count, _ = cart.cart_items.all().delete()
                            logger.info(f"Cleared {deleted_count} cart items for user {order_locked.buyer.email} (Order {order_locked.id}).")
                        except Exception as cart_e:
                            # Log error but don't fail the transaction just for cart clearing
                            logger.error(f"Failed to clear cart for Order {order_locked.id} buyer {order_locked.buyer.email}: {cart_e}", exc_info=True)
                    else:
                         logger.warning(f"Order {order_locked.id} has no buyer, cannot clear cart.")

                    logger.info(f"Successfully processed success webhook for Order {order_locked.id}")
                    return HttpResponse("Webhook received and processed successfully.", status=200)

                # --- FAILED/EXPIRED PAYMENT ---
                elif event_type in ['payment.failed', 'payment_request.failed', 'invoice.expired']:
                    logger.info(f"Processing failed/expired payment webhook for locked Order {order_locked.id}")
                    order_locked.status = 'FAILED'
                    # Store failure reason if available
                    failure_code = data.get('failure_code') or data.get('failure_reason', 'Failure reported by webhook')
                    order_locked.failure_reason = str(failure_code)[:255] # Store reason
                    order_locked.save(update_fields=['status', 'failure_reason'])
                    logger.info(f"Order {order_locked.id} status updated to FAILED. Reason: {order_locked.failure_reason}")
                    # Optional: Add logic to notify user, potentially restock items if needed
                    return HttpResponse("Webhook received and processed successfully.", status=200)

                # --- OTHER EVENTS ---
                else:
                    logger.info(f"Received unhandled Xendit event type '{event_type}' for Order {order_locked.id}. Ignoring.")
                    return HttpResponse("Webhook received, event not handled.", status=200) # Acknowledge

        except ValueError as ve: # Catch specific errors raised for rollback
            logger.error(f"Transaction rolled back for Order {order_id}. Reason: {ve}", exc_info=False)
            # Let the outer exception handler return 500 to signal retry maybe needed
            raise
        except Exception as e_atomic:
             # Catch unexpected errors within the atomic block
             logger.error(f"Critical error inside atomic block for Order {order_id}: {e_atomic}", exc_info=True)
             # Let the outer exception handler return 500
             raise


    except json.JSONDecodeError:
        logger.error("Invalid JSON received in Xendit webhook.", exc_info=True)
        return HttpResponse("Invalid JSON", status=400)
    except Exception as e:
        # Catch-all for unexpected errors (e.g., DB connection issues before atomic block)
        order_id_ref = "N/A"
        try: # Try to get order ID again for logging context
            payload_check = json.loads(request.body)
            order_id_ref = payload_check.get('data', {}).get('reference_id', 'N/A')
        except: pass
        logger.critical(f"Critical error processing Xendit webhook for Order Ref '{order_id_ref}': {e}", exc_info=True)
        # Return 500 to signal Xendit to potentially retry (check their retry policy)
        return HttpResponse("Internal Server Error", status=500)


# --- Payment Callback View (Keep as is) ---
def payment_callback_view(request, status):
    order_ref = request.GET.get('ref_id') # Get order ID from query param
    order = None

    if order_ref:
        try:
            order = Order.objects.get(id=order_ref)
        except (Order.DoesNotExist, ValueError):
            logger.warning(f"Order {order_ref} not found on {status} callback.")

    context = {'status': status, 'order': order} # Pass the order object if found
    template_name = 'payments/payment_status.html'

    if status == 'success':
        if order and order.status == 'PAID':
             messages.success(request, f"Payment for Order #{str(order.id)[:8]} confirmed!")
        else:
             messages.info(request, "Your payment redirect was successful. We are awaiting final confirmation.")
        if order:
            return redirect(reverse('orders:order_detail', kwargs={'order_id': order.id}))
        else:
             return render(request, template_name, context) # Show generic if order not found
    else: # failure or potentially cancelled
        messages.error(request, "Your payment failed, was cancelled, or encountered an issue during redirect.")
        context['checkout_url'] = reverse('cart:checkout')
        return render(request, template_name, context)