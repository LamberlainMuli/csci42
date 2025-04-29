from django.contrib import admin
from .models import Cart, CartItem, SavedItem

class CartItemInline(admin.TabularInline):
    """Inline view for Cart Items within the Cart admin."""
    model = CartItem
    fields = ('product', 'quantity', 'added_at')
    readonly_fields = ('added_at',)
    extra = 0 # Don't show extra blank forms by default
    autocomplete_fields = ['product'] # Improve product selection

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'total_items_display', 'total_price_display')
    readonly_fields = ('created_at', 'user') # Usually don't change user or creation date
    search_fields = ('user__email', 'user__username')
    inlines = [CartItemInline] # Add inline view

    def total_items_display(self, obj):
        # Use the model property
        return obj.total_items
    total_items_display.short_description = 'Total Items' # Column header

    def total_price_display(self, obj):
        # Use the model property
        return f"₱{obj.total_price:.2f}" # Format as currency
    total_price_display.short_description = 'Total Price' # Column header

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'product', 'quantity', 'added_at')
    autocomplete_fields = ['product', 'cart'] # Autocomplete for FKs

@admin.register(SavedItem)
class SavedItemAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'saved_at')
    search_fields = ('user__email', 'user__username', 'product__title')
    list_filter = ('saved_at',)
    autocomplete_fields = ['user', 'product'] # Autocomplete for FKs