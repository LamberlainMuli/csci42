# mix_and_match/utils.py

import logging
from io import BytesIO
from django.core.files.base import ContentFile
from .image_generator import generate_outfit_image
# Import UserOutfit model within the function or at top if no circular dependency risk
# from .models import UserOutfit # Might cause issues if models.py imports utils

logger = logging.getLogger(__name__)

def update_outfit_preview_image(outfit):
    """
    Generates the 2D composite preview image for an outfit and saves it
    to the preview_image field.
    Args:
        outfit (UserOutfit): The UserOutfit instance to update.
    Returns:
        bool: True if the image was successfully generated and saved, False otherwise.
    """
    if not outfit or not outfit.pk:
        logger.warning("Attempted to generate preview for an invalid outfit instance.")
        return False

    logger.info(f"Attempting to generate 2D preview for Outfit ID: {outfit.id}")
    try:
        # Generate the image using the existing function
        image_buffer = generate_outfit_image(outfit)

        if image_buffer:
            # Create a Django ContentFile
            file_name = f"outfit_preview_{outfit.id}.png"
            content_file = ContentFile(image_buffer.getvalue(), name=file_name)

            # Save the file to the preview_image field
            # Using save=False first to avoid recursive calls if signals are involved later
            outfit.preview_image.save(file_name, content_file, save=False)
            # Now explicitly save the outfit instance with the updated field
            outfit.save(update_fields=['preview_image', 'updated_at'])

            logger.info(f"Successfully generated and saved preview for Outfit ID: {outfit.id}")
            return True
        else:
            logger.warning(f"generate_outfit_image returned None for Outfit ID: {outfit.id}. Cannot save preview.")
            return False

    except Exception as e:
        logger.error(f"Error generating or saving preview image for Outfit ID {outfit.id}: {e}", exc_info=True)
        return False