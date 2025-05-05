# mix_and_match/image_generator.py
from io import BytesIO
from PIL import Image, ImageDraw # ImageDraw might be useful later
from PIL.Image import Resampling
import os
from django.conf import settings # Access MEDIA_ROOT if needed
import logging # Optional: Use logging instead of print for production

# Optional: Get logger
logger = logging.getLogger(__name__)

# *** Ensure this matches the JS BASE_ITEM_WIDTH ***
BASE_WIDTH = 80 # This corresponds to the frontend's base item width before scaling
TARGET_CANVAS_WIDTH = 500
TARGET_CANVAS_HEIGHT = 500

def generate_outfit_image(outfit):
    """
    Given a UserOutfit instance, generate a composite PNG image of size 500x500.
    OutfitItems are sorted by z_index (ascending) so lower layers are drawn first.
    Each product's primary image is resized based on the outfit item's scale
    (relative to BASE_WIDTH) and pasted onto the canvas at the stored
    normalized position_x, position_y (relative to TARGET_CANVAS_WIDTH/HEIGHT).
    """
    # Use logger instead of print
    logger.info(f"Starting image generation for Outfit ID: {outfit.id}")
    canvas_size = (TARGET_CANVAS_WIDTH, TARGET_CANVAS_HEIGHT)
    # Start with a transparent background
    canvas_img = Image.new("RGBA", canvas_size, (255, 255, 255, 0))

    # Ensure items relation is loaded, order by z_index
    # Use prefetch_related for product images to optimize DB queries
    items = outfit.items.select_related('product').prefetch_related('product__images').order_by('z_index')
    if not items.exists():
        logger.warning(f"Outfit {outfit.id} has no items to generate.")
        # Return an empty (transparent) image
        output = BytesIO()
        canvas_img.save(output, format="PNG")
        output.seek(0)
        return output

    item_count = 0
    for item in items:
        logger.debug(f"Processing item {item.id} for outfit {outfit.id} (Product ID: {item.product_id}, Z: {item.z_index})")
        # Find primary image or first image efficiently from prefetched data
        primary_image_instance = None
        first_image_instance = None
        # Check if images were prefetched; otherwise, query
        product_images = item.product.images.all() # Access prefetched or query if needed

        for img in product_images:
            if img.is_primary:
                primary_image_instance = img
                break
            if first_image_instance is None:
                first_image_instance = img

        prod_img_instance = primary_image_instance or first_image_instance

        if not prod_img_instance or not prod_img_instance.image:
            logger.warning(f"Skipping item {item.id} (Product ID: {item.product_id}) - No valid image instance found.")
            continue

        try:
            # Get image path. Handle different storage backends potentially.
            # For default FileSystemStorage:
            if hasattr(settings, 'MEDIA_ROOT') and settings.MEDIA_ROOT:
                 image_path = os.path.join(settings.MEDIA_ROOT, prod_img_instance.image.name)
                 if not os.path.exists(image_path):
                    raise FileNotFoundError(f"Image file not found at path: {image_path}")
                 prod_img = Image.open(image_path).convert("RGBA") # Open from path
            else:
                 # Handle other storage (e.g., S3 might require reading from URL or storage object)
                 # This basic example assumes FileSystemStorage or image field providing accessible path/file
                 with prod_img_instance.image.open('rb') as f:
                      prod_img = Image.open(f).convert("RGBA") # Open from file field


            logger.debug(f"Opened image for item {item.id}: {prod_img_instance.image.name} (Size: {prod_img.size})")

        except FileNotFoundError as e:
            logger.error(f"ERROR finding image file for item {item.id}: {e}")
            continue # Skip this item
        except Exception as e:
            logger.error(f"ERROR opening image for item {item.id} (Path/Name: {getattr(prod_img_instance, 'image', 'N/A')}): {e}", exc_info=True)
            continue # Skip this item if image can't be opened

        # --- Calculate size based on scale and BASE_WIDTH ---
        original_width, original_height = prod_img.size
        if original_width <= 0 or original_height <= 0: # Check height too
            logger.warning(f"Skipping item {item.id} - Image has zero/negative dimensions: {prod_img.size}.")
            continue

        # This calculates the target pixel width based on the frontend's 80px base and saved scale
        new_pixel_width = int(BASE_WIDTH * item.scale)
        # Maintain aspect ratio based on the original image's dimensions
        aspect_ratio = float(original_height) / float(original_width)
        new_pixel_height = int(new_pixel_width * aspect_ratio)

        # Ensure minimum dimensions (e.g., 1x1) after scaling
        new_pixel_width = max(1, new_pixel_width)
        new_pixel_height = max(1, new_pixel_height)

        logger.debug(f"Resizing item {item.id}: Original={original_width}x{original_height}, Scale={item.scale:.3f}, Target={new_pixel_width}x{new_pixel_height}")

        try:
            # Use LANCZOS (or Resampling.BILINEAR for speed) for resizing
            prod_img_resized = prod_img.resize((new_pixel_width, new_pixel_height), Resampling.LANCZOS)
        except Exception as e:
            logger.error(f"ERROR resizing image for item {item.id} to {new_pixel_width}x{new_pixel_height}: {e}", exc_info=True)
            continue # Skip if resize fails

        # --- Calculate paste position ---
        # position_x and position_y are saved normalized (0-500 range from frontend)
        # We use these directly as the top-left coordinates for pasting onto the 500x500 canvas.
        paste_x = int(round(item.position_x)) # Round to nearest integer
        paste_y = int(round(item.position_y)) # Round to nearest integer
        paste_position = (paste_x, paste_y)
        logger.debug(f"Pasting item {item.id} at {paste_position} (Normalized Pos: {item.position_x:.2f}, {item.position_y:.2f}) with z-index {item.z_index}")


        # --- Paste onto canvas using alpha mask ---
        # This ensures transparency from the item image (prod_img_resized) is handled correctly.
        try:
            # The third argument (mask) ensures alpha blending
            canvas_img.paste(prod_img_resized, paste_position, prod_img_resized)
            item_count += 1
        except Exception as e:
            logger.error(f"ERROR pasting image for item {item.id} at {paste_position}: {e}", exc_info=True)
            # Continue processing other items even if one fails to paste

    logger.info(f"Finished generation. Pasted {item_count} items onto canvas for Outfit ID: {outfit.id}")

    # --- Save final image to BytesIO ---
    output = BytesIO()
    try:
        canvas_img.save(output, format="PNG")
        output.seek(0) # Rewind buffer to the beginning for reading
        logger.info(f"Successfully saved final canvas image to buffer for Outfit ID: {outfit.id}")
        return output
    except Exception as e:
        logger.error(f"ERROR saving final canvas image to buffer for Outfit ID: {outfit.id}: {e}", exc_info=True)
        return None # Indicate failure