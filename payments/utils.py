# payments/utils.py

import logging
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.contrib.sites.shortcuts import get_current_site

# Add Brevo SDK imports if using API
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

logger = logging.getLogger(__name__)

def send_seller_sale_notification(order, seller_email, sold_items_list, buyer_info, request=None):
    """Sends sale notification email to a seller via Brevo API."""
    if not all([settings.BREVO_API_KEY, settings.BREVO_SENDER_EMAIL, settings.BREVO_SENDER_NAME]):
        logger.error(f"Cannot send seller notification for Order {order.id}: Brevo settings missing.")
        return False

    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = settings.BREVO_API_KEY
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

    subject = f"You've Made a Sale on Ukay! (Order #{str(order.id)[:8]})"
    # Construct order URL
    order_url = "#" # Default
    try:
        current_site = get_current_site(request) # Pass request if available
        order_detail_path = reverse('orders:order_detail', kwargs={'order_id': order.id})
        protocol = 'https' if request and (request.is_secure() or request.META.get("HTTP_X_FORWARDED_PROTO") == "https") else 'http'
        # If request is None, try getting default site and assume https
        if not request:
             current_site = get_current_site(None)
             protocol = 'https'
        order_url = f"{protocol}://{current_site.domain}{order_detail_path}"
    except Exception as e:
        logger.error(f"Could not build order URL for seller email (Order {order.id}): {e}")


    context = {
        'seller_email': seller_email, 'sold_items': sold_items_list,
        'order_id': str(order.id), 'order_short_id': str(order.id)[:8],
        'buyer_info': buyer_info, 'order_url': order_url
    }
    message_html = render_to_string('payments/email/sale_notification.html', context)
    message_txt = render_to_string('payments/email/sale_notification.txt', context) # Add text version

    sender_info = {"email": settings.BREVO_SENDER_EMAIL, "name": settings.BREVO_SENDER_NAME}
    to_info = [{"email": seller_email}]

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=to_info, sender=sender_info, subject=subject,
        html_content=message_html, text_content=message_txt
    )

    try:
        logger.info(f"Attempting to send sale notification to {seller_email} for Order {order.id} via Brevo API")
        api_response = api_instance.send_transac_email(send_smtp_email)
        logger.info(f"Brevo API response for seller {seller_email}: {api_response}")
        return True
    except ApiException as e:
        logger.error(f"Brevo API Exception sending seller ({seller_email}) email for Order {order.id}: {e.status} {e.reason} - {e.body}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Non-API error sending seller ({seller_email}) email for Order {order.id}: {e}", exc_info=True)
        return False