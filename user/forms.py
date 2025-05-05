# user/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm # Import UserChangeForm too
from .models import CustomUser, UserProfile
from django.core.validators import RegexValidator # Import if needed for specific validation
from decimal import Decimal # Import Decimal for weight/height validation
class CustomUserCreationForm(UserCreationForm):
    """Form for creating new users, removing the role selection."""
    # Inherit email/username/password fields from UserCreationForm
    # Specify fields explicitly if UserCreationForm doesn't include email by default
    email = forms.EmailField(required=True)
    username = forms.CharField(required=True, max_length=150)

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        # Include fields required for signup + email + username
        # Exclude 'role'
        fields = ('email', 'username')

    # No need for the old save method overriding role

class CustomUserChangeForm(UserChangeForm):
    """Form for updating users in the admin (if needed)."""
    class Meta(UserChangeForm.Meta):
        model = CustomUser
        # Exclude role if customizing admin user change form
        fields = ('email', 'username', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')


class UserProfileForm(forms.ModelForm):
    """Form for editing the user's profile, including new AI fields."""

    # Optional: Add specific widgets or validation if needed
    weight_kg = forms.DecimalField(
        max_digits=5, decimal_places=1, required=False,
        min_value=Decimal('20.0'), max_value=Decimal('300.0'),
        widget=forms.NumberInput(attrs={'step': '0.1'}),
        help_text="Optional: Your weight in kilograms (e.g., 68.5)."
    )
    height_cm = forms.IntegerField(
        required=False,
        min_value=50, max_value=300,
        widget=forms.NumberInput(),
        help_text="Optional: Your height in centimeters (e.g., 165)."
    )
    
    gender = forms.ChoiceField(            #  ← NEW
        choices=UserProfile.GENDER_CHOICES,
        required=False,
        label="Gender (for AI)",
    )

    class Meta:
        model = UserProfile
        # Explicitly list fields to control order and inclusion
        fields = [
            'first_name',
            'last_name',
            'bio',
            'profile_picture',
            'contact_number',
            'location',
            'height_cm', # New
            'weight_kg', # New
            'ethnicity_ai', # New
            'body_type_ai', # New
            'appearance_prompt_notes', # New
            'gender', # New	
            'age', # New
        ]
        # Optional: Add widgets for specific fields if needed
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 3}),
            'appearance_prompt_notes': forms.Textarea(attrs={'rows': 3}),
        }