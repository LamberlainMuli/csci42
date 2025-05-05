from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
import json
from django.http import FileResponse
from .models import UserOutfit, OutfitItem
from marketplace.models import Product, ProductImage 
from .image_generator import generate_outfit_image
import logging
from django.conf.urls.static import static
logger = logging.getLogger(__name__)
BASE_WIDTH = 80  # base container width at scale=1
import os
from django.views.decorators.http import require_POST
from django.contrib import messages
from .gemini_client import generate_outfit_image_with_critique
from django.core.files.base import ContentFile
from  .models import OutfitAIResult
from io import BytesIO
from django.http import Http404 
from django.urls import reverse
from django.db import transaction
from .utils import update_outfit_preview_image
@login_required
def create_outfit(request, outfit_id=None):
    
    """
    Handles both creation and editing of an outfit.
    If outfit_id is provided, existing outfit item data is passed as JSON.
    """
    outfit = None
    existing_items_json = "[]" # Default to empty JSON list for context

    # Try to fetch the outfit if an ID is provided (for editing)
    if outfit_id:
        outfit = get_object_or_404(UserOutfit, id=outfit_id, user=request.user)
        logger.info(f"Editing Outfit ID: {outfit_id}")
    else:
        logger.info("Creating new outfit.")

    # --- Handle POST request (Saving) ---
    if request.method == 'POST':
        print(request.POST)
        
        logger.debug(f"POST request received for outfit_id: {outfit_id}")
        try:
            outfit_data_str = request.POST.get('outfit_data', '[]')
            outfit_data = json.loads(outfit_data_str)
            logger.debug(f"Received outfit data: {outfit_data}")

            # --- Use transaction for saving outfit and items ---
            with transaction.atomic():
                if not outfit: # If creating new
                    outfit = UserOutfit.objects.create(user=request.user)
                    logger.info(f"Created new UserOutfit with ID: {outfit.id}")
                else: # If editing
                    # Clear existing items first WITHIN transaction
                    logger.debug(f"Deleting existing items for outfit {outfit.id} before saving new state.")
                    outfit.items.all().delete()

                # Prepare items for bulk create
                items_to_create = []
                for item_data in outfit_data:
                    if not all(k in item_data for k in ['product_id', 'x', 'y', 'scale']):
                        logger.warning(f"Skipping invalid item data: {item_data}")
                        continue
                    items_to_create.append(
                        OutfitItem(
                            outfit=outfit,
                            product_id=item_data['product_id'],
                            position_x=item_data['x'],
                            position_y=item_data['y'],
                            scale=item_data.get('scale', 1.0),
                            z_index=item_data.get('z_index', 0)
                        )
                    )

                # Bulk create items
                if items_to_create:
                    OutfitItem.objects.bulk_create(items_to_create)
                    items_created_count = len(items_to_create)
                    logger.info(f"Saved {items_created_count} items for outfit {outfit.id} within transaction.")
                else:
                     logger.info(f"No valid items to save for outfit {outfit.id}.")

                # Important: Assign the saved/created outfit instance to use AFTER the transaction
                outfit_instance_for_preview = outfit
                # Force update timestamp if editing, even if no items changed (unlikely but possible)
                if outfit_id:
                    outfit.save(update_fields=['updated_at'])


            # --- Generate Preview Image (AFTER transaction commits) ---
            if outfit_instance_for_preview:
                 logger.info(f"Attempting preview generation for Outfit ID: {outfit_instance_for_preview.id}")
                 # The helper function handles logging success/failure internally
                 preview_generated = update_outfit_preview_image(outfit_instance_for_preview)
                 if not preview_generated:
                      messages.warning(request, "Outfit saved, but the preview image could not be generated.")
                 else:
                     messages.success(request, "Outfit saved successfully.")
            else:
                 # Should not happen if logic is correct, but good to handle
                 messages.error(request, "Failed to get outfit instance after saving.")
                 logger.error("outfit_instance_for_preview was None after transaction commit.")


            # Redirect regardless of preview generation outcome (unless a critical error occurred earlier)
            return redirect('mix_and_match:preview_outfit', outfit_id=outfit_instance_for_preview.id)


        except json.JSONDecodeError:
            print(request.POST)
            logger.error(f"Failed to decode JSON data from outfit_data: {request.POST.get('outfit_data')}")
            # Redirect back to the edit/create page, potentially with an error message
            # Add Django messages framework if not already used: from django.contrib import messages
            # messages.error(request, "Failed to save outfit due to invalid data format.")
            # Redirect back to the same page (either create or edit URL)
            if outfit_id:
                 return redirect('mix_and_match:edit_outfit', outfit_id=outfit_id)
            else:
                 return redirect('mix_and_match:create_outfit')
        except Exception as e:
            logger.error(f"Unexpected error during POST: {e}", exc_info=True)
            # messages.error(request, "An unexpected error occurred while saving.")
            if outfit_id:
                 return redirect('mix_and_match:edit_outfit', outfit_id=outfit_id)
            else:
                 return redirect('mix_and_match:create_outfit')


    # --- Handle GET request (Displaying Create/Edit Page) ---
    else:
        logger.debug(f"GET request for outfit_id: {outfit_id}")

        # Prepare JSON data *only if* editing an existing outfit
        if outfit: # This means outfit_id was valid and outfit was fetched
            items_data = []
            for item in outfit.items.select_related('product').all().order_by('z_index'):
                items_data.append({
                    'product_id': item.product.id,
                    'position_x': item.position_x,
                    'position_y': item.position_y,
                    'scale': item.scale,
                    'z_index': item.z_index,
                })
            existing_items_json = json.dumps(items_data) # Convert list of dicts to JSON string
            logger.debug(f"Prepared JSON for existing items: {existing_items_json}")
        # If not editing (outfit is None), existing_items_json remains "[]" (default)

        # Fetch ALL available items for the user to choose from (Original Logic)
        available_items = Product.objects.filter(
            Q(is_public=True, is_sold=False, quantity__gt=0) | Q(seller=request.user, is_public=False)
        ).prefetch_related('images').distinct() # Use prefetch_related

        # Attach primary image (Original Logic - ensure JS can find img src)
        for item in available_items:
            # Use the prefetched data if available
            primary_image = None
            first_image = None
            # Access prefetched images if manager setup allows direct iteration,
            # otherwise .all() might trigger queries if not prefetched correctly
            image_qs = item.images.all()
            for img in image_qs:
                 if img.is_primary:
                     primary_image = img
                     break
                 if first_image is None:
                     first_image = img
            item.primary_image = primary_image or first_image # Attach image instance
            # Ensure JS has access to data-src for items being loaded
            if item.primary_image:
                item.primary_image_url = item.primary_image.image.url # Provide URL for JS data-src
            else:
                item.primary_image_url = None # Handle case where item has no image

        # Filter out items completely lacking an image for the available list display
        # This ensures `item.primary_image.image.url` works in the template loop
        displayable_available_items = [item for item in available_items if item.primary_image]

        # Get all available categories for the filter buttons (Original Logic)
        all_categories = list(Product.objects.filter(
            Q(is_public=True) | Q(seller=request.user, is_public=False),
            category__isnull=False # Explicitly check for non-null
        ).exclude(category__exact='').values_list('category', flat=True).distinct())
        all_categories = sorted([cat for cat in all_categories if cat]) # Ensure sorting after list creation


        context = {
            'available_items': displayable_available_items, # Pass items that have an image
            'outfit': outfit, # Pass the outfit object (or None if creating)
            'existing_items_json': existing_items_json, # Pass the JSON string or "[]"
            'all_categories': ['ALL'] + all_categories, # Categories for filter buttons
        }
        print(context)
        return render(request, 'mix_and_match/create_outfit.html', context)

@login_required
def edit_outfit(request, outfit_id):
    """
    Dedicated view for editing an existing outfit.
    Reuses create_outfit logic with an outfit_id.
    """
    return create_outfit(request, outfit_id=outfit_id)

@login_required
def preview_outfit(request, outfit_id):
    # Prefetch related product data including seller username for display/checks
    outfit = get_object_or_404(
        UserOutfit.objects.prefetch_related(
            'items__product__images', # Images for display
            'items__product__seller', # Seller info if needed
            'ai_result'               # Existing AI result
        ),
        id=outfit_id,
        user=request.user
    )

    outfit_items_for_template = []
    contains_unavailable_item = False # Flag to check if any item is sold/out of stock

    # Define the reference canvas size used during creation
    TARGET_CANVAS_WIDTH = 500.0 # Use float for calculations
    TARGET_CANVAS_HEIGHT = 500.0
    BASE_ITEM_WIDTH_ON_SAVE = 80.0 # Base width used when item position/scale was saved

    for item in outfit.items.all(): # Access prefetched items
        product = item.product
        primary_image = next((img for img in product.images.all() if img.is_primary), product.images.first())

        # Check if the product is currently unavailable (sold OR quantity <= 0)
        # Exclude the user's own private items from this check if desired
        is_unavailable = False
        if product.is_public and (product.is_sold or product.quantity <= 0):
             is_unavailable = True
             contains_unavailable_item = True # Mark that at least one item is unavailable

        outfit_items_for_template.append({
            'id': item.id,
            'product_id': product.id,
            'title': product.title,
            'primary_image_url': primary_image.image.url if primary_image and hasattr(primary_image, 'image') and primary_image.image else static('images/placeholder.png'),
            # Pass ORIGINAL saved data needed for JS scaling
            'saved_x': item.position_x,
            'saved_y': item.position_y,
            'saved_scale': item.scale,
            'z_index': item.z_index,
            'is_unavailable': is_unavailable, # Pass availability status
            'product_url': reverse('marketplace:product-detail', args=[product.pk]) # URL for linking
        })

    # Sort by z_index for correct layering in template loop
    outfit_items_for_template.sort(key=lambda x: x['z_index'])

    context = {
        'outfit': outfit,
        'outfit_items_data': outfit_items_for_template, # Pass the list of dictionaries
        'contains_unavailable_item': contains_unavailable_item,
        # Pass constants needed by JS
        'TARGET_CANVAS_WIDTH': TARGET_CANVAS_WIDTH,
        'BASE_ITEM_WIDTH_ON_SAVE': BASE_ITEM_WIDTH_ON_SAVE,
    }
    # AI result is prefetched, template can access via 'outfit.ai_result'
    return render(request, 'mix_and_match/preview_outfit.html', context)


@login_required
def download_outfit(request, outfit_id):
    """
    Generate and return the composite PNG image for the outfit.
    """
    outfit = get_object_or_404(UserOutfit, id=outfit_id, user=request.user)
    output = generate_outfit_image(outfit)
    filename = f"outfit_{outfit.id}.png"
    return FileResponse(output, as_attachment=True, filename=filename)


# --- NEW AI Generation View ---
@login_required
@require_POST # Make this POST only to prevent accidental triggers
def ai_generate_view(request, outfit_id):
    """Generates AI critique and image for an outfit."""
    outfit = get_object_or_404(UserOutfit, id=outfit_id, user=request.user)
    logger.info(f"AI Generation requested for Outfit {outfit_id} by User {request.user.email}")

    # Call the Gemini client function
    generated_image, critique, error_message = generate_outfit_image_with_critique(outfit)

    if error_message:
        messages.error(request, f"AI Generation Failed: {error_message}")
    else:
        if critique or generated_image:
            try:
                ai_result, created = OutfitAIResult.objects.update_or_create(
                    outfit=outfit,
                    defaults={
                        'critique': critique or "Critique not generated.",
                        # Clear old image before saving new one if update_or_create updates
                        'generated': None
                    }
                )
                # Save the new image if generated
                if generated_image:
                     img_buffer = BytesIO()
                     generated_image.save(img_buffer, format='PNG')
                     ai_result.generated.save(f"ai_outfit_{outfit.id}.png", ContentFile(img_buffer.getvalue()), save=True)
                     logger.info(f"Saved generated AI image for Outfit {outfit.id}")

                messages.success(request, "AI critique and image generated successfully!")
            except Exception as e:
                logger.error(f"Failed to save AI result for Outfit {outfit.id}: {e}", exc_info=True)
                messages.error(request, "AI generated results but failed to save them.")
        else:
             messages.warning(request, "AI generation completed but returned no image or critique.")

    return redirect('mix_and_match:preview_outfit', outfit_id=outfit_id)

@login_required
def recommendations(request):
    category = request.GET.get('category')
    condition = request.GET.get('condition')
    recommended_items = Product.objects.filter(is_public=True)
    if category:
        recommended_items = recommended_items.filter(category=category)
    if condition:
        recommended_items = recommended_items.filter(condition=condition)
    recommended_items = recommended_items.order_by('?')[:10]

    categories = Product.objects.filter(is_public=True).values_list('category', flat=True).distinct()
    conditions = Product.objects.filter(is_public=True).values_list('condition', flat=True).distinct()

    context = {
        'recommended_items': recommended_items,
        'categories': categories,
        'conditions': conditions,
        'current_category': category,
        'current_condition': condition,
    }
    return render(request, 'mix_and_match/recommendations.html', context)


# --- NEW Delete Outfit View ---
@login_required
@require_POST # Ensure deletion happens via POST
def delete_outfit(request, outfit_id):
    """Deletes a user's saved outfit."""
    outfit = get_object_or_404(UserOutfit, id=outfit_id, user=request.user)
    try:
        outfit_id_short = str(outfit.id)[:8]
        # Optional: Delete associated preview image file first
        if outfit.preview_image:
            if os.path.exists(outfit.preview_image.path):
                 os.remove(outfit.preview_image.path)
        # Optional: Delete associated AI result image file first
        if hasattr(outfit, 'ai_result') and outfit.ai_result.generated:
             if os.path.exists(outfit.ai_result.generated.path):
                 os.remove(outfit.ai_result.generated.path)

        outfit.delete()
        messages.success(request, f"Outfit ({outfit_id_short}...) deleted successfully.")
        logger.info(f"Deleted outfit {outfit_id} for user {request.user.email}")
    except Exception as e:
        logger.error(f"Error deleting outfit {outfit_id}: {e}", exc_info=True)
        messages.error(request, "Could not delete the outfit.")
        # Redirect back to profile or wherever the delete was triggered from
        return redirect('user:profile')

    return redirect('user:profile') # Redirect to profile after successful delete


from django.http import JsonResponse 
@login_required
@require_POST # Ensure this view only accepts POST requests
def toggle_outfit_privacy(request, outfit_id):
    """Toggles the is_public status of a user's outfit."""
    outfit = get_object_or_404(UserOutfit, id=outfit_id, user=request.user) # Ensure ownership

    try:
        # Toggle the boolean field
        outfit.is_public = not outfit.is_public
        outfit.save(update_fields=['is_public', 'updated_at']) # Update only necessary fields + timestamp
        logger.info(f"Toggled privacy for Outfit {outfit.id} to is_public={outfit.is_public} by User {request.user.email}")

        # Return JSON response for AJAX request
        return JsonResponse({
            'status': 'success',
            'is_public': outfit.is_public,
            'message': f'Outfit is now {"public" if outfit.is_public else "private"}.'
        })
    except Exception as e:
         logger.error(f"Error toggling privacy for Outfit {outfit.id}: {e}", exc_info=True)
         return JsonResponse({'status': 'error', 'error': 'Could not update outfit privacy.'}, status=500)
     
def public_outfit_preview(request, outfit_id):
    """Displays a public, read-only view of an outfit."""
    outfit = get_object_or_404(
        UserOutfit.objects.select_related('user__profile'), # Fetch user and profile
        id=outfit_id
    )

    # Check if the outfit is public OR if the logged-in user is the owner
    can_view = outfit.is_public or (request.user.is_authenticated and request.user == outfit.user)

    if not can_view:
        raise Http404("Outfit not found or is private.")

    # Fetch items and related product data
    outfit_items = outfit.items.select_related(
        'product__seller', # Needed if linking to product
        'product'
    ).prefetch_related(
        'product__images' # For primary image
    ).order_by('z_index')

    outfit_items_for_template = []
    contains_unavailable_item = False # Flag to check if any item is sold/out of stock

    # Define constants (same as preview_outfit)
    TARGET_CANVAS_WIDTH = 500.0
    BASE_ITEM_WIDTH_ON_SAVE = 80.0

    for item in outfit_items:
        product = item.product
        primary_image = next((img for img in product.images.all() if img.is_primary), product.images.first())

        # Check product availability (only relevant if the product itself is public)
        is_unavailable = False
        if product.is_public and (product.is_sold or product.quantity <= 0):
            is_unavailable = True
            contains_unavailable_item = True

        # Prepare item data for template rendering
        outfit_items_for_template.append({
            'id': item.id,
            'product_id': product.id,
            'title': product.title,
            'primary_image_url': primary_image.image.url if primary_image and hasattr(primary_image, 'image') and primary_image.image else static('images/placeholder.png'),
            'saved_x': item.position_x,
            'saved_y': item.position_y,
            'saved_scale': item.scale,
            'z_index': item.z_index,
            'is_unavailable': is_unavailable,
            # Only provide product URL if the product is public
            'product_url': reverse('marketplace:product-detail', args=[product.pk]) if product.is_public else None,
            'is_product_public': product.is_public, # Flag if the item itself is public
            'category': product.get_category_display() or 'N/A', # Get category display name
        })

    context = {
        'outfit': outfit,
        'outfit_owner': outfit.user, # Pass the owner user object
        'outfit_items_data': outfit_items_for_template,
        'contains_unavailable_item': contains_unavailable_item,
        'TARGET_CANVAS_WIDTH': TARGET_CANVAS_WIDTH,
        'BASE_ITEM_WIDTH_ON_SAVE': BASE_ITEM_WIDTH_ON_SAVE,
        'is_public_view': True, # Flag for the template
    }
    return render(request, 'mix_and_match/public_outfit_preview.html', context)