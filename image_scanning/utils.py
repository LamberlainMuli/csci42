# image_scanning/utils.py
import io
import logging
from rembg import remove
from PIL import Image, ImageEnhance, ImageOps # Ensure ImageOps is imported
import numpy as np
import cv2

logger = logging.getLogger(__name__)

def read_image_from_django_file(django_file):
    django_file.seek(0)
    file_bytes = django_file.read()
    np_arr = np.frombuffer(file_bytes, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    return image

def remove_background_and_optimize(file_path, max_dimension=1024):
    """
    Removes background, applies post-processing, resizes, and returns
    an optimized PIL Image object (RGBA).
    """
    logger.info(f"Starting background removal for: {file_path}")
    try:
        with open(file_path, 'rb') as f: input_bytes = f.read()

        # Use rembg for background removal
        output_bytes = remove(input_bytes)
        if not output_bytes: raise ValueError("Background removal returned empty output.")
        output_image = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
        logger.info("Background removal successful.")

        # Optional Post-processing (keep if helpful)
        logger.debug("Applying post-processing...")
        output_np = np.array(output_image); rgb = output_np[...,:3]; alpha = output_np[...,3]
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32); hsv[...,2] /= 255.0
        shadow_mask = hsv[...,2] < 0.4; hsv[...,2][shadow_mask] = np.power(hsv[...,2][shadow_mask], 0.8)
        hsv[...,2] *= 255.0; hsv = hsv.astype(np.uint8); processed_rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
        processed_image = Image.fromarray(processed_rgb); enhancer = ImageEnhance.Contrast(processed_image)
        processed_image = enhancer.enhance(1.1); final_image_np = np.dstack([np.array(processed_image), alpha])
        final_image = Image.fromarray(final_image_np, mode="RGBA")
        logger.debug("Post-processing applied.")

        # --- Resize image ---
        logger.debug(f"Resizing image to max dimension: {max_dimension}px")
        resized_image = final_image.copy()
        resized_image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS) # High-quality downscaling
        logger.info(f"Image resized to: {resized_image.size}")

        return resized_image # Return the resized PIL image

    except Exception as e:
        logger.error(f"Error in remove_background_and_optimize for {file_path}: {e}", exc_info=True)
        raise

# Keep check_brightness and check_contrast if used
def check_brightness(image, threshold=240):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY); mean_intensity = np.mean(gray)
    if mean_intensity > threshold: return "Warning: Image too bright."
    return None

def check_contrast(image, threshold=30):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY); std_dev = np.std(gray)
    if std_dev < threshold: return "Warning: Low contrast."
    return None