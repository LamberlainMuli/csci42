from wallet.models import Wallet, WalletTransaction
from django.db import transaction
from decimal import Decimal
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