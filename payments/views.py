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
import traceback # For detailed error logging

from orders.models import Order, Product, OrderItem # Import Product and OrderItem
# Use the function from cart.views or move it to a shared location
# Make sure the path is correct based on your project structure
# If you moved distribute_payment to orders/services.py, import from there.
# Assuming it's still in cart.views for now:
from cart.views import distribute_payment, initialize_cart

# Ensure logger is configured properly in settings.py if using file logging
logger = logging.getLogger(__name__)

# --- Webhook Verification ---
def verify_xendit_webhook(request):
    """Verifies the callback token from Xendit."""
    # Log headers for debugging token issues
    logger.debug(f"Webhook Headers: {request.headers}")
    callback_token = request.headers.get('x-callback-token')
    expected_token = getattr(settings, 'XENDIT_CALLBACK_VERIFICATION_TOKEN', None)

    if not expected_token:
        # CRITICAL: Avoid this in production. Set the token!
        logger.critical("CRITICAL: XENDIT_CALLBACK_VERIFICATION_TOKEN is not set in settings! Webhook verification is currently BYPASSED.")
        return True # Allow during development ONLY if token isn't set

    if not callback_token:
        logger.error("Webhook verification failed: Missing 'x-callback-token' in headers.")
        return False

    if callback_token != expected_token:
        # Mask token in logs for security
        logger.error(f"Webhook verification failed: Invalid token. Received: '{callback_token[:5]}...' (masked), Expected: '{expected_token[:5]}...' (masked)")
        return False

    logger.info("Xendit callback token verified successfully.")
    return True

# --- Webhook Handler ---
@csrf_exempt # Necessary for external POST requests like webhooks
@require_POST # Ensure only POST requests are accepted
def xendit_webhook(request):
    logger.info("--- Received Xendit Webhook Request ---")

    # Log raw body for deep debugging if needed (can be large)
    try:
        raw_body = request.body.decode('utf-8')
        logger.debug(f"Raw Webhook Body:\n{raw_body[:1000]}...") # Log first 1000 chars
    except Exception as decode_err:
        logger.error(f"Error decoding request body: {decode_err}")
        raw_body = None # Indicate body couldn't be decoded

    # --- Verification (Task 2) ---
    if not verify_xendit_webhook(request):
        # Return 403 Forbidden if verification fails
        return HttpResponse("Webhook verification failed.", status=403)

    # --- Payload Parsing ---
    try:
        if not raw_body: # Check if decoding failed
             raise json.JSONDecodeError("Cannot parse empty or undecoded body", "", 0)
        payload = json.loads(raw_body)
        # Log parsed payload clearly
        logger.debug(f"Parsed Webhook Payload:\n{json.dumps(payload, indent=2)}")
    except json.JSONDecodeError:
        logger.error("Invalid JSON received in Xendit webhook.", exc_info=True)
        return HttpResponse("Invalid JSON data.", status=400) # Bad request

    # --- Extract Key Information ---
    event_type = payload.get('event')
    data = payload.get('data')
    # Log extracted event and check if data exists
    logger.info(f"Webhook Event Type: '{event_type}'")
    if not data:
         logger.error("Webhook payload missing 'data' field.")
         # Acknowledge receipt but indicate error processing
         return HttpResponse("Payload missing data field.", status=400)

    # --- Identify Order (Task 2) ---
    # Determine order ID based on potential fields in 'data'
    order_id = None
    possible_id_fields = ['reference_id', 'payment_request_id', 'external_id']
    for field in possible_id_fields:
        order_id = data.get(field)
        if order_id:
            logger.info(f"Order ID found in field '{field}': {order_id}")
            break # Stop searching once found

    # Xendit's own ID for the specific payment/request (useful for reconciliation/Task 5b)
    # Use appropriate ID field based on the event type if needed, 'id' is common
    xendit_payment_id = data.get('id')
    logger.info(f"Xendit Object ID from payload ('data.id'): {xendit_payment_id}")

    if not order_id:
        logger.error(f"Webhook payload 'data' missing expected order reference field ({possible_id_fields}). Data: {data}")
        # Still return 200 OK to Xendit to prevent retries for a structurally invalid payload from our perspective
        return HttpResponse("Missing order reference in payload.", status=200)

    # --- Retrieve Order (Task 2) ---
    try:
        # Using UUID field requires matching type
        order = Order.objects.get(id=order_id)
        logger.info(f"Successfully retrieved Order {order.id}. Current status: {order.status}")
    except Order.DoesNotExist:
        logger.error(f"Order with ID '{order_id}' not found in database for webhook event '{event_type}'.")
        # Acknowledge receipt to Xendit, as the order might be old or from a different system
        return HttpResponse("Order not found, webhook acknowledged.", status=200)
    except (ValueError, TypeError) as e: # Catch if order_id is not a valid UUID format
        logger.error(f"Invalid Order ID format received: '{order_id}'. Error: {e}")
        # Acknowledge receipt, but indicate bad data format issue
        return HttpResponse("Invalid order ID format.", status=200) # Or 400 if you prefer

    # --- Idempotency Checks (Task 2) ---
    # Check if the order is already in the target state for this event
    is_success_event = event_type in ['payment.succeeded', 'payment_request.succeeded', 'invoice.paid']
    is_failure_event = event_type in ['payment.failed', 'payment_request.failed', 'invoice.expired']

    if is_success_event and order.status == 'PAID':
        logger.info(f"Idempotency Check: Order {order_id} is already PAID. Ignoring duplicate success webhook '{event_type}'.")
        return HttpResponse("Webhook acknowledged (Order already PAID)", status=200)

    if is_failure_event and order.status == 'FAILED':
        logger.info(f"Idempotency Check: Order {order_id} is already FAILED. Ignoring duplicate failure webhook '{event_type}'.")
        return HttpResponse("Webhook acknowledged (Order already FAILED)", status=200)

    # --- State Check: Process only if order is PENDING ---
    # Allow FAILED status update even if order was marked failed by API earlier (e.g., for expired events)
    if order.status != 'PENDING' and not (is_failure_event and order.status == 'FAILED'):
        logger.warning(f"State Check: Received webhook event '{event_type}' for Order {order_id}, but order status is '{order.status}' (not PENDING or target FAILED). Ignoring.")
        return HttpResponse("Webhook acknowledged (Order not in processable state)", status=200)

    # --- Process based on Event Type within an Atomic Transaction ---
    try:
        with transaction.atomic():
            logger.info(f"--- Starting Atomic Transaction for Order {order_id} ---")
            # Re-fetch and lock the order row *inside* the transaction for safety
            order_locked = Order.objects.select_for_update().get(id=order_id)
            logger.info(f"Locked Order {order_locked.id}. Verifying status within transaction...")

            # Double-check status *after* locking to prevent race conditions
            current_status_locked = order_locked.status
            if current_status_locked != 'PENDING' and not (is_failure_event and current_status_locked == 'FAILED'):
                 # If it changed from PENDING to something else non-final (e.g., PROCESSING) or already PAID
                 if not (is_success_event and current_status_locked == 'PAID') and not (is_failure_event and current_status_locked == 'FAILED'):
                     logger.warning(f"Race Condition Check: Order {order_id} status changed to '{current_status_locked}' between initial check and lock. Aborting transaction.")
                     return HttpResponse("Webhook acknowledged (Order status changed concurrently)", status=200)
                 else:
                      # If it changed to the target state already, handle idempotency again
                      logger.info(f"Idempotency Check (within lock): Order {order_id} already in target state '{current_status_locked}'. Ignoring webhook '{event_type}'.")
                      return HttpResponse(f"Webhook acknowledged (Order already {current_status_locked})", status=200)


            logger.info(f"Order {order_locked.id} status '{current_status_locked}' confirmed processable within transaction for event '{event_type}'.")

            # --- SUCCESSFUL PAYMENT ---
            # Process only if the current status is PENDING
            if is_success_event and current_status_locked == 'PENDING':
                logger.info(f"Processing SUCCESS event '{event_type}' for Order {order_locked.id}")

                # 1. Update Order Status and Payment ID (Task 5b)
                logger.debug(f"Updating Order {order_locked.id} status from PENDING to PAID.")
                order_locked.status = 'PAID'
                update_fields = ['status']
                if xendit_payment_id:
                    logger.debug(f"Updating Order {order_locked.id} xendit_payment_id to '{xendit_payment_id}'.")
                    order_locked.xendit_payment_id = xendit_payment_id # Save the ID from the webhook
                    update_fields.append('xendit_payment_id')
                else:
                     logger.warning(f"No 'data.id' (xendit_payment_id) found in payload for success event '{event_type}' for Order {order_locked.id}.")

                # Clear failure reason if it was set previously by API response
                if order_locked.failure_reason:
                    logger.debug(f"Clearing previous failure_reason for Order {order_locked.id}")
                    order_locked.failure_reason = None
                    update_fields.append('failure_reason')

                order_locked.save(update_fields=update_fields)
                logger.info(f"Order {order_locked.id} status and payment ID updated successfully.")

                # 2. Deduct Stock (Task 3 Verification)
                logger.info(f"--- Starting Stock Deduction for Order {order_locked.id} ---")
                order_items = OrderItem.objects.filter(order=order_locked).select_related('product', 'seller')
                if not order_items.exists():
                     logger.warning(f"Order {order_locked.id} has no associated OrderItems. Skipping stock deduction.")

                products_to_check_sold_status = []

                for item in order_items:
                    prod = item.product
                    logger.debug(f"Processing OrderItem {item.id} for Product ID {prod.id if prod else 'N/A'} (Title: {prod.title if prod else 'N/A'}), Quantity: {item.quantity}")

                    if not prod:
                        logger.warning(f"Product for OrderItem {item.id} (Order {order_locked.id}) not found in DB. Skipping stock deduction for this item.")
                        continue

                    try:
                        logger.debug(f"Attempting to deduct {item.quantity} from Product {prod.id} (Current stock: {prod.quantity})")
                        updated_rows = Product.objects.filter(
                            id=prod.id,
                            quantity__gte=item.quantity
                        ).update(
                            quantity=models.F('quantity') - item.quantity
                        )

                        if updated_rows == 0:
                            logger.error(f"Stock update FAILED for Product {prod.id} (Order {order_locked.id}). Expected to deduct {item.quantity}, but `updated_rows` was 0. Insufficient stock or product modified concurrently?")
                            raise ValueError(f"Insufficient stock or product missing/modified during webhook processing for Product {prod.id} (Order {order_locked.id})")
                        else:
                            logger.info(f"Successfully deducted {item.quantity} from stock for Product {prod.id}. updated_rows={updated_rows}")
                            products_to_check_sold_status.append(prod.id)

                    except Exception as stock_e:
                        logger.error(f"Unexpected error during stock update for Product {prod.id} (Order {order_locked.id}): {stock_e}", exc_info=True)
                        raise

                logger.info(f"--- Finished Stock Deduction Loop for Order {order_locked.id} ---")

                # 3. Update `is_sold` Status (Task 4 Verification)
                logger.info(f"--- Checking 'is_sold' status for affected products (Order {order_locked.id}) ---")
                if products_to_check_sold_status:
                    updated_products = Product.objects.filter(id__in=products_to_check_sold_status)
                    for prod_to_check in updated_products:
                        logger.debug(f"Checking Product {prod_to_check.id}: Current Quantity={prod_to_check.quantity}, Is Sold={prod_to_check.is_sold}")
                        if prod_to_check.quantity <= 0 and not prod_to_check.is_sold:
                            logger.info(f"Product {prod_to_check.id} quantity is now {prod_to_check.quantity}. Marking as sold.")
                            prod_to_check.is_sold = True
                            prod_to_check.save(update_fields=['is_sold'])
                            logger.info(f"Product {prod_to_check.id} marked as sold successfully.")
                        elif prod_to_check.quantity > 0 and prod_to_check.is_sold:
                             logger.warning(f"Product {prod_to_check.id} has quantity {prod_to_check.quantity} but is marked as sold. Consider un-marking it.")
                        else:
                             logger.debug(f"Product {prod_to_check.id} does not need 'is_sold' status change.")
                else:
                    logger.info("No products had stock deducted, skipping 'is_sold' check.")
                logger.info(f"--- Finished 'is_sold' Status Check for Order {order_locked.id} ---")


                # 4. Distribute Funds (Placeholder - Ensure this function is robust)
                logger.info(f"Calling 'distribute_payment' for Order {order_locked.id}")
                try:
                    distribution_successful = distribute_payment(order_locked)
                    logger.info(f"'distribute_payment' returned: {distribution_successful}")
                    if not distribution_successful:
                        logger.error(f"Fund distribution function failed for Order {order_locked.id}. Rolling back transaction.")
                        raise ValueError("Fund distribution failed.")
                except Exception as dist_e:
                     logger.error(f"Error calling 'distribute_payment' for Order {order_locked.id}: {dist_e}", exc_info=True)
                     raise


                # 5. Clear the Buyer's Cart (Optional)
                if order_locked.buyer:
                    logger.info(f"Attempting to clear cart for buyer {order_locked.buyer.email} (Order {order_locked.id}).")
                    try:
                        cart = initialize_cart(order_locked.buyer)
                        deleted_count, deleted_items_dict = cart.cart_items.all().delete()
                        logger.info(f"Cleared {deleted_count} cart items for user {order_locked.buyer.email}. Details: {deleted_items_dict}")
                    except Exception as cart_e:
                        logger.error(f"Non-critical error: Failed to clear cart for Order {order_locked.id} buyer {order_locked.buyer.email}: {cart_e}", exc_info=True)
                else:
                    logger.warning(f"Order {order_locked.id} has no buyer associated. Cannot clear cart.")

                # End of Successful Payment Block
                logger.info(f"--- Successfully processed success webhook event '{event_type}' for Order {order_locked.id} within transaction ---")


            # --- FAILED/EXPIRED PAYMENT ---
            # Process only if current status is PENDING or already FAILED (for idempotency)
            elif is_failure_event and current_status_locked in ['PENDING', 'FAILED']:
                logger.info(f"Processing FAILURE/EXPIRED event '{event_type}' for Order {order_locked.id}")

                # Update Order Status and Failure Reason (only if not already FAILED)
                if current_status_locked == 'PENDING':
                    order_locked.status = 'FAILED'
                    failure_code = data.get('failure_code')
                    failure_reason_from_payload = data.get('failure_reason')
                    reason = failure_code or failure_reason_from_payload or f"Expired/Failed: {event_type}"

                    logger.info(f"Updating Order {order_locked.id} status to FAILED. Reason: '{reason}'")
                    order_locked.failure_reason = str(reason)[:255]
                    order_locked.save(update_fields=['status', 'failure_reason'])
                    logger.info(f"Order {order_locked.id} status updated to FAILED.")
                else:
                    logger.info(f"Order {order_locked.id} was already FAILED. No status change needed for event '{event_type}'.")


                # Optional: Restock items if policy dictates
                # Be careful with restocking logic to avoid race conditions if multiple failure webhooks arrive

                logger.info(f"--- Successfully processed failure/expired webhook event '{event_type}' for Order {order_locked.id} within transaction ---")


            # --- OTHER/UNHANDLED EVENTS ---
            else:
                # This case handles success/failure events arriving when the order is NOT in a state to process them
                # (e.g., success event arrives for an already PAID order - handled by idempotency check earlier,
                # or an unknown event type arrives)
                 logger.info(f"Received event '{event_type}' for Order {order_locked.id} with status '{current_status_locked}'. No action taken within transaction.")

            # If we reach here, the relevant logic within the transaction block for the event completed (or it was unhandled/idempotent)
            logger.info(f"--- Committing Transaction for Order {order_id} ---")
            # Transaction automatically commits here if no exception was raised

        # --- Transaction Committed Successfully ---
        # Send final response to Xendit *after* transaction is done
        logger.info(f"Transaction for Order {order_id} committed. Sending HTTP 200 OK response.")
        return HttpResponse("Webhook processed successfully.", status=200)

    # --- Error Handling for Transaction Block ---
    except ValueError as ve: # Catch specific errors raised for rollback (e.g., stock issue, distribution fail)
        # Transaction automatically rolled back due to the exception
        logger.error(f"TRANSACTION ROLLED BACK for Order {order_id} due to ValueError: {ve}", exc_info=False)
        # Return 500 Internal Server Error - tells Xendit something went wrong on our end, potentially retry
        return HttpResponse(f"Internal processing error: {ve}", status=500)
    except Exception as e_atomic:
        # Catch any other unexpected errors within the atomic block
        # Transaction automatically rolled back
        logger.critical(f"CRITICAL ERROR inside atomic transaction block for Order {order_id}: {e_atomic}", exc_info=True)
        logger.critical(traceback.format_exc()) # Log full traceback
        # Return 500 Internal Server Error
        return HttpResponse("Internal Server Error during webhook processing.", status=500)

    # --- Error Handling for Code Outside Transaction Block ---
    except Exception as e:
        # Catch-all for unexpected errors *before* or *after* the atomic block attempt
        logger.critical(f"CRITICAL UNHANDLED error processing Xendit webhook (Order Ref: '{order_id}'): {e}", exc_info=True)
        logger.critical(traceback.format_exc()) # Log full traceback
        # Return 500 to signal Xendit to potentially retry (check their retry policy)
        return HttpResponse("Internal Server Error", status=500)


# --- Payment Callback View (No changes needed for Tasks 3-5) ---
def payment_callback_view(request, status):
    order_ref = request.GET.get('ref_id') # Get order ID from query param
    order = None
    logger.info(f"Received payment callback for status '{status}' with ref_id '{order_ref}'")

    if order_ref:
        try:
            # Use appropriate type casting if order_ref is UUID
            order = Order.objects.get(id=order_ref)
            logger.info(f"Found Order {order.id} for callback view. Status: {order.status}")
        except (Order.DoesNotExist, ValueError, TypeError):
            logger.warning(f"Order with ref_id '{order_ref}' not found or invalid format on '{status}' callback.")

    context = {'status': status, 'order': order} # Pass the order object if found
    template_name = 'payments/payment_status.html'

    if status == 'success':
        if order:
             if order.status == 'PAID':
                 messages.success(request, f"Payment confirmed for Order #{str(order.id)[:8]}!")
                 logger.info(f"Success callback for Order {order.id} (Already PAID). Redirecting to detail.")
             else:
                 # Status might still be PENDING if webhook hasn't arrived yet
                 messages.info(request, "Payment processing initiated. We are awaiting final confirmation from the payment provider.")
                 logger.info(f"Success callback for Order {order.id} (Status: {order.status}). Displaying pending message, awaiting webhook.")
             # Always redirect to order detail on success callback if order exists
             return redirect(reverse('orders:order_detail', kwargs={'order_id': order.id}))
        else:
             # Order not found, show generic success/pending page
             messages.info(request, "Payment processing initiated. We are awaiting final confirmation.")
             logger.warning(f"Success callback but Order '{order_ref}' not found. Showing generic status page.")
             return render(request, template_name, context)

    else: # failure or potentially cancelled/expired
        logger.warning(f"Failure/Cancel callback received for Order Ref '{order_ref}'.")
        messages.error(request, "Your payment failed, was cancelled, or could not be completed.")
        if order and order.status != 'FAILED':
             # If order exists but isn't marked FAILED yet by webhook/API, log discrepancy
             logger.warning(f"Failure callback for Order {order.id}, but status is '{order.status}'. Webhook might be delayed or API call didn't mark failed.")
        context['checkout_url'] = reverse('cart:checkout') # Link back to checkout
        return render(request, template_name, context)