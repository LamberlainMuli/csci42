# user/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import (
    login as auth_login,
    authenticate, # Keep authenticate if needed, but AuthenticationForm handles it
    logout as auth_logout,
    get_user_model
)
# Use Django's built-in form for standard login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.urls import reverse
from django.conf import settings
from django.contrib import messages
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
# Import transaction for atomic registration
from django.db import transaction
import logging
import traceback
from mix_and_match.models import UserOutfit
from .forms import CustomUserCreationForm, UserProfileForm
from .models import UserProfile

logger = logging.getLogger(__name__)
User = get_user_model()

# --- Email Verification Sender (Using Brevo API) ---
def send_verification_email(request, user):
    """Sends the verification email via Brevo API."""
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    current_site = get_current_site(request)
    protocol = 'https' # Assume HTTPS for production links
    # Or use logic as before if needed:
    # protocol = 'https' if request.is_secure() or request.META.get("HTTP_X_FORWARDED_PROTO") == "https" else 'http'
    verify_path = reverse('user:verify_email', kwargs={'uidb64': uid, 'token': token})
    # Use current_site.domain which should be correct if Sites framework is set up
    verify_url = f"{protocol}://{current_site.domain}{verify_path}"

    subject = 'Activate Your Ukay Account'
    context = {
        'user': user, 'verify_url': verify_url,
        'site_name': current_site.name,
    }
    # Render HTML content (Brevo API primarily uses HTML content)
    message_html = render_to_string('user/email/verify_email.html', context)
    # Optional: Render text content as fallback if needed by Brevo templates/API
    # message_txt = render_to_string('user/email/verify_email.txt', context)

    # --- Brevo API Configuration & Sending ---
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = settings.BREVO_API_KEY # Get key from settings

    if not configuration.api_key['api-key']:
         logger.error(f"Brevo API Key not found in settings for sending email to {user.email}")
         return False

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
    sender_info = {"email": settings.BREVO_SENDER_EMAIL, "name": settings.BREVO_SENDER_NAME}
    to_info = [{"email": user.email, "name": user.username}] # Use username or full name if available

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=to_info,
        sender=sender_info,
        subject=subject,
        html_content=message_html
        # text_content=message_txt # Add if you have a text version
    )

    try:
        logger.info(f"Attempting to send verification email to {user.email} via Brevo API")
        api_response = api_instance.send_transac_email(send_smtp_email)
        logger.info(f"Brevo API response for {user.email}: {api_response}")
        # Check response? Usually, no exception means it was accepted by Brevo.
        return True
    except ApiException as e:
        logger.error(f"Brevo API Exception when sending email to {user.email}: {e.status} {e.reason} - {e.body}\n", exc_info=True)
        return False
    except Exception as e:
        # Catch other potential errors (network before API call, config issues)
        logger.error(f"Non-API error sending verification email to {user.email}: {e}", exc_info=True)
        return False
    # --- End Brevo API Sending ---

# --- Registration View (Added Explicit Profile Creation) ---
def register_view(request):
    if request.user.is_authenticated:
        return redirect('user:profile')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            email_for_logging = form.cleaned_data.get('email', 'UNKNOWN_EMAIL')
            try:
                with transaction.atomic():
                    logger.info(f"Attempting registration for {email_for_logging}")
                    user = form.save(commit=False)
                    # Password is set by form.save() inherited behavior
                    user.save() # Save user within transaction
                    logger.info(f"User {user.email} created in DB (inactive).")

                    # *** Explicitly create the UserProfile here ***
                    UserProfile.objects.create(user=user)
                    logger.info(f"UserProfile created for {user.email}.")

                    # Send verification email *within the transaction*
                    email_sent = send_verification_email(request, user)

                    if not email_sent:
                        # If email fails, raise error to rollback user AND profile creation
                        logger.error(f"Verification email failed for {user.email}. Rolling back transaction.")
                        raise Exception("EMAIL_SEND_FAILURE") # Use sentinel string

                # --- Transaction Committed Successfully ---
                logger.info(f"Registration transaction committed for {user.email}.")
                messages.info(request, 'Registration successful! Please check your email to verify your account.')
                return redirect('user:registration_pending')

            except Exception as e:
                logger.error(f"Registration transaction failed for {email_for_logging}: {e}", exc_info=('EMAIL_SEND_FAILURE' not in str(e))) # Less detail for expected email failure

                if "EMAIL_SEND_FAILURE" in str(e):
                    error_message = "Registration failed: Could not send verification email. Check address or contact support."
                else:
                    error_message = "An error occurred during registration. Please try again or contact support."
                messages.error(request, error_message)
                # Fall through to re-render form

        else: # Form invalid
            logger.warning(f"Registration form invalid: {form.errors.as_json()}")
            messages.error(request, "Please correct the errors below.")
            # Fall through to re-render form

    else: # GET request
        form = CustomUserCreationForm()

    return render(request, 'user/register.html', {'form': form})


# --- Registration Pending Info View (No changes needed) ---
def registration_pending_view(request):
     return render(request, 'user/registration_pending.html')


# --- Email Verification View (No changes needed) ---
def verify_email_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if user.is_active and user.is_email_verified:
             messages.info(request, 'Your email is already verified. You can login.')
        elif not user.is_active:
             user.is_active = True
             user.is_email_verified = True
             user.save(update_fields=['is_active', 'is_email_verified'])
             logger.info(f"User {user.email} activated and verified email.")
             messages.success(request, 'Email verified successfully! Your account is now active. Please login.')
        else: # Active but not verified
             user.is_email_verified = True
             user.save(update_fields=['is_email_verified'])
             logger.info(f"User {user.email} verified email (was already active).")
             messages.success(request, 'Email verified successfully! You can now login.')
        return redirect('user:login')
    else:
        messages.error(request, 'The verification link was invalid or has expired.')
        return redirect('user:register')


# --- Login View (Improved Checks & Redirect) ---
def login_view(request):
    if request.user.is_authenticated:
        return redirect('user:profile') # Or wherever logged-in users should go

    next_url = request.GET.get('next') or request.POST.get('next') or reverse('user:profile') # Determine redirect URL

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST) # Pass request to AuthenticationForm
        if form.is_valid():
            user = form.get_user()

            # Check active and verified status *after* getting the user object
            if not user.is_email_verified:
                 logger.warning(f"Login attempt failed for {user.email}: Email not verified.")
                 messages.error(request, 'Your email address has not been verified. Please check your inbox for the verification link.')
                 # Optionally allow resending verification email here
                 return render(request, 'user/login.html', {'form': form, 'next': next_url})

            if not user.is_active:
                 logger.warning(f"Login attempt failed for {user.email}: Account inactive.")
                 messages.error(request, 'This account is inactive. Please contact support if you believe this is an error.')
                 return render(request, 'user/login.html', {'form': form, 'next': next_url})

            # If checks pass, log the user in
            auth_login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            logger.info(f"User {user.email} logged in successfully.")
            # Redirect to 'next' URL or profile
            # Add safety check for next_url using url_has_allowed_host_and_scheme
            from django.utils.http import url_has_allowed_host_and_scheme
            if url_has_allowed_host_and_scheme(url=next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            else:
                return redirect('user:profile') # Fallback redirect

        else: # Form is invalid (e.g., wrong password)
             logger.warning(f"Invalid login attempt for user: {request.POST.get('username')}") # 'username' is the default field name for AuthenticationForm
             messages.error(request, 'Invalid email or password. Please try again.')
             # Errors are attached to the form by AuthenticationForm

    else: # GET request
        form = AuthenticationForm()

    return render(request, 'user/login.html', {'form': form, 'next': next_url})


# --- Logout View (No changes needed) ---
@login_required
def logout_view(request):
    logger.info(f"User {request.user.email} logging out.")
    auth_logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('user:login')


# --- Profile Views (No changes needed for this fix) ---
@login_required
def profile_view(request):
    """Displays user profile along with their saved outfits."""
    profile = get_object_or_404(UserProfile, user=request.user)

    # Fetch user's saved outfits, ordered by most recent
    # Prefetch items and product images for efficiency in the template preview
    user_outfits = UserOutfit.objects.filter(
        user=request.user
    ).prefetch_related(
        'items',
        'items__product__images', # Prefetch product images via items
        'ai_result' # Prefetch the AI result if it exists
    ).order_by('-created_at')

    context = {
        'profile': profile,
        'outfits': user_outfits, # Add outfits to context
    }
    return render(request, 'user/profile.html', context)

@login_required
def update_profile_view(request):
    profile = get_object_or_404(UserProfile, user=request.user)
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('user:profile')
        else:
             messages.error(request, "Please correct the errors below.")
    else:
        form = UserProfileForm(instance=profile)
    return render(request, 'user/profile_update.html', {'form': form})

def public_profile_view(request, username):
    """Displays a public version of a user's profile."""
    User = get_user_model()
    # Fetch the user whose profile is being viewed
    target_user = get_object_or_404(User.objects.select_related('profile'), username=username, is_active=True)
    target_profile = target_user.profile # Access profile via related object

    # Fetch only the PUBLIC outfits for this user
    public_outfits = UserOutfit.objects.filter(
        user=target_user,
        is_public=True
    ).prefetch_related(
        'items', # Prefetch items if needed in template (e.g., count)
        'ai_result' # Prefetch AI result for display_image_url
    ).order_by('-created_at')

    context = {
        'target_user': target_user,
        'target_profile': target_profile,
        'public_outfits': public_outfits,
        'is_own_profile': request.user == target_user # Flag if viewer is the profile owner
    }
    return render(request, 'user/public_profile.html', context)