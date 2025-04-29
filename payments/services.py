# payments/services.py

import xendit
from xendit import Configuration
from xendit.apis import PaymentRequestApi
# Import the correct exception class for API errors
from xendit.exceptions import XenditSdkException
# Import other potential exceptions from the library
from xendit.exceptions import ApiValueError, ApiKeyError, ApiTypeError, ApiAttributeError, OpenApiException
from xendit.payment_request.model import (
    EWalletChannelCode,
    VirtualAccountChannelCode,
    OverTheCounterChannelCode,
    QRCodeChannelCode,
    PaymentRequestCurrency
)

from orders.models import Order
from django.urls import reverse
from django.conf import settings
import logging
import json
from decimal import Decimal
from django.db import transaction

logger = logging.getLogger(__name__)

# --- Helper Function to Build Redirect URLs ---
def _build_callback_url(request, order_id, status):
    """Builds the absolute callback URL with order ID."""
    base_url = request.build_absolute_uri('/')[:-1]
    relative_url = reverse('payments:payment_callback', kwargs={'status': status})
    full_url = f"{base_url.rstrip('/')}/{relative_url.lstrip('/')}?ref_id={order_id}"
    logger.debug(f"Built callback URL: {full_url}")
    return full_url

# --- Main Service Function ---
def create_xendit_payment_request(order: Order, request, selected_channel_key: str):
    """
    Creates a payment request with Xendit using dictionary payloads,
    adds logging, saves the payment channel, handles redirects, and uses correct exception handling.
    """
    logger.info(f"--- Initiating Xendit Payment Request for Order {order.id} ---")
    logger.info(f"Selected Channel Key: {selected_channel_key}")

    # --- 1. Initialize Xendit Client with API Key ---
    api_key = settings.XENDIT_SECRET_API_KEY
    if not api_key:
        logger.critical("XENDIT_SECRET_API_KEY is not set in Django settings.")
        return {'status': 'FAILED', 'error': 'Payment system configuration error.'}

    try:
        configuration = Configuration(api_key=api_key)
        api_client = xendit.ApiClient(configuration=configuration)
        api_instance = PaymentRequestApi(api_client)
        logger.debug("Xendit API client initialized successfully.")
    except Exception as config_e:
        logger.critical(f"Failed to initialize Xendit API client: {config_e}", exc_info=True)
        return {'status': 'FAILED', 'error': 'Payment system configuration error.'}

    # --- 2. Determine Payment Type and Channel Code from Key ---
    payment_type_str = None
    channel_code_str = None
    derived_payment_channel = None
    # (Keep the logic for determining these based on selected_channel_key as before)
    parts = selected_channel_key.split('_', 1)
    method_prefix = parts[0]
    if method_prefix == 'EWALLET':
        payment_type_str = 'EWALLET'
        if len(parts) > 1: channel_code_str = parts[1]
        derived_payment_channel = channel_code_str or payment_type_str
    elif method_prefix == 'VIRTUAL':
        parts_va = selected_channel_key.split('_', 2)
        if len(parts_va) == 3 and parts_va[0] == 'VIRTUAL' and parts_va[1] == 'ACCOUNT':
            payment_type_str = 'VIRTUAL_ACCOUNT'
            channel_code_str = parts_va[2]
            derived_payment_channel = channel_code_str or payment_type_str
    elif method_prefix == 'OTC':
        payment_type_str = 'OVER_THE_COUNTER'
        if len(parts) > 1: channel_code_str = parts[1]
        derived_payment_channel = channel_code_str or payment_type_str
    elif method_prefix == 'QR':
        parts_qr = selected_channel_key.split('_', 2)
        if len(parts_qr) == 3 and parts_qr[0] == 'QR' and parts_qr[1] == 'CODE':
            payment_type_str = 'QR_CODE'
            channel_code_str = parts_qr[2]
            derived_payment_channel = channel_code_str or payment_type_str
    elif method_prefix == 'CARD':
        payment_type_str = 'CARD'
        channel_code_str = None
        derived_payment_channel = payment_type_str
    elif method_prefix == 'DIRECT':
        parts_dd = selected_channel_key.split('_', 2)
        if len(parts_dd) == 3 and parts_dd[0] == 'DIRECT' and parts_dd[1] == 'DEBIT':
            payment_type_str = 'DIRECT_DEBIT'
            channel_code_str = parts_dd[2]
            derived_payment_channel = channel_code_str or payment_type_str

    logger.debug(f"Determined Payment Type: {payment_type_str}, Channel Code: {channel_code_str}")
    logger.debug(f"Channel to be saved to Order: {derived_payment_channel}")
    if not payment_type_str:
        logger.error(f"Could not determine payment type from channel key: {selected_channel_key} for Order {order.id}")
        return {'status': 'FAILED', 'error': 'Invalid payment channel key format.'}

    # --- 2.5 Save Payment Channel (Task 5a) ---
    try:
        with transaction.atomic():
            order_to_update = Order.objects.select_for_update().get(id=order.id)
            order_to_update.payment_channel = derived_payment_channel
            order_to_update.save(update_fields=['payment_channel'])
            logger.info(f"Successfully saved payment_channel='{derived_payment_channel}' to Order {order.id}")
    except Order.DoesNotExist:
         logger.error(f"Order {order.id} not found during payment channel update.")
         return {'status': 'FAILED', 'error': 'Order consistency error.'}
    except Exception as db_err:
        logger.error(f"Failed to save payment_channel to Order {order.id}: {db_err}", exc_info=True)
        return {'status': 'FAILED', 'error': 'Database error saving payment details.'}

    # --- 3. Instantiate Currency Enum ---
    order_currency_str = getattr(order, 'currency', 'PHP')
    try:
        currency_enum = PaymentRequestCurrency(order_currency_str)
        logger.debug(f"Validated currency: {order_currency_str}")
    except ValueError:
        logger.error(f"Invalid PaymentRequestCurrency '{order_currency_str}' for Order {order.id}")
        return {'status': 'FAILED', 'error': f'Invalid currency code: {order_currency_str}'}


    # --- 4. Build the Payment Method Payload (Dictionary) ---
    payment_method_payload = {
        'type': payment_type_str,
        'reusability': 'ONE_TIME_USE',
    }

    success_redirect_url = _build_callback_url(request, order.id, 'success')
    failure_redirect_url = _build_callback_url(request, order.id, 'failure')

    # Add channel-specific details
    if payment_type_str == 'EWALLET':
        if not channel_code_str: return {'status': 'FAILED', 'error': 'EWallet channel code missing.'}
        try: EWalletChannelCode(channel_code_str)
        except ValueError: return {'status': 'FAILED', 'error': f'Invalid EWallet channel: {channel_code_str}'}
        # *** REVERTED: Put redirect URLs back into nested properties for EWallet ***
        payment_method_payload['ewallet'] = {
            'channel_code': channel_code_str,
            'channel_properties': {
                 'success_return_url': success_redirect_url,
                 'failure_return_url': failure_redirect_url,
                 # Add mobile_number here if needed for specific e-wallets like GrabPay
            }
        }
        # Note: We will STILL add the top-level channel_properties later as per the old working code
    elif payment_type_str == 'VIRTUAL_ACCOUNT':
        if not channel_code_str: return {'status': 'FAILED', 'error': 'VA channel code missing.'}
        try: VirtualAccountChannelCode(channel_code_str)
        except ValueError: return {'status': 'FAILED', 'error': f'Invalid VA channel: {channel_code_str}'}
        payment_method_payload['virtual_account'] = {
            'channel_code': channel_code_str,
            'channel_properties': {
                'customer_name': f"{order.buyer.first_name or ''} {order.buyer.last_name or ''}".strip() or order.buyer.email,
            }
        }
    elif payment_type_str == 'OVER_THE_COUNTER':
        if not channel_code_str: return {'status': 'FAILED', 'error': 'OTC channel code missing.'}
        try: OverTheCounterChannelCode(channel_code_str)
        except ValueError: return {'status': 'FAILED', 'error': f'Invalid OTC channel: {channel_code_str}'}
        payment_method_payload['over_the_counter'] = {
            'channel_code': channel_code_str,
            'currency': order_currency_str,
            'amount': float(order.total_amount),
            'channel_properties': {
                'customer_name': f"{order.buyer.first_name or ''} {order.buyer.last_name or ''}".strip() or order.buyer.email,
            }
        }
    elif payment_type_str == 'QR_CODE':
        if not channel_code_str: return {'status': 'FAILED', 'error': 'QR channel code missing.'}
        try: QRCodeChannelCode(channel_code_str)
        except ValueError: return {'status': 'FAILED', 'error': f'Invalid QR channel: {channel_code_str}'}
        payment_method_payload['qr_code'] = {
             'channel_code': channel_code_str,
             'currency': order_currency_str,
        }
    elif payment_type_str == 'CARD':
         pass # No nested payload needed usually
    elif payment_type_str == 'DIRECT_DEBIT':
         pass # Placeholder - Implement if needed

    # Log the built payment method payload
    try:
        logger.debug(f"Built Payment Method Payload for Order {order.id}: {json.dumps(payment_method_payload, default=str, indent=2)}")
    except Exception as json_err:
        logger.warning(f"Could not serialize payment_method_payload for logging: {json_err}")


    # --- 5. Build the Main Payment Request Payload (Dictionary) ---
    try:
        order_country_str = getattr(order, 'country', 'PH')
        buyer_email = order.buyer.email if order.buyer else None
        if not buyer_email and payment_type_str not in ['QR_CODE']:
             logger.warning(f"Order {order.id} is missing buyer email, potentially required for {payment_type_str}.")

        payment_request_payload = {
            'currency': currency_enum,
            'amount': float(order.total_amount),
            'reference_id': str(order.id),
            'country': order_country_str,
            'payment_method': payment_method_payload, # Includes the nested structure
            'metadata': {
                'order_id': str(order.id),
                'user_email': buyer_email or 'N/A',
            },
            'description': f"Payment for Order #{str(order.id)[:8]}",
        }

        # Add top-level channel properties - As per old working code, ADD for both CARD and EWALLET
        if payment_type_str in ['CARD', 'EWALLET']:
             logger.debug(f"Adding TOP-LEVEL channel_properties for {payment_type_str}")
             payment_request_payload['channel_properties'] = {
                 'success_return_url': success_redirect_url,
                 'failure_return_url': failure_redirect_url,
             }

        # Log the final constructed payload before sending
        logger.debug(f"Constructed FINAL Payment Request Payload for Order {order.id}: {json.dumps(payment_request_payload, default=str, indent=2)}")

    except Exception as e:
        logger.error(f"Failed to construct main Payment Request payload for Order {order.id}: {e}", exc_info=True)
        return {'status': 'FAILED', 'error': 'Internal error constructing payment request payload.'}


    # --- 6. Make the API Call ---
    try:
        logger.info(f"Sending Create Payment Request API call to Xendit for Order {order.id}")
        api_response = api_instance.create_payment_request(
            payment_request_parameters=payment_request_payload
        )
        api_response_dict = api_response.to_dict()
        logger.info(f"Xendit create_payment_request successful for Order {order.id}. Status: {api_response_dict.get('status')}")
        logger.debug(f"Xendit Raw Response Dict for Order {order.id}: {json.dumps(api_response_dict, default=str, indent=2)}")

        # --- 7. Process Xendit Response ---
        response_status = api_response_dict.get('status')
        xendit_request_id = api_response_dict.get('id')
        # (Keep the logic for saving xendit_request_id)
        if xendit_request_id:
            try:
                with transaction.atomic():
                    order_locked = Order.objects.select_for_update().get(id=order.id)
                    order_locked.xendit_payment_request_id = xendit_request_id
                    order_locked.save(update_fields=['xendit_payment_request_id'])
                    logger.info(f"Saved xendit_payment_request_id {xendit_request_id} to Order {order.id}")
            except Exception as db_err:
                logger.error(f"Failed to save xendit_payment_request_id {xendit_request_id} to Order {order.id}: {db_err}", exc_info=True)
        else:
            logger.warning(f"Xendit response for Order {order.id} missing Payment Request 'id'.")

        # (Keep the logic for structuring the response, including redirect fix and display types)
        structured_response = {
            'xendit_request_id': xendit_request_id,
            'status': response_status
        }
        actions = api_response_dict.get('actions', [])
        payment_method_details = api_response_dict.get('payment_method', {})
        pm_type_from_response = payment_method_details.get('type')

        if response_status in ['PENDING', 'REQUIRES_ACTION']:
            redirect_url = None
            for action in actions:
                url = action.get('url')
                action_name = action.get('action', 'UNKNOWN').upper()
                if url:
                    redirect_url = url
                    structured_response['type'] = 'REDIRECT'
                    structured_response['payment_url'] = redirect_url
                    logger.info(f"Order {order.id} ({response_status}) requires REDIRECT via action '{action_name}' to: {redirect_url}")
                    break
            if not redirect_url:
                # Handle VA, QR, OTC, UNKNOWN_PENDING display types
                # (Keep this logic exactly as in the previous correct version)
                if pm_type_from_response == 'QR_CODE':
                    qr_info = payment_method_details.get('qr_code', {})
                    qr_code_string = qr_info.get('channel_properties', {}).get('qr_string')
                    if qr_code_string:
                        structured_response['type'] = 'QR_CODE'
                        structured_response['qr_string'] = qr_code_string
                        structured_response['details'] = {
                             'channel_code': qr_info.get('channel_code'),
                             'amount': api_response_dict.get('amount'),
                             'currency': api_response_dict.get('currency'),
                             'expires_at': qr_info.get('channel_properties', {}).get('expires_at'),
                         }
                        logger.info(f"Order {order.id} ({response_status}) requires QR_CODE display.")
                    else:
                        structured_response['type'] = 'UNKNOWN_PENDING'
                        logger.warning(f"Order {order.id} ({response_status}) is QR Code type but missing qr_string.")
                elif pm_type_from_response == 'VIRTUAL_ACCOUNT':
                    va_info = payment_method_details.get('virtual_account', {})
                    structured_response['type'] = 'VIRTUAL_ACCOUNT'
                    structured_response['details'] = {
                        'channel_code': va_info.get('channel_code'),
                        'account_number': va_info.get('account_number'),
                        'name': va_info.get('channel_properties', {}).get('customer_name'),
                        'amount': api_response_dict.get('amount'),
                        'currency': api_response_dict.get('currency'),
                        'expires_at': va_info.get('channel_properties', {}).get('expires_at'),
                    }
                    logger.info(f"Order {order.id} ({response_status}) requires VIRTUAL_ACCOUNT display.")
                elif pm_type_from_response == 'OVER_THE_COUNTER':
                    otc_info = payment_method_details.get('over_the_counter', {})
                    structured_response['type'] = 'OTC'
                    structured_response['details'] = {
                        'channel_code': otc_info.get('channel_code'),
                        'payment_code': otc_info.get('channel_properties', {}).get('payment_code'),
                        'expires_at': otc_info.get('channel_properties', {}).get('expires_at'),
                        'amount': otc_info.get('amount'),
                        'currency': otc_info.get('currency'),
                        'customer_name': otc_info.get('channel_properties', {}).get('customer_name'),
                    }
                    logger.info(f"Order {order.id} ({response_status}) requires OTC display.")
                else:
                    structured_response['type'] = 'UNKNOWN_PENDING'
                    logger.warning(f"Order {order.id} status {response_status} but no redirect/display type found. PM Type={pm_type_from_response}, Actions={actions}")

        elif response_status == 'SUCCEEDED':
             structured_response['type'] = 'DIRECT_SUCCESS'
             logger.info(f"Order {order.id} payment SUCCEEDED immediately via API response.")
        elif response_status == 'FAILED':
            # (Keep FAILED handling, including DB update)
            failure_code = api_response_dict.get('failure_code', 'UNKNOWN_API_ERROR')
            structured_response['error'] = f'Payment request failed ({failure_code})'
            try:
                 with transaction.atomic():
                      order_failed = Order.objects.select_for_update().get(id=order.id)
                      if order_failed.status != 'FAILED':
                          order_failed.status = 'FAILED'
                          order_failed.failure_reason = failure_code[:255]
                          order_failed.save(update_fields=['status', 'failure_reason'])
                          logger.info(f"Order {order.id} status set to FAILED via API response. Reason: {failure_code}")
            except Exception as db_err:
                  logger.error(f"Failed to update order status to FAILED for Order {order.id} after API failure: {db_err}", exc_info=True)
            logger.error(f"Xendit payment request creation failed for Order {order.id}. Code: {failure_code}")
        else: # (Handle unexpected status)
            structured_response['type'] = 'UNEXPECTED_STATUS'
            structured_response['error'] = f'Unexpected Xendit status: {response_status}'
            logger.warning(f"Unexpected Xendit status '{response_status}' for Order {order.id}")

        logger.debug(f"Returning structured response for Order {order.id}: {json.dumps(structured_response, default=str)}")
        return structured_response

    # --- 8. Error Handling for API Call ---
    except XenditSdkException as e: # Catch correct exception
        # (Keep the corrected XenditSdkException handling as before)
        logger.error(f"Xendit API Exception creating Payment Request for Order {order.id}: Status {e.status}, Code: {e.errorCode}, Message: {e.errorMessage}", exc_info=False)
        logger.debug(f"Xendit API Exception Raw Response: {e.rawResponse}", exc_info=False)
        error_detail = f"Payment Gateway Error ({e.status})"
        if e.errorCode: error_detail += f" Code: {e.errorCode}"
        if e.errorMessage: error_detail += f": {e.errorMessage[:100]}" + ("..." if len(e.errorMessage) > 100 else "")
        else: error_detail += ": Please try again or contact support."
        raw_error_body_for_response = e.rawResponse
        try: # Attempt to update order status to FAILED
            with transaction.atomic():
                 order_failed_api = Order.objects.select_for_update().get(id=order.id)
                 if order_failed_api.status != 'FAILED':
                     order_failed_api.status = 'FAILED'
                     reason = f"API Error: {e.status} {e.errorCode} - {e.errorMessage}"
                     order_failed_api.failure_reason = reason[:255]
                     order_failed_api.save(update_fields=['status', 'failure_reason'])
                     logger.info(f"Order {order.id} status set to FAILED due to XenditSdkException.")
        except Exception as db_err:
             logger.error(f"Failed to update order status to FAILED for Order {order.id} after XenditSdkException: {db_err}", exc_info=True)
        return {'status': 'FAILED', 'error': error_detail, 'raw_error': raw_error_body_for_response}

    except (ApiValueError, ApiKeyError, ApiTypeError, ApiAttributeError, OpenApiException) as e:
        # (Keep handling for other library errors)
        logger.error(f"Xendit Library Error processing request for Order {order.id}: {type(e).__name__} - {e}", exc_info=True)
        try: # Attempt to update order status to FAILED
            with transaction.atomic():
                 order_failed_lib = Order.objects.select_for_update().get(id=order.id)
                 if order_failed_lib.status != 'FAILED':
                     order_failed_lib.status = 'FAILED'
                     order_failed_lib.failure_reason = f"Internal Library Error: {type(e).__name__}"[:255]
                     order_failed_lib.save(update_fields=['status', 'failure_reason'])
                     logger.info(f"Order {order.id} status set to FAILED due to Xendit Library Error.")
        except Exception as db_err:
             logger.error(f"Failed to update order status to FAILED for Order {order.id} after Library Error: {db_err}", exc_info=True)
        return {'status': 'FAILED', 'error': f'Internal payment processing error. Please contact support.'}

    except Exception as e:
        # (Keep general exception handling)
        logger.error(f"General error during Xendit payment request API call/processing for Order {order.id}: {e}", exc_info=True)
        try: # Attempt to update order status to FAILED
            with transaction.atomic():
                 order_failed_gen = Order.objects.select_for_update().get(id=order.id)
                 if order_failed_gen.status != 'FAILED':
                     order_failed_gen.status = 'FAILED'
                     order_failed_gen.failure_reason = "Internal Server Error during Payment Creation"[:255]
                     order_failed_gen.save(update_fields=['status', 'failure_reason'])
                     logger.info(f"Order {order.id} status set to FAILED due to General Exception.")
        except Exception as db_err:
             logger.error(f"Failed to update order status to FAILED for Order {order.id} after General Exception: {db_err}", exc_info=True)
        return {'status': 'FAILED', 'error': 'An unexpected internal server error occurred during payment creation.'}