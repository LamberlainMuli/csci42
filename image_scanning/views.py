# ukay/image_scanning/views.py
import os
import base64
import io
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.core.files.base import ContentFile
from django.urls import reverse

from .forms import UploadedImageForm
from .models import UploadedImage # Import model containing upload_to functions
# Remove ProcessedClothingItem if not directly used
from marketplace.models import Product, ProductImage
from . import utils
import logging

logger = logging.getLogger(__name__)

# --- Helper to get expected paths/url (Revised) ---
def get_processed_paths(uploaded_instance: UploadedImage):
    """Generates expected relative path, full path, and URL for the processed image."""
    if not all([uploaded_instance, uploaded_instance.original_image, uploaded_instance.user]):
         return None, None, None

    # Replicate logic from models.upload_to_processed
    base_name = os.path.splitext(os.path.basename(uploaded_instance.original_image.name))[0]
    processed_filename = f"processed_{base_name}.png" # Standardize name
    relative_dir = f'image_scanning/processed/{uploaded_instance.user.username}' # Matches models.py function

    processed_relative_path = os.path.join(relative_dir, processed_filename)
    processed_full_path = os.path.join(settings.MEDIA_ROOT, processed_relative_path)
    processed_url = os.path.join(settings.MEDIA_URL, processed_relative_path).replace(os.path.sep, '/')

    return processed_relative_path, processed_full_path, processed_url

# --- Views ---

@login_required
def scanning_guide(request):
    return render(request, 'image_scanning/scanning_guide.html')

@login_required
def upload_image(request):
    if request.method == 'POST':
        form = UploadedImageForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['original_image']
            if uploaded_file.size > 25 * 1024 * 1024:
                 messages.error(request, "Image file too large (max 25MB).")
                 return render(request, 'image_scanning/upload.html', {'form': form})
            try:
                uploaded = form.save(commit=False); uploaded.user = request.user; uploaded.save()
                logger.info(f"Uploaded image {uploaded.id} saved by {request.user.email}")
                # Instead of redirecting to process_image, redirect to the preview page
                # which will *trigger* processing via JS if needed, or show result.
                # For now, we stick to sync: redirect to process which redirects to preview
                return redirect('image_scanning:process_image', uploaded_id=uploaded.id)
            except Exception as e:
                 logger.error(f"Error saving uploaded image: {e}", exc_info=True)
                 messages.error(request, "Could not save uploaded image.")
        else: messages.error(request, "Invalid file or form data.")
    else: form = UploadedImageForm()
    return render(request, 'image_scanning/upload.html', {'form': form})

@login_required
def process_image(request, uploaded_id):
    """
    Processes the image synchronously, saves optimized version, redirects to preview.
    """
    uploaded = get_object_or_404(UploadedImage, id=uploaded_id, user=request.user)
    try:
        logger.info(f"Processing image {uploaded_id} for {request.user.email}")
        processed_image_pil = utils.remove_background_and_optimize(uploaded.original_image.path)

        relative_path, full_path, _ = get_processed_paths(uploaded)
        if not full_path: raise ValueError("Could not determine processed image path.")

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        processed_image_pil.save(full_path, format='PNG', optimize=True)
        logger.info(f"Saved optimized processed image to: {full_path}")

        # Redirect to the preview page
        return redirect('image_scanning:process_preview', uploaded_id=uploaded.id)

    except Exception as e:
        logger.error(f"Error processing image {uploaded_id}: {e}", exc_info=True)
        messages.error(request, f"Error processing image: Please try uploading again.")
        return redirect('image_scanning:upload_image')

@login_required
def process_preview(request, uploaded_id):
     """Displays processed image preview, handles confirm/retake/edit."""
     uploaded = get_object_or_404(UploadedImage, id=uploaded_id, user=request.user)
     relative_path, full_path, processed_url = get_processed_paths(uploaded)

     if not processed_url or not os.path.exists(full_path):
         # Maybe the file is still being processed? Or failed?
         # Re-trigger processing just in case? Or assume failure?
         logger.warning(f"Processed image file not found at preview: {full_path}. Re-processing attempt disabled for now.")
         messages.error(request, "Processed image not ready or failed. Please try uploading again.")
         return redirect('image_scanning:upload_image')

     if request.method == 'POST':
         if 'confirm' in request.POST:
             product_id = request.session.get('attach_product_id') or request.session.get('replace_product_id')
             if product_id:
                 # Pass uploaded_id to finalize view
                 return redirect(reverse('marketplace:finalize-product-image', kwargs={'product_id': product_id, 'uploaded_id': uploaded.id}))
             else:
                 messages.error(request, "No product context found.")
                 return redirect('marketplace:home')
         elif 'retake' in request.POST:
             # Clean up files and record before redirecting
             try: os.remove(full_path); logger.info(f"Deleted processed file: {full_path}")
             except OSError: logger.warning(f"Could not delete processed file: {full_path}")
             try: os.remove(uploaded.original_image.path); logger.info(f"Deleted original file: {uploaded.original_image.path}")
             except OSError: logger.warning(f"Could not delete original file: {uploaded.original_image.path}")
             uploaded.delete(); logger.info(f"Deleted UploadedImage record: {uploaded_id}")
             messages.info(request, "Image discarded. Please upload new image.")
             return redirect('image_scanning:upload_image')
         elif 'edit' in request.POST:
             return redirect('image_scanning:edit_image', uploaded_id=uploaded.id)

     context = {'uploaded': uploaded, 'processed_url': processed_url}
     return render(request, 'image_scanning/process_preview.html', context)

@login_required
def edit_image(request, uploaded_id):
    """Allows editing using Toast UI Image Editor."""
    uploaded = get_object_or_404(UploadedImage, id=uploaded_id, user=request.user)
    relative_path, full_path, processed_url = get_processed_paths(uploaded)

    if not processed_url or not os.path.exists(full_path):
        messages.error(request, "Image to edit not found.")
        return redirect('image_scanning:upload_image')

    if request.method == 'POST':
        edited_data = request.POST.get('edited_image_data') # Matches JS output
        if edited_data:
            try:
                # Decode base64 data
                format, imgstr = edited_data.split(';base64,')
                image_bytes = base64.b64decode(imgstr)

                # Overwrite the *processed* file with the edited version
                with open(full_path, 'wb') as f:
                    f.write(image_bytes)
                logger.info(f"Saved edited version over: {full_path}")
                messages.success(request, "Edited image saved!")

                # Redirect to finalize, passing the original uploaded_id
                product_id = request.session.get('attach_product_id') or request.session.get('replace_product_id')
                if product_id:
                    return redirect(reverse('marketplace:finalize-product-image', kwargs={'product_id': product_id, 'uploaded_id': uploaded.id}))
                else:
                    messages.error(request, "No product context found.")
                    return redirect('marketplace:home')
            except Exception as e:
                 logger.error(f"Error saving edited image for {uploaded_id}: {e}", exc_info=True)
                 messages.error(request, "Could not save edited image.")
                 # Fall through to render editor again with error
        else:
            messages.error(request, "No edited image data received.")
            # Fall through to render editor again

    # For GET request or if POST failed validation/saving
    context = {
        'uploaded': uploaded,
        'processed_url': processed_url, # URL for the editor to load
    }
    return render(request, 'image_scanning/edit.html', context)