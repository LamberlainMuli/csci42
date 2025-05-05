# wallet/forms.py
from django import forms
from decimal import Decimal

class WalletTopUpForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('50.00'), # Example minimum
        widget=forms.NumberInput(attrs={'step': '10.00', 'placeholder': 'PHP 50.00 minimum'}),
        label="Top-Up Amount (PHP)",
        help_text="Enter the amount you wish to add to your wallet."
    )
    # Define available Xendit channels for top-up
    # You can customize this list as needed
    XENDIT_TOPUP_CHANNELS = [
        ("", "--- Select Payment Method ---"), # Placeholder
        ("EWALLET_GCASH", "GCash"),
        ("EWALLET_PAYMAYA", "Maya"),
        # ("EWALLET_GRABPAY", "GrabPay"), # Often requires mobile#
        # ("EWALLET_SHOPEEPAY", "ShopeePay"), # Might need specific setup
        ("VIRTUAL_ACCOUNT_BPI", "BPI Virtual Account"),
        ("VIRTUAL_ACCOUNT_BDO", "BDO Virtual Account"),
        ("VIRTUAL_ACCOUNT_UNIONBANK", "Unionbank Virtual Account"),
        ("CARD_CARD", "Credit / Debit Card"),
        # Add OTC channels if desired
        # ("OTC_7ELEVEN", "7-Eleven"),
    ]
    xendit_channel = forms.ChoiceField(
        choices=XENDIT_TOPUP_CHANNELS,
        required=True,
        label="Payment Method",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount and amount <= 0:
             raise forms.ValidationError("Amount must be positive.")
        # Add max amount validation if needed
        # if amount and amount > 50000:
        #     raise forms.ValidationError("Maximum top-up amount is PHP 50,000.")
        return amount