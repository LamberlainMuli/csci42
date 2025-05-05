# wallet/models.py
import uuid # Import uuid
from django.db import models
from django.conf import settings
from django.db import transaction, IntegrityError
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class Wallet(models.Model):
    # No changes needed here
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet for {self.user.email} (Balance: {self.balance})"

class WalletTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('DEPOSIT', 'Deposit'),         # Successful deposit completion
        ('WITHDRAWAL', 'Withdrawal'),   # Successful withdrawal
        ('PURCHASE', 'Purchase'),       # Buyer paying with wallet (debit)
        ('SALE', 'Sale'),               # Seller receiving funds (credit)
        ('REFUND', 'Refund'),           # Refunding a purchase/sale
        ('TOPUP_PENDING', 'Top-Up Pending'), # Initial state for Xendit top-up
        ('TOPUP_FAILED', 'Top-Up Failed'),   # If Xendit initiation or webhook fails
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),       # For external transactions awaiting confirmation (like top-up)
        ('COMPLETED', 'Completed'),   # Transaction finished successfully
        ('FAILED', 'Failed'),         # Transaction failed
        # ('CANCELLED', 'Cancelled'), # Optional
    ]

    # Add a UUID primary key for unique reference
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    # Adjust choices and add default/max_length
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPE_CHOICES,
        # Default type might not be needed if always set explicitly
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='COMPLETED', # Default to completed for direct actions like PURCHASE/SALE
        db_index=True       # Index status for faster lookups of PENDING
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2
        # Amount is always positive, type indicates direction (or use negative for debits)
    )
    # This can store the Xendit Payment ID or other external refs if needed
    external_reference = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    related_order_id = models.CharField(max_length=255, null=True, blank=True) # Keep for linking to actual Orders
    description = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
         return f"[{self.id}] {self.get_transaction_type_display()}/{self.get_status_display()} ({self.amount}) for {self.wallet.user.email}"

# --- Utility Functions (Adjusted) ---

# This function now focuses SOLELY on INCREASING the balance and logging the FINAL transaction
# It assumes the caller (e.g., webhook, distribute_payment) has already validated the action
# and handles the corresponding PENDING transaction status update separately if needed.
def add_funds(user, amount, transaction_type='DEPOSIT', description=None, related_order_id=None, external_reference=None):
    """
    Atomically adds funds to a user's wallet and logs a COMPLETED transaction.
    Assumes wallet exists. Should be called AFTER payment is confirmed.
    """
    if amount <= 0:
        # Allow zero amount? Maybe for status updates? For now, require positive.
        raise ValueError("Add funds amount must be positive.")

    try:
        with transaction.atomic():
            # Lock the wallet row
            wallet_locked = Wallet.objects.select_for_update().get(user=user)
            wallet_locked.balance += Decimal(amount)
            wallet_locked.save(update_fields=['balance', 'updated_at'])

            # Create the final COMPLETED transaction log
            WalletTransaction.objects.create(
                wallet=wallet_locked,
                transaction_type=transaction_type, # e.g., DEPOSIT, SALE, REFUND
                status='COMPLETED', # Mark this record as completed
                amount=Decimal(amount), # Store positive amount for credits
                description=description,
                related_order_id=related_order_id,
                external_reference=external_reference # e.g., Xendit Payment ID
            )
            logger.info(f"Successfully added {amount} to wallet for {user.email}. New balance: {wallet_locked.balance}. Type: {transaction_type}")
            return wallet_locked # Return updated wallet
    except Wallet.DoesNotExist:
        logger.error(f"CRITICAL: Wallet not found for user {user.email} during add_funds.")
        # Raise a more specific error or handle as appropriate
        raise ValueError(f"Wallet does not exist for user {user.email}.")
    except IntegrityError as e:
         logger.error(f"Database integrity error during add_funds for {user.email}: {e}", exc_info=True)
         raise # Re-raise to ensure transaction rollback if needed
    except Exception as e:
         logger.error(f"Unexpected error during add_funds for {user.email}: {e}", exc_info=True)
         raise # Re-raise

# This function deducts funds and logs the transaction
def deduct_funds(user, amount, transaction_type='PURCHASE', description=None, related_order_id=None, external_reference=None):
    """
    Atomically deducts funds from a user's wallet and logs a COMPLETED transaction.
    Raises ValueError if insufficient funds.
    """
    if amount <= 0:
        raise ValueError("Deduct funds amount must be positive.")

    try:
        with transaction.atomic():
            # Lock the wallet row
            wallet_locked = Wallet.objects.select_for_update().get(user=user)

            if wallet_locked.balance < Decimal(amount):
                raise ValueError(f"Insufficient funds. Balance: {wallet_locked.balance}, Required: {amount}")

            wallet_locked.balance -= Decimal(amount)
            wallet_locked.save(update_fields=['balance', 'updated_at'])

            # Create the COMPLETED transaction log for the deduction
            WalletTransaction.objects.create(
                wallet=wallet_locked,
                transaction_type=transaction_type, # e.g., PURCHASE, WITHDRAWAL
                status='COMPLETED',
                amount=Decimal(amount), # Store positive amount, type indicates debit
                # OR store negative: amount=-Decimal(amount),
                description=description,
                related_order_id=related_order_id,
                external_reference=external_reference
            )
            logger.info(f"Successfully deducted {amount} from wallet for {user.email}. New balance: {wallet_locked.balance}. Type: {transaction_type}")
            return wallet_locked
    except Wallet.DoesNotExist:
        logger.error(f"CRITICAL: Wallet not found for user {user.email} during deduct_funds.")
        raise ValueError(f"Wallet does not exist for user {user.email}.")
    except IntegrityError as e:
         logger.error(f"Database integrity error during deduct_funds for {user.email}: {e}", exc_info=True)
         raise
    except Exception as e:
         # Catch potential ValueError from insufficient funds here too if needed,
         # but it's better to let it propagate.
         logger.error(f"Unexpected error during deduct_funds for {user.email}: {e}", exc_info=True)
         raise