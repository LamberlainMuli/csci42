from django.contrib import admin
from .models import Wallet, WalletTransaction

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    """Admin configuration for the Wallet model."""
    list_display = ('user', 'balance', 'updated_at')
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('created_at', 'updated_at', 'balance') # Balance modified via transactions

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    """Admin configuration for the WalletTransaction model."""
    list_display = ('timestamp', 'wallet', 'transaction_type', 'amount', 'related_order_id')
    list_filter = ('transaction_type', 'timestamp')
    search_fields = ('wallet__user__email', 'wallet__user__username', 'related_order_id', 'description')
    ordering = ('-timestamp',)
    readonly_fields = ('timestamp',) # Typically shouldn't change timestamp