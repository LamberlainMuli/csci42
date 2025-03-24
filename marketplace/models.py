from django.db import models
from django.conf import settings
from django.urls import reverse

class Product(models.Model):
    CATEGORY_CHOICES = [
        ('TOPS', 'Tops'),
        ('BOTTOMS', 'Bottoms'),
        ('DRESSES', 'Dresses'),
        ('OUTERWEAR', 'Outerwear'),
        ('ACCESSORIES', 'Accessories'),
    ]

    CONDITION_CHOICES = [
        ('NWT', 'New with tags'),
        ('EU', 'Excellent used'),
        ('GU', 'Good used'),
        ('FU', 'Fair used'),
    ]

    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    # Price is optional for private products.
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)  # New field: available quantity
    size = models.CharField(max_length=20, null=True, blank=True)
    color = models.CharField(max_length=50, null=True, blank=True)
    material = models.CharField(max_length=100, null=True, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, null=True, blank=True)
    condition = models.CharField(max_length=3, choices=CONDITION_CHOICES, null=True, blank=True)
    is_sold = models.BooleanField(default=False)
    is_public = models.BooleanField(default=True, help_text="Uncheck for a private item (personal closet)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title}"

    def get_absolute_url(self):
        return reverse('marketplace:product-detail', kwargs={'pk': self.pk})

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/')
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"Image for {self.product.title}"
