# payments/services.py

import xendit
from xendit import Configuration # <<< Import Configuration
from xendit.apis import PaymentRequestApi
# Only import Enums that are actually *needed* for instantiation, not for payload dict keys
import xendit.exceptions
from xendit.payment_request.model import (
    EWalletChannelCode,
    VirtualAccountChannelCode,
    OverTheCounterChannelCode,
    QRCodeChannelCode,
    PaymentRequestCurrency
    # We pass PaymentMethodType as string in the payload dict
)
# We pass PaymentMethodReusability as string in the payload dict

from orders.models import Order
from django.urls import reverse
from django.conf import settings # <<< Import Django settings
import logging
import json
from decimal import Decimal
from django.db import transaction
logger = logging.getLogger(__name__)

# --- Helper Function to Build Redirect URLs ---
def _build_callback_url(request, order_id, status):
    """Builds the absolute callback URL with order ID."""
    base_url = request.build_absolute_uri('/')[:-1] # Get http(s)://domain
    relative_url = reverse('payments:payment_callback', kwargs={'status': status})
    full_url = f"{base_url.rstrip('/')}/{relative_url.lstrip('/')}?ref_id={order_id}"
    logger.debug(f"Built callback URL: {full_url}")
    return full_url

# --- Main Service Function ---
def create_xendit_payment_request(order: Order, request, selected_channel_key: str):
    """
    Creates a payment request with Xendit using dictionary payloads.
    """
    # --- 1. Initialize Xendit Client with API Key ---
    api_key = settings.XENDIT_SECRET_API_KEY
    if not api_key:
        logger.critical("XENDIT_SECRET_API_KEY is not set in Django settings.")
        return {'status': 'FAILED', 'error': 'Payment system configuration error.'}

    try:
        # *** FIX: Explicitly configure the client ***
        configuration = Configuration(api_key=api_key)
        api_client = xendit.ApiClient(configuration=configuration) # Pass configuration
        api_instance = PaymentRequestApi(api_client)
    except Exception as config_e:
        logger.critical(f"Failed to initialize Xendit API client: {config_e}", exc_info=True)
        return {'status': 'FAILED', 'error': 'Payment system configuration error.'}


    # --- 2. Determine Payment Type and Channel Code from Key ---
    payment_type_str = None
    channel_code_str = None
    parts = selected_channel_key.split('_', 1)
    method_prefix = parts[0]
    if method_prefix == 'EWALLET':
        payment_type_str = 'EWALLET'
        if len(parts) > 1: channel_code_str = parts[1]
    elif method_prefix == 'VIRTUAL':
        parts_va = selected_channel_key.split('_', 2)
        if len(parts_va) == 3 and parts_va[0] == 'VIRTUAL' and parts_va[1] == 'ACCOUNT':
            payment_type_str = 'VIRTUAL_ACCOUNT'
            channel_code_str = parts_va[2]
    elif method_prefix == 'OTC':
        payment_type_str = 'OVER_THE_COUNTER'
        if len(parts) > 1: channel_code_str = parts[1]
    elif method_prefix == 'QR':
         parts_qr = selected_channel_key.split('_', 2)
         if len(parts_qr) == 3 and parts_qr[0] == 'QR' and parts_qr[1] == 'CODE':
            payment_type_str = 'QR_CODE'
            channel_code_str = parts_qr[2]
    elif method_prefix == 'CARD':
        payment_type_str = 'CARD'
        channel_code_str = None
    elif method_prefix == 'DIRECT':
         parts_dd = selected_channel_key.split('_', 2)
         if len(parts_dd) == 3 and parts_dd[0] == 'DIRECT' and parts_dd[1] == 'DEBIT':
            payment_type_str = 'DIRECT_DEBIT'
            channel_code_str = parts_dd[2]

    if not payment_type_str:
        logger.error(f"Could not determine payment type from channel key: {selected_channel_key} for Order {order.id}")
        return {'status': 'FAILED', 'error': 'Invalid payment channel key format.'}

    # --- 3. Instantiate Currency Enum (Still likely needed for top-level param) ---
    order_currency_str = getattr(order, 'currency', 'PHP')
    try:
        currency_enum = PaymentRequestCurrency(order_currency_str)
    except ValueError:
        logger.error(f"Invalid PaymentRequestCurrency '{order_currency_str}' for Order {order.id}")
        return {'status': 'FAILED', 'error': f'Invalid currency code: {order_currency_str}'}


    # --- 4. Build the Payment Method Payload (Dictionary) ---
    payment_method_payload = {
        'type': payment_type_str,
        'reusability': 'ONE_TIME_USE',
    }

    # --- EWallet Specific ---
    if payment_type_str == 'EWALLET':
        if not channel_code_str: return {'status': 'FAILED', 'error': 'EWallet channel code missing.'}
        # Validate channel code string using Enum before putting string in payload
        try: EWalletChannelCode(channel_code_str)
        except ValueError: return {'status': 'FAILED', 'error': f'Invalid EWallet channel: {channel_code_str}'}

        success_redirect_url = _build_callback_url(request, order.id, 'success')
        failure_redirect_url = _build_callback_url(request, order.id, 'failure')
        payment_method_payload['ewallet'] = {
            'channel_code': channel_code_str, # Pass string
            'channel_properties': {
                'success_return_url': success_redirect_url,
                'failure_return_url': failure_redirect_url,
            }
        }

    # --- Virtual Account Specific ---
    elif payment_type_str == 'VIRTUAL_ACCOUNT':
        if not channel_code_str: return {'status': 'FAILED', 'error': 'VA channel code missing.'}
        # Validate channel code string using Enum
        try: VirtualAccountChannelCode(channel_code_str)
        except ValueError: return {'status': 'FAILED', 'error': f'Invalid VA channel: {channel_code_str}'}

        payment_method_payload['virtual_account'] = {
            'channel_code': channel_code_str, # Pass string
            'channel_properties': {
                'customer_name': f"{order.buyer.first_name or ''} {order.buyer.last_name or ''}".strip() or order.buyer.email,
            }
        }

    # --- Over The Counter Specific ---
    elif payment_type_str == 'OVER_THE_COUNTER':
        if not channel_code_str: return {'status': 'FAILED', 'error': 'OTC channel code missing.'}
        # Validate channel code string using Enum
        try: OverTheCounterChannelCode(channel_code_str)
        except ValueError: return {'status': 'FAILED', 'error': f'Invalid OTC channel: {channel_code_str}'}

        payment_method_payload['over_the_counter'] = {
            'channel_code': channel_code_str, # Pass string
            'currency': order_currency_str, # Pass string currency
            'amount': float(order.total_amount),
            'channel_properties': {
                'customer_name': f"{order.buyer.first_name or ''} {order.buyer.last_name or ''}".strip() or order.buyer.email,
            }
        }

    # --- QR Code Specific ---
    elif payment_type_str == 'QR_CODE':
        if not channel_code_str: return {'status': 'FAILED', 'error': 'QR channel code missing.'}
        # Validate channel code string using Enum
        try: QRCodeChannelCode(channel_code_str)
        except ValueError: return {'status': 'FAILED', 'error': f'Invalid QR channel: {channel_code_str}'}

        payment_method_payload['qr_code'] = {
             'channel_code': channel_code_str, # Pass string
             'currency': order_currency_str,   # Pass string currency
        }

    # --- Card Specific (Placeholder) ---
    elif payment_type_str == 'CARD':
        # No nested payload needed usually
        pass

    # --- Add DIRECT_DEBIT, PAYLATER if needed ---


    # --- 5. Build the Main Payment Request Payload (Dictionary) ---
    try:
        order_country_str = getattr(order, 'country', 'PH')

        payment_request_payload = {
            'currency': currency_enum, # <<< Use the Currency Enum object here
            'amount': float(order.total_amount),
            'reference_id': str(order.id),
            'country': order_country_str,
            'payment_method': payment_method_payload, # The nested dictionary
            'metadata': {
                'order_id': str(order.id),
                'user_email': order.buyer.email if order.buyer else 'N/A',
            },
            'description': f"Payment for Order #{str(order.id)[:8]}",
        }

        # Add top-level channel properties ONLY if needed (e.g., for Card redirect)
        if payment_type_str == 'CARD':
             success_redirect_url = _build_callback_url(request, order.id, 'success')
             failure_redirect_url = _build_callback_url(request, order.id, 'failure')
             payment_request_payload['channel_properties'] = {
                  'success_return_url': success_redirect_url,
                  'failure_return_url': failure_redirect_url,
             }

        logger.debug(f"Constructed Payment Request Payload for Order {order.id}: {json.dumps(payment_request_payload, default=str, indent=2)}") # Use default=str for Enums in log

    except Exception as e:
         logger.error(f"Failed to construct main Payment Request payload for Order {order.id}: {e}", exc_info=True)
         return {'status': 'FAILED', 'error': 'Internal error constructing payment request payload.'}


    # --- 6. Make the API Call ---
    try:
        logger.info(f"Sending Create Payment Request API call for Order {order.id}")
        api_response = api_instance.create_payment_request(
            payment_request_parameters=payment_request_payload
        )
        api_response_dict = api_response.to_dict()
        logger.info(f"Xendit create_payment_request successful for Order {order.id}.")
        logger.debug(f"Xendit Raw Response Dict: {api_response_dict}")

        # --- 7. Process Xendit Response ---
        # (Keep the response processing logic from the previous version)
        response_status = api_response_dict.get('status')
        xendit_request_id = api_response_dict.get('id')

        if xendit_request_id:
            try:
                with transaction.atomic():
                    order_locked = Order.objects.select_for_update().get(id=order.id)
                    order_locked.xendit_payment_request_id = xendit_request_id
                    order_locked.save(update_fields=['xendit_payment_request_id'])
            except Exception as db_err:
                 logger.error(f"Failed to save xendit_payment_request_id {xendit_request_id} to Order {order.id}: {db_err}", exc_info=True)
        else:
             logger.warning(f"Xendit response for Order {order.id} missing Payment Request 'id'.")

        structured_response = {'xendit_id': xendit_request_id, 'status': response_status}
        actions = api_response_dict.get('actions', [])
        payment_method_details = api_response_dict.get('payment_method', {})
        pm_type_from_response = payment_method_details.get('type')

        # (Keep the PENDING/REQUIRES_ACTION/SUCCEEDED/FAILED logic based on response_status)
        if response_status == 'PENDING' or response_status == 'REQUIRES_ACTION':
            redirect_url = None
            for action in actions:
                 action_type = action.get('action', '').upper()
                 url = action.get('url')
                 if url and action_type in ['CHECKOUT', 'AUTH', 'AUTHORIZE', 'QR_CODE_SCAN', 'VERIFY']:
                      redirect_url = url
                      structured_response['type'] = 'REDIRECT'
                      structured_response['payment_url'] = redirect_url
                      logger.info(f"Order {order.id} ({response_status}) requires redirect ({action_type}) to: {redirect_url}")
                      break
            if not redirect_url:
                  if pm_type_from_response == 'VIRTUAL_ACCOUNT':
                     # ... (extract VA details) ...
                     va_info = payment_method_details.get('virtual_account', {})
                     structured_response['type'] = 'VIRTUAL_ACCOUNT'
                     structured_response['details'] = {
                        'channel_code': va_info.get('channel_code'),
                        'account_number': va_info.get('account_number'),
                        'name': va_info.get('channel_properties', {}).get('customer_name'),
                        'expires_at': va_info.get('channel_properties', {}).get('expires_at'),
                     }
                     logger.info(f"Order {order.id} ({response_status}) requires VA payment.")
                  elif pm_type_from_response == 'QR_CODE':
                     # ... (extract QR details) ...
                     qr_info = payment_method_details.get('qr_code', {})
                     qr_string = qr_info.get('channel_properties', {}).get('qr_string')
                     if qr_string:
                        structured_response['type'] = 'QR_CODE'
                        structured_response['qr_string'] = qr_string
                        logger.info(f"Order {order.id} ({response_status}) requires QR Code payment.")
                     else: structured_response['type'] = 'UNKNOWN'
                  elif pm_type_from_response == 'OVER_THE_COUNTER':
                     # ... (extract OTC details) ...
                     otc_info = payment_method_details.get('over_the_counter', {})
                     structured_response['type'] = 'OTC'
                     structured_response['details'] = {
                        'channel_code': otc_info.get('channel_code'),
                        'payment_code': otc_info.get('channel_properties', {}).get('payment_code'),
                        'expires_at': otc_info.get('channel_properties', {}).get('expires_at'),
                        'amount': otc_info.get('amount'),
                        'currency': otc_info.get('currency'),
                     }
                     logger.info(f"Order {order.id} ({response_status}) requires OTC payment.")
                  else:
                      structured_response['type'] = 'UNKNOWN'
                      logger.warning(f"Order {order.id} status {response_status} but action/type unclear: PM Type={pm_type_from_response}, Actions={actions}")

        elif response_status == 'SUCCEEDED':
            structured_response['type'] = 'DIRECT'
            logger.info(f"Order {order.id} succeeded immediately.")

        elif response_status == 'FAILED':
            failure_code = api_response_dict.get('failure_code', 'UNKNOWN_ERROR')
            structured_response['error'] = f'Payment failed ({failure_code})'
            logger.error(f"Xendit payment request failed for Order {order.id}. Code: {failure_code}")

        else:
            structured_response['type'] = 'UNEXPECTED'
            structured_response['error'] = f'Unexpected status: {response_status}'
            logger.warning(f"Unexpected Xendit status '{response_status}' for Order {order.id}")

        return structured_response

    # --- 8. Error Handling for API Call ---
    except xendit.exceptions.ApiKeyError as e:
        # (Keep the same detailed ApiException handling)
        logger.error(f"Xendit API Exception creating Payment Request for Order {order.id}: Status {e.status}, Reason: {e.reason}", exc_info=False)
        logger.debug(f"Xendit API Exception Body: {e.body}")
        error_detail = f"API Error ({e.status})"
        try:
            error_body = json.loads(e.body)
            message = error_body.get('message', e.reason)
            error_detail += f": {message}"
        except:
             error_detail += f": {e.reason}"
        return {'status': 'FAILED', 'error': error_detail, 'raw_error': e.body}
    except Exception as e:
        # (Keep the same general Exception handling)
        logger.error(f"General error creating Xendit payment request for Order {order.id}: {e}", exc_info=True)
        return {'status': 'FAILED', 'error': 'Internal server error during payment creation.'}