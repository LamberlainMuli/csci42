# utils.py
import io
from rembg import remove
from PIL import Image, ImageEnhance
import numpy as np
import cv2

def read_image_from_django_file(django_file):
    """
    Reads a Django UploadedFile and converts it to a NumPy image.
    """
    django_file.seek(0)
    file_bytes = django_file.read()
    np_arr = np.frombuffer(file_bytes, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    return image

def remove_background_u2net(file_path):
    """
    Uses rembg (U2-Net based) to remove the background from the image at file_path.
    Returns a PIL Image (RGBA) after postprocessing to reduce shadow artifacts.
    """
    # Read input bytes directly from file
    with open(file_path, 'rb') as f:
        input_bytes = f.read()
    
    # Remove background using rembg (which uses U2-Net internally)
    output_bytes = remove(input_bytes)
    
    # Open the result as an RGBA image
    output_image = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    
    # --- Postprocessing: Reduce shadows ---
    # Convert output image to numpy array for processing
    output_np = np.array(output_image)
    
    # Separate RGB and alpha channels
    rgb = output_np[..., :3]
    alpha = output_np[..., 3]
    
    # Convert RGB to HSV
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    # Normalize V channel to [0,1]
    hsv[..., 2] = hsv[..., 2] / 255.0
    
    # For pixels with low brightness (possible shadows), boost brightness.
    # Here, for V < 0.4, apply gamma correction (gamma=0.8) to increase brightness.
    shadow_mask = hsv[..., 2] < 0.4
    hsv[..., 2][shadow_mask] = np.power(hsv[..., 2][shadow_mask], 0.8)
    
    # Rescale V back to [0,255]
    hsv[..., 2] = hsv[..., 2] * 255.0
    hsv = hsv.astype(np.uint8)
    
    # Convert back to RGB
    processed_rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    
    # Optionally, apply a slight contrast enhancement using PIL
    processed_image = Image.fromarray(processed_rgb)
    enhancer = ImageEnhance.Contrast(processed_image)
    processed_image = enhancer.enhance(1.1)  # Adjust factor as needed

    # Recombine with alpha channel
    processed_np = np.dstack([np.array(processed_image), alpha])
    final_image = Image.fromarray(processed_np, mode="RGBA")
    
    return final_image

def check_brightness(image, threshold=240):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mean_intensity = np.mean(gray)
    if mean_intensity > threshold:
        return "Warning: The image appears too bright. Please use soft lighting."
    return None

def check_contrast(image, threshold=30):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    std_dev = np.std(gray)
    if std_dev < threshold:
        return "Warning: The contrast seems low. Please ensure the clothing stands out from the background."
    return None

def process_image(image):
    """
    A naive demonstration using HSV thresholding.
    (Not used in our U2-Net approach.)
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    sensitivity = 60
    lower_white = np.array([0, 0, 255 - sensitivity])
    upper_white = np.array([255, sensitivity, 255])
    mask = cv2.inRange(hsv, lower_white, upper_white)
    mask_inv = cv2.bitwise_not(mask)
    result = cv2.bitwise_and(image, image, mask=mask_inv)
    contours, _ = cv2.findContours(mask_inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(result, contours, -1, (0, 255, 0), 2)
    return result


if __name__ == '__main__':
    # Test the background removal and shadow reduction function
    input_path = "tests/samples/sample2.jpg"
    output_path = "tests/outputs/sample2.png"
    img = remove_background_u2net(input_path)
    img.save(output_path)
    print(f"Saved output image: {output_path}")
