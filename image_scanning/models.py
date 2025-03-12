# image_scanning/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from marketplace.models import Product  # Adjust import if your Product is located elsewhere

def upload_to_raw(instance, filename):
    return f'image_scanning/raw/{instance.user.username}/{filename}'

def upload_to_processed(instance, filename):
    return f'image_scanning/processed/{instance.user.username}/{filename}'

class UploadedImage(models.Model):
    """
    Stores the raw user-uploaded image before background removal and processing.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='uploaded_images'
    )
    original_image = models.ImageField(upload_to=upload_to_raw)
    upload_date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Raw image by {self.user.username} on {self.upload_date:%Y-%m-%d}"

class ProcessedClothingItem(models.Model):
    """
    Represents the final, processed clothing image.
    Optionally linked to a Product or stored just for the user.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='processed_items'
    )
    processed_image = models.ImageField(upload_to=upload_to_processed)
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_variants'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        product_str = f" for Product {self.product.title}" if self.product else ""
        return f"Processed image by {self.user.username}{product_str}"
