from django.db import models
from django.contrib.auth.models import User

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

    seller = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    size = models.CharField(max_length=20)
    color = models.CharField(max_length=50)
    material = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    condition = models.CharField(max_length=3, choices=CONDITION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_sold = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} - {self.get_category_display()}"

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/')
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"Image for {self.product.title}"