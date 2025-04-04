from django.db import models
from django.conf import settings
from marketplace.models import Product
from decimal import Decimal
import uuid

class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending Payment'),
        ('PAID', 'Paid'),
        ('FAILED', 'Payment Failed'),
        ('SHIPPED', 'Shipped'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('WALLET', 'Wallet'),
        ('XENDIT', 'Xendit'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # Use UUID for external refs
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='orders')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    currency = models.CharField(max_length=3, default='PHP') # ISO 4217 currency code
    country = models.CharField(max_length=2, default='PH') # ISO 3166-1 alpha-2 country code
    # Optional: Store specific channel used (useful for display)
    payment_channel = models.CharField(max_length=50, null=True, blank=True)
    # Optional: Store failure reason
    failure_reason = models.CharField(max_length=255, null=True, blank=True)
    
    # Xendit specific fields (optional, but helpful)
    xendit_payment_request_id = models.CharField(max_length=255, null=True, blank=True, unique=True, db_index=True)
    xendit_payment_id = models.CharField(max_length=255, null=True, blank=True, unique=True) # From callback

    def __str__(self):
        return f"Order {self.id} by {self.buyer.email if self.buyer else 'N/A'}"

    @property
    def items_list(self):
         return self.items.all() # Easier access in templates

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True) # Keep item even if product deleted
    # Seller is linked via the product at the time of order creation.
    # Storing it denormalized here is also an option if products can change sellers,
    # but linking via product.seller is usually sufficient if seller doesn't change.
    # If you need to store the seller explicitly at the time of sale:
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='sold_items')
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2) # Price at the time of order

    def __str__(self):
        return f"{self.quantity} x {self.product.title if self.product else 'Deleted Product'} in Order {self.order.id}"

    @property
    def subtotal(self):
        return self.price * self.quantity