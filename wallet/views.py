# wallet/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from decimal import Decimal
import logging
from types import SimpleNamespace # For mocking order object

from .models import Wallet, WalletTransaction
from .forms import WalletTopUpForm
# Import Xendit service - Ensure payments app is correctly installed/imported
try:
    from payments.services import create_xendit_payment_request
except ImportError:
    logger.critical("Could not import create_xendit_payment_request from payments.services")
    create_xendit_payment_request = None # Define as None to avoid NameError later

logger = logging.getLogger(__name__)

@login_required
def top_up_view(request):
    """Displays top-up form and initiates Xendit payment for wallet top-up."""
    wallet = get_object_or_404(Wallet, user=request.user) # Wallet should exist

    if request.method == 'POST':
        form = WalletTopUpForm(request.POST)
        if form.is_valid():
            amount_to_add = form.cleaned_data['amount']
            selected_xendit_channel = form.cleaned_data['xendit_channel']
            pending_tx = None # To store the reference to the pending transaction

            try:
                # 1. Create Pending Transaction Record (within its own transaction)
                with transaction.atomic():
                    pending_tx = WalletTransaction.objects.create(
                        wallet=wallet,
                        transaction_type='TOPUP_PENDING',
                        status='PENDING',
                        amount=amount_to_add,
                        description=f"Pending Top-Up via {dict(WalletTopUpForm.XENDIT_TOPUP_CHANNELS).get(selected_xendit_channel)}"
                    )
                    logger.info(f"Created PENDING WalletTransaction {pending_tx.id} for ₱{amount_to_add} by {request.user.email}")

                # 2. Initiate Xendit Payment (outside the DB transaction)
                if not create_xendit_payment_request:
                     raise ImportError("Xendit payment service not available.") # Fail clearly

                reference_id = str(pending_tx.id) # Use the pending transaction's UUID
                # Create a mock object mimicking essential Order fields for the service
                topup_order_mock = SimpleNamespace(
                    id=reference_id, # Critical: Pass Tx ID as reference
                    total_amount=amount_to_add,
                    currency='PHP',
                    country='PH',
                    buyer=request.user
                )
                # NOTE: Consider refactoring create_xendit_payment_request later
                # to accept amount/reference/description directly for non-order payments.

                xendit_response = create_xendit_payment_request(
                    order_or_mock=topup_order_mock, # Pass the mock structure
                    request=request,
                    selected_channel_key=selected_xendit_channel
                )

                response_status = xendit_response.get('status') # e.g., PENDING, REQUIRES_ACTION, FAILED
                response_type = xendit_response.get('type')     # e.g., REDIRECT, VIRTUAL_ACCOUNT, etc.

                # 3. Handle Xendit Response
                if response_status in ['PENDING', 'REQUIRES_ACTION']:
                    # Associate Xendit Request ID with pending transaction if available
                    xendit_request_id = xendit_response.get('xendit_request_id')
                    if xendit_request_id:
                         pending_tx.external_reference = xendit_request_id
                         pending_tx.save(update_fields=['external_reference'])

                    # Handle redirect or display information
                    if response_type == 'REDIRECT' and 'payment_url' in xendit_response:
                        payment_url = xendit_response['payment_url']
                        logger.info(f"Redirecting user for Wallet Top-Up {pending_tx.id} to {payment_url}")
                        # No cart to clear for top-up
                        messages.info(request, "Redirecting to payment page...")
                        return redirect(payment_url)
                    elif response_type == 'VIRTUAL_ACCOUNT':
                         logger.info(f"Displaying VA details for Top-Up {pending_tx.id}")
                         context = {'pending_tx': pending_tx, 'va_details': xendit_response.get('details')}
                         return render(request, 'wallet/top_up_va_details.html', context) # Create this
                    # Add elif for QR_CODE, OTC if needed/enabled for topup
                    else:
                        logger.warning(f"Top-Up {pending_tx.id} requires action but unknown type/no URL. Status: {response_status}")
                        messages.info(request, f"Your top-up is {response_status.lower()}. Follow provider instructions or check status later.")
                        return redirect('dashboard:dashboard')

                elif response_status == 'SUCCEEDED': # Immediate success (rare)
                     logger.warning(f"Top-Up {pending_tx.id} SUCCEEDED immediately via API. Webhook should confirm.")
                     messages.success(request, "Top-up initiated successfully! Funds may take a moment to reflect.")
                     return redirect('dashboard:dashboard')

                else: # FAILED or other unexpected status from Xendit service
                    error_message = xendit_response.get('error', 'Payment initiation failed.')
                    logger.error(f"Xendit top-up initiation FAILED for pending Tx {pending_tx.id}. Error: {error_message}")
                    # Mark pending transaction as failed
                    pending_tx.status = 'FAILED'
                    pending_tx.description += f" | Xendit Init Failed: {error_message[:100]}"
                    # Store Xendit request ID if available for debugging
                    xendit_request_id = xendit_response.get('xendit_request_id')
                    if xendit_request_id: pending_tx.external_reference = xendit_request_id
                    pending_tx.save(update_fields=['status', 'description', 'external_reference'])
                    messages.error(request, f"Could not initiate top-up: {error_message}")
                    return redirect('wallet:top_up')

            except Exception as e:
                logger.error(f"Error processing top-up POST for {request.user.email}: {e}", exc_info=True)
                messages.error(request, "An unexpected error occurred. Please try again.")
                # Mark pending transaction as failed if it was created before error
                if pending_tx and pending_tx.status == 'PENDING':
                     try:
                         pending_tx.status = 'FAILED'
                         pending_tx.description += " | Internal error during initiation."
                         pending_tx.save(update_fields=['status', 'description'])
                     except Exception as update_err:
                          logger.error(f"Failed to mark pending TX {pending_tx.id} as FAILED: {update_err}")
                # Go back to top up form
                return redirect('wallet:top_up')

        else: # Form is invalid
            messages.error(request, "Please correct the errors in the form below.")
            # Fall through to render the form with errors

    else: # GET request
        form = WalletTopUpForm()

    context = {
        'form': form,
        'wallet_balance': wallet.balance
    }
    return render(request, 'wallet/top_up.html', context)


# Placeholder view for VA details page (Create this template)
@login_required
def top_up_va_details_view(request):
     # This view isn't directly used if top_up_view renders the template
     # But useful if you redirect here with context
     # Retrieve details from session or query params if needed
     return render(request, 'wallet/top_up_va_details.html', {})