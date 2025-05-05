# payments/services.py

import uuid
import xendit
from xendit import Configuration
from xendit.apis import PaymentRequestApi
from xendit.exceptions import XenditSdkException, ApiValueError, ApiKeyError, ApiTypeError, ApiAttributeError, OpenApiException
from xendit.payment_request.model import (
    EWalletChannelCode, VirtualAccountChannelCode, OverTheCounterChannelCode,
    QRCodeChannelCode, PaymentRequestCurrency
)

# Import Order model correctly
from orders.models import Order
# Import WalletTransaction only for type checking or specific updates if needed later
from wallet.models import WalletTransaction
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.conf import settings
import logging
import json
from decimal import Decimal
from django.db import transaction

logger = logging.getLogger(__name__)
User = get_user_model()

# --- Helper: Build Redirect URL ---
def _build_callback_url(request, ref_id_str, status):
    """Builds the absolute callback URL with reference ID (UUID as string)."""
    # Ensure ref_id_str is actually a string before using it
    ref_id_str = str(ref_id_str)
    base_url = request.build_absolute_uri('/')[:-1]
    relative_url = reverse('payments:payment_callback', kwargs={'status': status})
    full_url = f"{base_url.rstrip('/')}/{relative_url.lstrip('/')}?ref_id={ref_id_str}"
    logger.debug(f"Built callback URL: {full_url}")
    return full_url

# --- Helper: Determine Payment Type ---
def _determine_payment_details(selected_channel_key):
    """Determines payment type, channel code, and derived channel from key."""
    payment_type_str, channel_code_str, derived_payment_channel = None, None, None
    parts = selected_channel_key.split('_', 1); method_prefix = parts[0]
    if method_prefix == 'EWALLET': payment_type_str='EWALLET'; channel_code_str=parts[1] if len(parts)>1 else None; derived_payment_channel=channel_code_str or payment_type_str
    elif method_prefix == 'VIRTUAL': parts_va=selected_channel_key.split('_',2); payment_type_str='VIRTUAL_ACCOUNT' if len(parts_va)==3 and parts_va[1]=='ACCOUNT' else None; channel_code_str=parts_va[2] if payment_type_str else None; derived_payment_channel=channel_code_str or payment_type_str
    elif method_prefix == 'OTC': payment_type_str='OVER_THE_COUNTER'; channel_code_str=parts[1] if len(parts)>1 else None; derived_payment_channel=channel_code_str or payment_type_str
    elif method_prefix == 'QR': parts_qr=selected_channel_key.split('_',2); payment_type_str='QR_CODE' if len(parts_qr)==3 and parts_qr[1]=='CODE' else None; channel_code_str=parts_qr[2] if payment_type_str else None; derived_payment_channel=channel_code_str or payment_type_str
    elif method_prefix == 'CARD': payment_type_str='CARD'; channel_code_str=None; derived_payment_channel=payment_type_str
    elif method_prefix == 'DIRECT': parts_dd=selected_channel_key.split('_',2); payment_type_str='DIRECT_DEBIT' if len(parts_dd)==3 and parts_dd[1]=='DEBIT' else None; channel_code_str=parts_dd[2] if payment_type_str else None; derived_payment_channel=channel_code_str or payment_type_str
    logger.debug(f"Determined Payment Details: Type={payment_type_str}, Code={channel_code_str}, Derived={derived_payment_channel}")
    return payment_type_str, channel_code_str, derived_payment_channel

# --- Helper: Build Payment Method Payload ---
def _build_payment_method_payload(payment_type_str, channel_code_str, currency_code, amount, buyer_name, success_redirect_url, failure_redirect_url):
    """Builds the 'payment_method' part of the Xendit payload."""
    payload = {'type': payment_type_str, 'reusability': 'ONE_TIME_USE'}
    if payment_type_str == 'EWALLET':
        if not channel_code_str: raise ValueError('EWallet code missing.')
        try: EWalletChannelCode(channel_code_str)
        except ValueError as e: raise ValueError(f'Invalid EWallet code: {channel_code_str}') from e
        payload['ewallet'] = {'channel_code': channel_code_str, 'channel_properties': {'success_return_url': success_redirect_url, 'failure_return_url': failure_redirect_url}}
    elif payment_type_str == 'VIRTUAL_ACCOUNT':
        if not channel_code_str: raise ValueError('VA code missing.')
        try: VirtualAccountChannelCode(channel_code_str)
        except ValueError as e: raise ValueError(f'Invalid VA code: {channel_code_str}') from e
        payload['virtual_account'] = {'channel_code': channel_code_str, 'channel_properties': {'customer_name': buyer_name}}
    elif payment_type_str == 'OVER_THE_COUNTER':
        if not channel_code_str: raise ValueError('OTC code missing.')
        try: OverTheCounterChannelCode(channel_code_str)
        except ValueError as e: raise ValueError(f'Invalid OTC code: {channel_code_str}') from e
        payload['over_the_counter'] = {'channel_code': channel_code_str, 'currency': currency_code, 'amount': float(amount), 'channel_properties': {'customer_name': buyer_name}}
    elif payment_type_str == 'QR_CODE':
        if not channel_code_str: raise ValueError('QR code missing.')
        try: QRCodeChannelCode(channel_code_str)
        except ValueError as e: raise ValueError(f'Invalid QR code: {channel_code_str}') from e
        payload['qr_code'] = {'channel_code': channel_code_str, 'currency': currency_code}
    # Add CARD, DIRECT_DEBIT etc. if needed
    return payload

# --- Helper: Build Main Xendit Payload ---
def _build_main_payload(currency_enum, amount, reference_id, country_code, payment_method_payload, buyer_email_str, context_type, description, success_redirect_url, failure_redirect_url, payment_type_str):
    """Builds the main payload dictionary for the Xendit API call."""
    payload = {
        'currency': currency_enum, 'amount': float(amount), 'reference_id': reference_id,
        'country': country_code, 'payment_method': payment_method_payload,
        'metadata': {'reference_id': reference_id, 'user_email': buyer_email_str or 'N/A', 'context': context_type},
        'description': description,
    }
    if payment_type_str in ['CARD', 'EWALLET']:
         payload['channel_properties'] = {'success_return_url': success_redirect_url, 'failure_return_url': failure_redirect_url}
    return payload

# --- Helper: Process Xendit API Response ---
def _process_xendit_response(api_response_dict, reference_id):
    """Processes the successful API response dictionary and structures frontend response."""
    response_status = api_response_dict.get('status')
    xendit_request_id = api_response_dict.get('id')
    structured_response = {'xendit_request_id': xendit_request_id, 'status': response_status}
    actions = api_response_dict.get('actions', [])
    pm_details = api_response_dict.get('payment_method', {})
    pm_type = pm_details.get('type')

    if response_status in ['PENDING', 'REQUIRES_ACTION']:
        redirect_url = next((a.get('url') for a in actions if a.get('url')), None)
        if redirect_url:
            structured_response['type'] = 'REDIRECT'; structured_response['payment_url'] = redirect_url
            logger.info(f"{reference_id} requires REDIRECT.")
        else: # Handle non-redirect display types
             if pm_type == 'VIRTUAL_ACCOUNT':
                 va_info = pm_details.get('virtual_account',{}); structured_response['type']='VIRTUAL_ACCOUNT'
                 structured_response['details']={'channel_code':va_info.get('channel_code'),'account_number':va_info.get('account_number'),'name':va_info.get('channel_properties',{}).get('customer_name'),'amount':api_response_dict.get('amount'),'currency':api_response_dict.get('currency'),'expires_at':va_info.get('channel_properties',{}).get('expires_at')}
                 logger.info(f"{reference_id} requires VA display.")
             elif pm_type == 'QR_CODE':
                 qr_info=pm_details.get('qr_code',{}); qr_str=qr_info.get('channel_properties',{}).get('qr_string')
                 structured_response['type']='QR_CODE' if qr_str else 'UNKNOWN_PENDING'; structured_response['qr_string']=qr_str; structured_response['details']=qr_info; logger.info(f"{reference_id} requires QR display.")
             elif pm_type == 'OVER_THE_COUNTER':
                 otc_info=pm_details.get('over_the_counter',{}); structured_response['type']='OTC'
                 structured_response['details']={'channel_code':otc_info.get('channel_code'), 'payment_code':otc_info.get('channel_properties',{}).get('payment_code'),'expires_at':otc_info.get('channel_properties',{}).get('expires_at'), 'amount':otc_info.get('amount'),'currency':otc_info.get('currency'), 'customer_name':otc_info.get('channel_properties',{}).get('customer_name')}
                 logger.info(f"{reference_id} requires OTC display.")
             else: structured_response['type'] = 'UNKNOWN_PENDING'; logger.warning(f"Unhandled PENDING/REQUIRES_ACTION state for {reference_id}")
    elif response_status == 'SUCCEEDED': structured_response['type'] = 'DIRECT_SUCCESS'; logger.info(f"{reference_id} SUCCEEDED immediately.")
    elif response_status == 'FAILED': structured_response['error'] = f"Payment request failed ({api_response_dict.get('failure_code','UNKNOWN')})"; logger.error(f"Xendit request FAILED for {reference_id}.")
    else: structured_response['type'] = 'UNEXPECTED_STATUS'; structured_response['error'] = f'Unexpected status: {response_status}'; logger.warning(f"Unexpected Xendit status '{response_status}'")

    return structured_response

# --- Helper: Handle API/Library Errors ---
def _handle_payment_request_error(error, reference_id, order_or_mock):
    """Logs error and updates DB status if possible."""
    is_real_order = isinstance(order_or_mock, Order)
    error_detail = "An unexpected error occurred."
    raw_error_body = None
    failure_reason_code = "UNKNOWN_ERROR"

    if isinstance(error, XenditSdkException):
        logger.error(f"Xendit API Exc for {reference_id}: {error.status} {error.errorCode} {error.errorMessage}", exc_info=False)
        error_detail = f"Gateway Error ({error.status} {error.errorCode})" #: {error.errorMessage[:100]}" # Keep user msg short
        raw_error_body = error.rawResponse
        failure_reason_code = f"API Error: {error.errorCode}"
    elif isinstance(error, (ApiValueError, ApiKeyError, ApiTypeError, ApiAttributeError, OpenApiException)):
        logger.error(f"Xendit Lib Error for {reference_id}: {error}", exc_info=True)
        error_detail = 'Internal payment library error.'
        failure_reason_code = f"Lib Error: {type(error).__name__}"
    else: # General Exception
        logger.error(f"General error in Xendit request for {reference_id}: {error}", exc_info=True)
        error_detail = 'Internal server error during payment processing.'
        failure_reason_code = "Internal Server Error"

    # Attempt to mark appropriate object as FAILED
    try:
        with transaction.atomic(): # Ensure status update is atomic
            if is_real_order:
                o=Order.objects.select_for_update().get(id=order_or_mock.id)
                if o.status != 'FAILED': o.status='FAILED'; o.failure_reason=failure_reason_code[:255]; o.save(update_fields=['status','failure_reason'])
            else: # Wallet Transaction
                # Use try-except for WT lookup as ref_id might be invalid format here if initial validation failed
                try:
                    wt_uuid = uuid.UUID(hex=reference_id) # Validate before lookup
                    wt=WalletTransaction.objects.select_for_update().get(id=wt_uuid, status='PENDING')
                    wt.status='FAILED'; wt.description += f" | Failed: {failure_reason_code[:50]}"; wt.save(update_fields=['status','description'])
                except (WalletTransaction.DoesNotExist, ValueError):
                    logger.warning(f"Could not find PENDING WT with ID {reference_id} to mark as failed.")
                except Exception as wt_update_e:
                     logger.error(f"Failed to mark WT {reference_id} as FAILED: {wt_update_e}")
    except Exception as db_err:
        logger.error(f"DB error while trying to mark object {reference_id} as FAILED: {db_err}")

    return {'status': 'FAILED', 'error': error_detail, 'raw_error': raw_error_body}


# --- Main Service Function (Refactored) ---
def create_xendit_payment_request(order_or_mock, request, selected_channel_key: str):
    # 1. Extract and Validate Input
    try:
        reference_id = str(getattr(order_or_mock, 'id'))
        amount = Decimal(getattr(order_or_mock, 'total_amount'))
        buyer = getattr(order_or_mock, 'buyer')
        currency_code = getattr(order_or_mock, 'currency', 'PHP')
        country_code = getattr(order_or_mock, 'country', 'PH')
        is_real_order = isinstance(order_or_mock, Order)
        context_type = 'Order' if is_real_order else 'WalletTopUp'
        if not all([reference_id, isinstance(amount, Decimal), amount > 0, isinstance(buyer, User)]): raise ValueError("Missing required data")
    except Exception as e: return _handle_payment_request_error(e, getattr(order_or_mock,'id','N/A'), order_or_mock)

    logger.info(f"--- Initiating Xendit Request for Ref ID {reference_id} (Context: {context_type}) ---")

    # 2. Initialize Xendit Client
    api_key = settings.XENDIT_SECRET_API_KEY
    if not api_key: logger.critical("XENDIT_SECRET_API_KEY not set."); return {'status': 'FAILED', 'error': 'Payment system config error.'}
    try: configuration = Configuration(api_key=api_key); api_client = xendit.ApiClient(configuration=configuration); api_instance = PaymentRequestApi(api_client)
    except Exception as e: return _handle_payment_request_error(e, reference_id, order_or_mock)

    try:
        # 3. Determine Payment Details
        payment_type_str, channel_code_str, derived_payment_channel = _determine_payment_details(selected_channel_key)
        if not payment_type_str: return {'status': 'FAILED', 'error': 'Invalid payment channel key.'}

        # 4. Save Payment Channel (Order Only)
        if is_real_order:
            try: # Nested transaction OK
                with transaction.atomic(): o=Order.objects.select_for_update().get(id=order_or_mock.id); o.payment_channel=derived_payment_channel; o.save(update_fields=['payment_channel']); logger.info(f"Saved channel to Order {order_or_mock.id}")
            except Exception as e: logger.error(f"DB error saving channel: {e}"); return {'status': 'FAILED', 'error': 'DB error saving channel.'}
        else: logger.info(f"Skipping Order.payment_channel update for non-Order reference: {reference_id}")

        # 5. Build Payloads
        currency_enum = PaymentRequestCurrency(currency_code)
        success_url = _build_callback_url(request, reference_id, 'success')
        failure_url = _build_callback_url(request, reference_id, 'failure')
        buyer_name = f"{getattr(buyer, 'first_name', '') or ''} {getattr(buyer, 'last_name', '') or ''}".strip() or getattr(buyer, 'email', 'Unknown')
        buyer_email = getattr(buyer, 'email', None)
        description = f"Ref #{reference_id[:8]}" if context_type != 'Order' else f"Order #{reference_id[:8]}"

        payment_method_payload = _build_payment_method_payload(payment_type_str, channel_code_str, currency_code, amount, buyer_name, success_url, failure_url)
        main_payload = _build_main_payload(currency_enum, amount, reference_id, country_code, payment_method_payload, buyer_email, context_type, description, success_url, failure_url, payment_type_str)

        # 6. API Call
        logger.info(f"Sending Xendit CreatePaymentRequest for {reference_id}")
        api_response = api_instance.create_payment_request(payment_request_parameters=main_payload)
        api_response_dict = api_response.to_dict()
        logger.info(f"Xendit API success for {reference_id}. Status: {api_response_dict.get('status')}")

        # 7. Save Xendit Request ID (if applicable)
        xendit_request_id = api_response_dict.get('id')
        if xendit_request_id:
            if is_real_order:
                try: # Nested transaction OK
                    with transaction.atomic(): o=Order.objects.select_for_update().get(id=order_or_mock.id); o.xendit_payment_request_id = xendit_request_id; o.save(update_fields=['xendit_payment_request_id']); logger.info(f"Saved req ID to Order {order_or_mock.id}")
                except Exception as e: logger.error(f"Failed save req ID to Order {order_or_mock.id}: {e}")
            else: # Save to WalletTransaction external_reference
                 try: wt=WalletTransaction.objects.get(id=reference_id); wt.external_reference=xendit_request_id; wt.save(update_fields=['external_reference']); logger.info(f"Saved req ID to WT {reference_id}")
                 except Exception as e: logger.error(f"Failed save req ID to WT {reference_id}: {e}") # Log error but don't fail request
        else: logger.warning(f"Xendit response missing Request ID for {reference_id}.")

        # 8. Process & Structure Response
        return _process_xendit_response(api_response_dict, reference_id)

    # 9. Handle Errors during processing/API call
    except Exception as e:
        # Pass the original object back for context in error handling
        return _handle_payment_request_error(e, reference_id, order_or_mock)