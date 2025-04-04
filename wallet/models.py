from django.db import models
from django.conf import settings
from django.db import transaction
from decimal import Decimal

class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet for {self.user.email} (Balance: {self.balance})"

class WalletTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('PURCHASE', 'Purchase'), # Buyer paying with wallet
        ('SALE', 'Sale'),         # Seller receiving funds
        ('REFUND', 'Refund'),
    ]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2) # Can be positive (credit) or negative (debit)
    related_order_id = models.CharField(max_length=255, null=True, blank=True) # Link to Order if applicable
    description = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} of {self.amount} for {self.wallet.user.email} at {self.timestamp}"

# Keep the utility functions here or move to services.py
# Utility functions (consider placing in wallet/utils.py or services.py)
def add_funds(user, amount, transaction_type='DEPOSIT', description=None, related_order_id=None):
    if amount <= 0:
        raise ValueError("Amount must be positive.")
    # Use get_or_create to handle cases where wallet might not exist yet
    wallet, created = Wallet.objects.get_or_create(user=user)
    if created:
        print(f"Created new wallet for user {user.email}")

    with transaction.atomic():
        # Retrieve wallet again inside transaction for locking
        wallet_locked = Wallet.objects.select_for_update().get(user=user)
        wallet_locked.balance += Decimal(amount)
        wallet_locked.save()
        WalletTransaction.objects.create(
            wallet=wallet_locked,
            transaction_type=transaction_type,
            amount=Decimal(amount),
            description=description,
            related_order_id=related_order_id
        )
    # Return the original wallet instance (or the locked one, doesn't matter much here)
    return wallet

def deduct_funds(user, amount, transaction_type='PURCHASE', description=None, related_order_id=None):
    if amount <= 0:
        raise ValueError("Amount must be positive.")
    # Use get_or_create to ensure wallet exists
    wallet, created = Wallet.objects.get_or_create(user=user)
    if created:
         # If wallet was just created, balance is 0, so deduction will fail
         raise ValueError("Insufficient funds (new wallet).")

    with transaction.atomic():
        # Retrieve wallet again inside transaction for locking
        wallet_locked = Wallet.objects.select_for_update().get(user=user)
        if wallet_locked.balance < Decimal(amount):
            raise ValueError(f"Insufficient funds. Current balance: {wallet_locked.balance}, required: {amount}")
        wallet_locked.balance -= Decimal(amount)
        wallet_locked.save()
        # Record debit as a negative amount for clarity, or keep positive and rely on type
        WalletTransaction.objects.create(
            wallet=wallet_locked,
            transaction_type=transaction_type,
            amount=-Decimal(amount), # Using negative for debits
            description=description,
            related_order_id=related_order_id
        )
    # Return the original wallet instance
    return wallet