from django.db import models
from django.conf import settings
from marketplace.models import Product
from django.templatetags.static import static

class UserOutfit(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    preview_image = models.ImageField(upload_to='outfit_previews/', null=True, blank=True)
    is_public = models.BooleanField(
            default=True,
            help_text="Make this outfit visible on your public profile?"
        )
    def __str__(self):
        return f"Outfit by {self.user.username} created at {self.created_at}"
    
    @property
    def item_count(self):
        """Returns the number of items in the outfit."""
        # Assumes related_name='items' on OutfitItem's ForeignKey to UserOutfit
        # You might need to adjust if the related_name is different or not set
        # Check if 'items' related manager exists before accessing it
        if hasattr(self, 'items'):
             return self.items.count()
        return 0 # Return 0 if 'items' doesn't exist (e.g., before initial save)


    @property
    def display_image_url(self):
        """
        Returns the URL for the best available preview image.
        Priority: AI Generated > Auto-generated 2D Preview > Placeholder
        Includes cache-busting parameter.
        """
        # Determine timestamp for cache busting (use updated_at if available)
        timestamp = self.updated_at.timestamp() if self.updated_at else timezone.now().timestamp()
        cache_bust = f"?v={int(timestamp)}" # Use int timestamp

        placeholder = static('images/placeholder.png') # Default placeholder

        # 1. Check AI result image
        ai_result_image_url = None
        if hasattr(self, 'ai_result') and self.ai_result and hasattr(self.ai_result, 'generated') and self.ai_result.generated:
             try:
                 # Check storage existence if possible/needed
                 if self.ai_result.generated.storage.exists(self.ai_result.generated.name):
                      ai_result_image_url = self.ai_result.generated.url
             except Exception: # Catch storage errors or ValueError from .url
                 pass # Fall through
        if ai_result_image_url:
             return ai_result_image_url + cache_bust

        # 2. Check auto-generated preview_image
        preview_image_url = None
        if self.preview_image and hasattr(self.preview_image, 'url'):
             try:
                 if self.preview_image.storage.exists(self.preview_image.name):
                     preview_image_url = self.preview_image.url
             except Exception:
                 pass # Fall through
        if preview_image_url:
             return preview_image_url + cache_bust

        # 3. Fallback to placeholder
        return placeholder

class OutfitItem(models.Model):
    modified_at = models.DateTimeField(auto_now=True)  
    outfit = models.ForeignKey(UserOutfit, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    position_x = models.FloatField()
    position_y = models.FloatField()
    scale = models.FloatField(default=1.0)
    z_index = models.IntegerField(default=0)

class OutfitRecommendation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    recommended_items = models.ManyToManyField(Product)
    criteria = models.TextField()  # e.g., "color: beige; material: cotton"
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Recommendation for {self.user.username} at {self.created_at}"

class OutfitAIResult(models.Model):
    outfit     = models.OneToOneField(UserOutfit, on_delete=models.CASCADE, related_name="ai_result")
    generated  = models.ImageField(upload_to="ai_outfits/")
    critique   = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"AI result for outfit {self.outfit_id}"
