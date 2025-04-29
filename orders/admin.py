from django.contrib import admin
from .models import Order, OrderItem

class OrderItemInline(admin.TabularInline):
    """Inline view for Order Items within the Order admin page."""
    model = OrderItem
    # Fields to display in the inline table
    fields = ('product', 'seller', 'quantity', 'price', 'subtotal')
    readonly_fields = ('product', 'seller', 'quantity', 'price', 'subtotal') # Make fields read-only in Order view
    extra = 0 # Don't show extra blank forms
    can_delete = False # Usually don't delete items from a placed order via admin

    def subtotal(self, obj):
        # Method to display the calculated subtotal
        return obj.subtotal
    subtotal.short_description = 'Subtotal' # Column header

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Admin configuration for the Order model."""
    list_display = (
        'id',
        'buyer_email',
        'status',
        'payment_method',
        'payment_channel',
        'total_amount',
        'created_at',
    )
    list_filter = ('status', 'payment_method', 'payment_channel', 'created_at')
    search_fields = ('id__iexact', 'buyer__email', 'buyer__username', 'xendit_payment_request_id', 'xendit_payment_id')
    ordering = ('-created_at',)
    readonly_fields = (
        'id',
        'buyer',
        'total_amount',
        'created_at',
        'updated_at',
        'xendit_payment_request_id',
        'xendit_payment_id',
        'currency',
        'country',
        'failure_reason' # Usually failure reason is system-set
    )
    inlines = [OrderItemInline] # Add the inline view for items

    def buyer_email(self, obj):
        # Method to display buyer's email safely
        return obj.buyer.email if obj.buyer else 'N/A'
    buyer_email.short_description = 'Buyer Email' # Column header

    # Make items read-only when viewing an existing order
    def get_readonly_fields(self, request, obj=None):
        if obj: # obj is not None, so this is an existing order being edited/viewed
             # Combine base readonly fields with payment method/channel if order exists
             return self.readonly_fields + ('payment_method', 'payment_channel')
        return self.readonly_fields