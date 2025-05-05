# payments/views.py

from django.shortcuts import render, HttpResponse, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.db import transaction, models
from django.contrib import messages
from django.conf import settings
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site # For seller email URLs
import json
import logging
import traceback
import uuid
from collections import defaultdict

# Brevo SDK Imports (keep if using API directly later, not needed for current SMTP via send_mail)
# import sib_api_v3_sdk
# from sib_api_v3_sdk.rest import ApiException

# Models
from orders.models import Order, Product, OrderItem
from wallet.models import Wallet, WalletTransaction, add_funds # Import add_funds

# Other App Views/Functions (ensure correct import path)
from cart.views import distribute_payment, initialize_cart # Assuming these are still correct

# Seller Notification Helper (keep from previous step)
from .utils import send_seller_sale_notification # Assume moved helper here

logger = logging.getLogger(__name__)

# --- Webhook Verification (Keep as is) ---
def verify_xendit_webhook(request):
    logger.debug(f"Webhook Headers: {request.headers}")
    callback_token = request.headers.get('x-callback-token')
    expected_token = getattr(settings, 'XENDIT_CALLBACK_VERIFICATION_TOKEN', None)
    if not expected_token:
        logger.critical("CRITICAL: XENDIT_CALLBACK_VERIFICATION_TOKEN not set! Verification BYPASSED.")
        return True # DEVELOPMENT ONLY
    if not callback_token:
        logger.error("Webhook verification failed: Missing 'x-callback-token'.")
        return False
    if callback_token != expected_token:
        logger.error(f"Webhook verification failed: Invalid token.")
        return False
    logger.info("Xendit callback token verified successfully.")
    return True

# --- Helper Functions for Webhook Logic ---

def _parse_and_verify(request):
    """Parses request body, verifies webhook signature."""
    logger.info("--- Received Xendit Webhook Request ---")
    try:
        raw_body = request.body.decode('utf-8')
        logger.debug(f"Raw Webhook Body:\n{raw_body[:1000]}...")
        payload = json.loads(raw_body)
        logger.debug(f"Parsed Webhook Payload:\n{json.dumps(payload, indent=2)}")
    except Exception as e:
        logger.error(f"Error decoding request body or parsing JSON: {e}", exc_info=True)
        return None, HttpResponse("Invalid request body or JSON data.", status=400)

    if not verify_xendit_webhook(request):
        return None, HttpResponse("Webhook verification failed.", status=403)

    return payload, None # Return payload if successful, no error response

def _extract_data_and_ids(payload):
    """Extracts event, data, Xendit ID, and validates/finds reference UUID."""
    event_type = payload.get('event')
    data = payload.get('data')
    logger.info(f"Webhook Event Type: '{event_type}'")

    if not data:
        logger.error("Webhook payload missing 'data' field.")
        return None, None, None, None # event_type, reference_uuid, xendit_payment_id, data

    xendit_payment_id = data.get('id') # Xendit's own object ID
    logger.info(f"Xendit Object ID ('data.id'): {xendit_payment_id}")

    reference_uuid = None
    possible_id_fields = ['reference_id', 'payment_request_id', 'external_id']

    for field in possible_id_fields:
        potential_id = data.get(field)
        if potential_id:
            logger.info(f"Potential Reference ID found in field '{field}': {potential_id}")
            try:
                reference_uuid = uuid.UUID(hex=potential_id)
                logger.info(f"Validated '{potential_id}' as UUID: {reference_uuid}.")
                break # Use the first valid UUID found
            except ValueError:
                logger.warning(f"Value '{potential_id}' in field '{field}' is not a valid UUID.")
                # Continue loop

    if reference_uuid is None:
        logger.error(f"Webhook payload did not contain a valid UUID in expected fields.")
        return event_type, None, xendit_payment_id, data # Return None for reference_uuid

    return event_type, reference_uuid, xendit_payment_id, data

def _get_webhook_target(reference_uuid):
    """Finds Order or pending WalletTransaction matching the UUID."""
    if not isinstance(reference_uuid, uuid.UUID):
        logger.error(f"Invalid type passed to _get_webhook_target: {type(reference_uuid)}")
        return None, None

    try:
        target_object = Order.objects.get(id=reference_uuid)
        return target_object, 'Order'
    except Order.DoesNotExist:
        logger.info(f"No Order found with ID {reference_uuid}. Checking WalletTransaction.")
        try:
            target_object = WalletTransaction.objects.get(id=reference_uuid, status='PENDING')
            return target_object, 'WalletTransaction'
        except WalletTransaction.DoesNotExist:
            logger.error(f"No Order or PENDING WalletTransaction found for UUID '{reference_uuid}'.")
            return None, None
    except Exception as e: # Catch other potential errors
        logger.error(f"Error retrieving object for UUID {reference_uuid}: {e}", exc_info=True)
        return None, None

def _handle_order_success(order_locked, xendit_payment_id, request):
    """Processes a successful Order payment within a transaction."""
    logger.info(f"--- Processing SUCCESS for Order {order_locked.id} ---")
    order_items_qs = OrderItem.objects.filter(order=order_locked).select_related('product', 'seller')
    seller_items_map = defaultdict(list)
    products_to_check = []

    # Prepare seller notification data and product list for stock check
    for item in order_items_qs:
        if item.seller:
            seller_items_map[item.seller.email].append({
                'product_title': item.product.title if item.product else '(Deleted Product)',
                'quantity': item.quantity, 'price': item.price, 'subtotal': item.subtotal
            })
        if item.product:
             products_to_check.append(item.product.id)

    # 1. Update Order Status & Payment ID
    order_locked.status = 'PAID'
    update_fields = ['status']
    if xendit_payment_id: order_locked.xendit_payment_id = xendit_payment_id; update_fields.append('xendit_payment_id')
    if order_locked.failure_reason: order_locked.failure_reason = None; update_fields.append('failure_reason')
    order_locked.save(update_fields=update_fields)
    logger.info(f"Order {order_locked.id} status updated to PAID.")

    # 2. Deduct Stock
    logger.info(f"--- Order {order_locked.id}: Stock Deduction ---")
    for item in order_items_qs:
        prod = item.product
        if not prod: continue
        updated = Product.objects.filter(id=prod.id, quantity__gte=item.quantity).update(quantity=models.F('quantity') - item.quantity)
        if updated == 0: raise ValueError(f"Stock fail/concurrent mod Prod {prod.id}")
        logger.info(f"Stock deducted for Product {prod.id}.")

    # 3. Update is_sold Status
    logger.info(f"--- Order {order_locked.id}: is_sold Check ---")
    if products_to_check:
        for p in Product.objects.filter(id__in=products_to_check):
            if p.quantity <= 0 and not p.is_sold: p.is_sold=True; p.save(update_fields=['is_sold']); logger.info(f"Marked Product {p.id} sold.")

    # 4. Distribute Funds
    logger.info(f"--- Order {order_locked.id}: Distribute Payment ---")
    distribute_payment(order_locked) # Assumes this raises Exception on failure

    # 5. Clear Buyer's Cart
    logger.info(f"--- Order {order_locked.id}: Clear Cart ---")
    if order_locked.buyer:
        try: cart=initialize_cart(order_locked.buyer); count, _ = cart.cart_items.all().delete(); logger.info(f"Cleared {count} cart items.")
        except Exception as cart_e: logger.error(f"Non-critical cart clear error: {cart_e}")

    # 6. Send Seller Notifications (Outside main transaction potentially better, but here for now)
    logger.info(f"--- Order {order_locked.id}: Send Seller Notifications ---")
    email_failures = 0
    buyer_info = order_locked.buyer.email if order_locked.buyer else "N/A"
    for seller_email, items_list in seller_items_map.items():
        if not seller_email: continue
        sent = send_seller_sale_notification(order_locked, seller_email, items_list, buyer_info, request)
        if not sent: email_failures += 1
    if email_failures > 0: logger.warning(f"{email_failures} seller emails failed for Order {order_locked.id}")

    logger.info(f"--- Order {order_locked.id}: Success processing complete ---")

def _handle_topup_success(pending_tx_locked, xendit_payment_id):
    """Processes a successful Wallet Top-Up within a transaction."""
    logger.info(f"--- Processing SUCCESS for Wallet Top-Up Tx {pending_tx_locked.id} ---")
    wallet_user = pending_tx_locked.wallet.user
    amount = pending_tx_locked.amount

    # 1. Add Funds (creates final 'DEPOSIT' transaction)
    try:
        add_funds(
            user=wallet_user, amount=amount, transaction_type='DEPOSIT',
            description=f"Completed Top-Up ref {str(pending_tx_locked.id)[:8]}", # Simpler desc
            external_reference=xendit_payment_id
        )
    except Exception as add_fund_e:
        # Critical error - log intensely and mark pending TX as failed
        logger.critical(f"CRITICAL: add_funds FAILED for confirmed Top-Up Tx {pending_tx_locked.id}. Xendit Pymt: {xendit_payment_id}. Error: {add_fund_e}", exc_info=True)
        pending_tx_locked.status = 'FAILED' # Or 'MANUAL_REVIEW'
        pending_tx_locked.description += f" | CRITICAL: add_funds failed: {str(add_fund_e)[:100]}"
        pending_tx_locked.external_reference = xendit_payment_id
        pending_tx_locked.save(update_fields=['status', 'description', 'external_reference'])
        # Avoid raising error here to commit the FAILED status, needs manual fix!
        # We might want to add a notification system for admins here.
        return # Stop processing this webhook further

    # 2. Mark original PENDING transaction as COMPLETED
    pending_tx_locked.status = 'COMPLETED'
    pending_tx_locked.external_reference = xendit_payment_id
    pending_tx_locked.save(update_fields=['status', 'external_reference'])
    logger.info(f"Wallet Top-Up Tx {pending_tx_locked.id} marked COMPLETED.")
    logger.info(f"--- Wallet Top-Up Tx {pending_tx_locked.id}: Success processing complete ---")

def _handle_failure_event(locked_object, object_type, data, event_type):
    """Handles a failure/expired event for Order or WalletTransaction within a transaction."""
    logger.info(f"--- Processing FAILURE/EXPIRED event '{event_type}' for {object_type} {locked_object.id} ---")
    locked_object.status = 'FAILED'
    failure_code = data.get('failure_code')
    failure_reason_payload = data.get('failure_reason')
    reason = failure_code or failure_reason_payload or f"Expired/Failed: {event_type}"

    update_fields = ['status']
    if object_type == 'Order':
        locked_object.failure_reason = str(reason)[:255]
        update_fields.append('failure_reason')
    elif object_type == 'WalletTransaction':
        locked_object.description += f" | Failed: {reason[:100]}"
        update_fields.append('description')

    # Store Xendit payment ID if available, useful for debugging failures
    xendit_payment_id = data.get('id')
    if xendit_payment_id and hasattr(locked_object, 'external_reference'): # Check if field exists
         locked_object.external_reference = xendit_payment_id
         update_fields.append('external_reference')
    elif xendit_payment_id and hasattr(locked_object, 'xendit_payment_id'):
         locked_object.xendit_payment_id = xendit_payment_id
         update_fields.append('xendit_payment_id')


    locked_object.save(update_fields=list(set(update_fields))) # Use set to avoid duplicates
    logger.info(f"{object_type} {locked_object.id} status updated to FAILED. Reason: '{reason}'")
    logger.info(f"--- {object_type} {locked_object.id}: Failure processing complete ---")


# --- Refactored Webhook Handler ---
@csrf_exempt
@require_POST
def xendit_webhook(request):
    # 1. Parse and Verify
    payload, error_response = _parse_and_verify(request)
    if error_response:
        return error_response

    # 2. Extract Data and Validate Reference ID
    event_type, reference_uuid, xendit_payment_id, data = _extract_data_and_ids(payload)
    if data is None: # Handle case where data field itself was missing
        return HttpResponse("Payload missing data field.", status=400)
    if reference_uuid is None:
        return HttpResponse("Missing or invalid reference UUID.", status=200) # Acknowledge OK

    # 3. Get Target Object (Order or WalletTransaction)
    target_object, object_type = _get_webhook_target(reference_uuid)
    if target_object is None:
        # Error already logged in helper
        return HttpResponse("Matching Order or Pending Transaction not found.", status=200) # Acknowledge OK

    # 4. Idempotency & State Checks (before transaction)
    is_success_event = event_type in ['payment.succeeded', 'payment_request.succeeded', 'invoice.paid', 'capture.succeeded']
    is_failure_event = event_type in ['payment.failed', 'payment_request.failed', 'invoice.expired', 'capture.failed']
    current_status = target_object.status

    if is_success_event and current_status in ['PAID', 'COMPLETED']:
        logger.info(f"Idempotency: {object_type} {target_object.id} already {current_status}. Ignoring '{event_type}'.")
        return HttpResponse(f"Webhook acknowledged (Already {current_status})", status=200)
    if is_failure_event and current_status == 'FAILED':
        logger.info(f"Idempotency: {object_type} {target_object.id} already FAILED. Ignoring '{event_type}'.")
        return HttpResponse("Webhook acknowledged (Already FAILED)", status=200)
    if current_status != 'PENDING':
        logger.warning(f"State Check: Received '{event_type}' for {object_type} {target_object.id}, but status is '{current_status}'. Ignoring.")
        return HttpResponse("Webhook acknowledged (Not PENDING)", status=200)

    # 5. Process within Transaction
    try:
        with transaction.atomic():
            logger.info(f"--- Starting Atomic Transaction for {object_type} {target_object.id} ---")
            # Lock the specific object
            if object_type == 'Order':
                locked_object = Order.objects.select_for_update().get(id=target_object.id)
            elif object_type == 'WalletTransaction':
                locked_object = WalletTransaction.objects.select_for_update().get(id=target_object.id)
            else: raise RuntimeError("Invalid object_type.") # Should not happen

            logger.info(f"Locked {object_type} {locked_object.id}. Verifying status...")
            current_status_locked = locked_object.status

            # Final Idempotency/State check after lock
            if is_success_event and current_status_locked in ['PAID', 'COMPLETED']:
                 logger.info(f"Idempotency (lock): {object_type} {locked_object.id} already {current_status_locked}. Ignoring."); return HttpResponse(f"Ack (Already {current_status_locked})", status=200)
            if is_failure_event and current_status_locked == 'FAILED':
                 logger.info(f"Idempotency (lock): {object_type} {locked_object.id} already FAILED. Ignoring."); return HttpResponse("Ack (Already FAILED)", status=200)
            if current_status_locked != 'PENDING':
                 logger.warning(f"Race Condition: {object_type} {locked_object.id} status '{current_status_locked}'. Aborting."); return HttpResponse("Ack (Status changed)", status=200)

            logger.info(f"{object_type} {locked_object.id} status 'PENDING' OK for '{event_type}'.")

            # --- Call appropriate handler ---
            if is_success_event:
                if object_type == 'Order':
                    _handle_order_success(locked_object, xendit_payment_id, request) # Pass request for email URLs
                elif object_type == 'WalletTransaction':
                    _handle_topup_success(locked_object, xendit_payment_id)
            elif is_failure_event:
                _handle_failure_event(locked_object, object_type, data, event_type)
            else:
                logger.info(f"Event '{event_type}' requires no action for {object_type} {locked_object.id}.")

            logger.info(f"--- Committing Transaction for {object_type} {locked_object.id} ---")
            # Transaction commits here if no exception raised in handlers

        # --- Transaction Committed Successfully ---
        logger.info(f"Transaction for {object_type} {target_object.id} committed. Sending HTTP 200 OK.")
        return HttpResponse("Webhook processed successfully.", status=200)

    # --- Error Handling for Transaction Block ---
    except ValueError as ve: # Specific errors raised by handlers (stock, distribution, etc.)
        logger.error(f"TRANSACTION ROLLED BACK for {object_type} {target_object.id} due to ValueError: {ve}", exc_info=False)
        return HttpResponse(f"Internal processing error: {ve}", status=500) # Use 500 to signal retry might be needed
    except Exception as e_atomic:
        logger.critical(f"CRITICAL ERROR inside atomic transaction for {object_type} {target_object.id}: {e_atomic}", exc_info=True)
        logger.critical(traceback.format_exc())
        return HttpResponse("Internal Server Error during webhook processing.", status=500) # Use 500

    # --- Error Handling for Code Outside Transaction Block ---
    except Exception as e:
        logger.critical(f"CRITICAL UNHANDLED error processing webhook (Ref UUID: '{reference_uuid}'): {e}", exc_info=True)
        logger.critical(traceback.format_exc())
        return HttpResponse("Internal Server Error", status=500)


# --- Payment Callback View (No changes needed) ---
def payment_callback_view(request, status):
    order_ref = request.GET.get('ref_id')
    target_object = None
    object_type = None
    logger.info(f"Received payment callback for status '{status}' with ref_id '{order_ref}'")

    if order_ref:
        try:
            ref_uuid = uuid.UUID(hex=order_ref)
            # Check Order first, then maybe WalletTransaction if needed for callbacks
            try:
                 target_object = Order.objects.get(id=ref_uuid)
                 object_type = 'Order'
                 logger.info(f"Found Order {target_object.id} for callback view.")
            except Order.DoesNotExist:
                 try:
                     # Check if it was a Wallet TX ID - might need different handling on status page
                     target_object = WalletTransaction.objects.get(id=ref_uuid)
                     object_type = 'WalletTransaction'
                     logger.info(f"Found WalletTransaction {target_object.id} for callback view.")
                 except WalletTransaction.DoesNotExist:
                      logger.warning(f"No Order or WalletTransaction found for ref_id '{order_ref}'")
        except (ValueError, TypeError):
            logger.warning(f"Invalid UUID format for ref_id '{order_ref}' on callback.")

    # Pass object to context, might need specific handling in template based on type
    context = {'status': status, 'target_object': target_object, 'object_type': object_type}
    template_name = 'payments/payment_status.html' # May need adjustments for top-ups

    if status == 'success':
        if target_object and object_type == 'Order':
             if target_object.status == 'PAID':
                 messages.success(request, f"Payment confirmed for Order #{str(target_object.id)[:8]}!")
             else:
                 messages.info(request, "Payment processing initiated. Final status pending.")
             return redirect(reverse('orders:order_detail', kwargs={'order_id': target_object.id}))
        elif target_object and object_type == 'WalletTransaction':
             messages.success(request, f"Wallet Top-Up of {target_object.amount} initiated. Funds will be added shortly.")
             return redirect('dashboard:dashboard') # Redirect to dashboard for top-ups
        else: # No object found or invalid ref_id
             messages.info(request, "Payment processing initiated.")
             return render(request, template_name, context) # Show generic page

    else: # failure
        logger.warning(f"Failure/Cancel callback received for Ref '{order_ref}'.")
        messages.error(request, "Your payment failed, was cancelled, or could not be completed.")
        # Optionally add specific message if it was a failed top-up
        if target_object and object_type == 'WalletTransaction':
             messages.warning(request, "Your wallet top-up could not be completed.")
        context['checkout_url'] = reverse('cart:checkout')
        # Decide where to redirect on failure - maybe back to cart or dashboard?
        return render(request, template_name, context)