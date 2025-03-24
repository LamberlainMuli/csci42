from django.db import models
from django.conf import settings
from marketplace.models import Product

class UserOutfit(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    preview_image = models.ImageField(upload_to='outfit_previews/', null=True, blank=True)

    def __str__(self):
        return f"Outfit by {self.user.username} created at {self.created_at}"

class OutfitItem(models.Model):
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
