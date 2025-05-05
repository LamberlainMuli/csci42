# cart/models.py
from django.db import models
from django.conf import settings
from marketplace.models import Product

class Cart(models.Model):
    """One cart per user."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart for {self.user.email}"

    @property
    def total_items(self):
        """Sum of quantities for all items in the cart."""
        return sum(item.quantity for item in self.cart_items.all())

    @property
    def total_price(self):
        """Sum of (price * quantity) for items in the cart."""
        return sum(item.product.price * item.quantity for item in self.cart_items.all())

class CartItem(models.Model):
    """Individual product item in the user's cart."""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='cart_items')
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='in_carts' 
    )
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.title} x {self.quantity}"

class SavedItem(models.Model):
    """Model for 'Saved' or 'Wishlist' items."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='saved_by_users' 
    )
    saved_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Saved by {self.user.email}: {self.product.title}"
