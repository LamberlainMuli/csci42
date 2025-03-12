# ukay/image_scanning/views.py
import os
import base64
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.core.files.base import ContentFile
from .forms import UploadedImageForm, ProcessedClothingItemForm
from .models import UploadedImage, ProcessedClothingItem
from marketplace.models import Product, ProductImage
from . import utils

@login_required
def scanning_guide(request):
    """
    Displays instructions for capturing clothing images.
    """
    return render(request, 'image_scanning/scanning_guide.html')

@login_required
def upload_image(request):
    """
    Traditional file upload for an image.
    """
    if request.method == 'POST':
        form = UploadedImageForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.save(commit=False)
            uploaded.user = request.user
            uploaded.save()
            # Once user has uploaded, redirect to process_image
            return redirect('image_scanning:process_image', uploaded_id=uploaded.id)
    else:
        form = UploadedImageForm()
    return render(request, 'image_scanning/upload.html', {'form': form})

@login_required
def process_image(request, uploaded_id):
    """
    Process the uploaded image using a U2-Net based background removal (rembg).
    Display the processed preview and allow the user to confirm or retake.
    If the session has a product id (either attach_product_id or replace_product_id),
    redirect to finalize product image attachment.
    """
    uploaded = get_object_or_404(UploadedImage, id=uploaded_id, user=request.user)

    if request.method == 'POST':
        if 'confirm' in request.POST:
            # Check for product id stored in session
            attach_product_id = request.session.get('attach_product_id')
            replace_product_id = request.session.get('replace_product_id')
            product_id = attach_product_id or replace_product_id
            if product_id:
                return redirect('marketplace:finalize-product-image', product_id=product_id, uploaded_id=uploaded.id)
            else:
                messages.error(request, "No product found to attach this image to.")
                return redirect('image_scanning:scanning_guide')
        elif 'retake' in request.POST:
            return redirect('image_scanning:upload_image')

    try:
        processed_image_pil = utils.remove_background_u2net(uploaded.original_image.path)
    except Exception as e:
        messages.error(request, f"Error processing image: {str(e)}")
        return redirect('image_scanning:scanning_guide')

    # Save the processed image as PNG (since transparency is needed)
    dir_path = os.path.dirname(uploaded.original_image.path)
    base_name = os.path.splitext(os.path.basename(uploaded.original_image.path))[0]
    processed_filename = f"processed_{base_name}.png"
    processed_path = os.path.join(dir_path, processed_filename)
    processed_image_pil.save(processed_path)

    # Build the URL for the processed image.
    original_url = uploaded.original_image.url  # e.g., /media/image_scanning/raw/username/filename.jpg
    processed_url = os.path.join(os.path.dirname(original_url), processed_filename)

    context = {
        'uploaded': uploaded,
        'processed_url': processed_url,
    }
    return render(request, 'image_scanning/process.html', context)

@login_required
def edit_image(request, uploaded_id):
    """
    Renders an image editor with a brush tool for manual corrections.
    On POST, receives the base64-encoded edited image and saves it.
    After saving, it redirects to finalize the product image attachment.
    """
    uploaded = get_object_or_404(UploadedImage, id=uploaded_id, user=request.user)
    dir_path = os.path.dirname(uploaded.original_image.path)
    base_name = os.path.splitext(os.path.basename(uploaded.original_image.path))[0]
    processed_filename = f"processed_{base_name}.png"  # force PNG
    base_url = os.path.dirname(uploaded.original_image.url).rstrip('/')
    processed_url = base_url + '/' + processed_filename

    if request.method == 'POST':
        edited_data = request.POST.get('edited_image')
        if edited_data:
            format, imgstr = edited_data.split(';base64,')
            ext = format.split('/')[-1]
            new_filename = "edited_" + base_name + f".{ext}"
            new_path = os.path.join(dir_path, new_filename)
            image_bytes = base64.b64decode(imgstr)
            with open(new_path, 'wb') as f:
                f.write(image_bytes)
            messages.success(request, "Edited image saved successfully!")
            # Redirect to finalize product image attachment if product id is available
            product_id = request.session.get('attach_product_id') or request.session.get('replace_product_id')
            if product_id:
                return redirect('marketplace:finalize-product-image', product_id=product_id, uploaded_id=uploaded.id)
            else:
                messages.error(request, "No product found to attach this image to.")
                return redirect('image_scanning:scanning_guide')
        else:
            messages.error(request, "No edited image data received.")
            return redirect('image_scanning:edit_image', uploaded_id=uploaded.id)

    context = {
        'uploaded': uploaded,
        'processed_url': processed_url,
    }
    return render(request, 'image_scanning/edit.html', context)
