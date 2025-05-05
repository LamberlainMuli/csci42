# wallet/admin.py
from django.contrib import admin
from .models import Wallet, WalletTransaction

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'balance', 'updated_at')
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('id', 'user', 'created_at', 'updated_at', 'balance')

    @admin.display(description='User Email', ordering='user__email')
    def user_email(self, obj):
        return obj.user.email

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id', # Display the new UUID
        'timestamp',
        'wallet_user_email',
        'transaction_type',
        'status', # Display status
        'amount',
        'external_reference',
        'related_order_id',
    )
    list_filter = ('transaction_type', 'status', 'timestamp') # Add status filter
    search_fields = (
        'id__iexact', # Search by UUID
        'wallet__user__email',
        'wallet__user__username',
        'related_order_id',
        'external_reference',
        'description'
    )
    ordering = ('-timestamp',)
    # Make most fields read-only in admin as they are system-generated
    readonly_fields = ('id', 'wallet', 'timestamp', 'amount', 'transaction_type', 'status', 'external_reference', 'related_order_id')
    list_select_related = ['wallet', 'wallet__user'] # Optimize user lookup

    @admin.display(description='User Email', ordering='wallet__user__email')
    def wallet_user_email(self, obj):
        return obj.wallet.user.email