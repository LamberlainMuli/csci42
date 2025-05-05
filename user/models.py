# user/models.py
import uuid
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from decimal import Decimal # Import Decimal
from django.db import transaction
# Import Wallet model at the top
from wallet.models import Wallet
from django.templatetags.static import static

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        """Creates and saves a new user, inactive by default, and creates profile/wallet."""
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', False)
        if 'username' not in extra_fields:
             raise ValueError("Username must be provided.")

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        # Use a transaction to ensure user, profile, and wallet are created together
        with transaction.atomic():
            user.save(using=self._db)
            # Create profile (assuming UserProfile is defined below or imported)
            UserProfile.objects.create(user=user)
            # *** Automatically create Wallet ***
            Wallet.objects.create(user=user)
            # *** End Wallet Creation ***
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Creates and saves a new superuser with profile and wallet."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_email_verified', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        if 'username' not in extra_fields:
             extra_fields['username'] = email.split('@')[0] + "_admin"

        # create_user now creates profile and wallet within its transaction
        user = self.create_user(email, password, **extra_fields)
        return user

class CustomUser(AbstractUser, PermissionsMixin):
    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=255, unique=True)

    # REMOVED: role field and ROLE_CHOICES

    is_active = models.BooleanField(
        default=False, # Start as inactive until email verified
        help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.'
    )
    is_email_verified = models.BooleanField(
        default=False,
        help_text='Designates whether the user has verified their email address.'
    )
    is_staff = models.BooleanField(default=False)
    date_created = models.DateTimeField(auto_now_add=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username'] # Username still required for Django admin/commands

    def __str__(self):
        return self.email

    @property
    def account_age(self):
        # Ensure date_created is not None before calculation
        if self.date_created:
            return (timezone.now() - self.date_created).days
        return 0

class UserProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='profile')

    # Standard Profile Fields
    first_name = models.CharField(
        max_length=255, null=True, blank=True,
        validators=[RegexValidator(r'^[a-zA-Z\s\-]+$', 'First name must contain only letters, spaces, or hyphens')]
    )
    last_name = models.CharField(
        max_length=255, null=True, blank=True,
        validators=[RegexValidator(r'^[a-zA-Z\s\-]+$', 'Last name must contain only letters, spaces, or hyphens')]
    )
    bio = models.TextField(null=True, blank=True, help_text="A short description about yourself.")
    profile_picture = models.ImageField(null=True, blank=True, upload_to="profile_pictures/")
    contact_number = models.CharField(
        max_length=15, # Allow slightly longer for potential country codes etc.
        null=True, blank=True,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', 'Enter a valid phone number.')] # Basic international format check
    )
    location = models.CharField(max_length=255, blank=True, null=True, help_text="e.g., City, Province")

    # --- NEW Fields for AI Image Generation Assistance ---
    height_cm = models.PositiveIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(50), MaxValueValidator(300)], # Reasonable height range
        help_text="Optional: Your height in centimeters (e.g., 165)."
    )
    weight_kg = models.DecimalField(
        max_digits=5, decimal_places=1, # e.g., allows 120.5 kg
        null=True, blank=True,
        validators=[MinValueValidator(Decimal('20.0')), MaxValueValidator(Decimal('300.0'))], # Reasonable weight range
        help_text="Optional: Your weight in kilograms (e.g., 68.5)."
    )
    ethnicity_ai = models.CharField(
        max_length=100, null=True, blank=True,
        help_text="Optional: Helps AI visualize appearance (e.g., Filipino, East Asian, Caucasian, Hispanic, Black, etc.)"
    )
    body_type_ai = models.CharField(
        max_length=100, null=True, blank=True,
        help_text="Optional: Helps AI visualize appearance (e.g., Slim, Athletic, Average, Stocky, Curvy, etc.)"
    )
    
    GENDER_CHOICES = [
        ("male",        "Male"),
        ("female",      "Female"),
        ("non_binary",  "Non-binary / Gender-diverse"),
        ("unknown",     "Prefer not to say / Let AI infer"),
    ]

    gender = models.CharField(             
        max_length=20,
        choices=GENDER_CHOICES,
        default="unknown",
        blank=True,
        help_text="Optional: lets the AI choose better outfits; leave blank to let it infer."
    )
    
    age = models.PositiveIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(120)], # Reasonable age range
        help_text="Optional: Your age in years (e.g., 30)."
    )
    # Changed name slightly to make purpose clear
    appearance_prompt_notes = models.TextField(
        null=True, blank=True,
        help_text="Optional: Other distinct features for AI prompts (e.g., 'long wavy brown hair', 'wears round glasses', 'visible tattoo on left forearm')."
    )
    # --- End NEW Fields ---

    def __str__(self):
        return f"Profile for {self.user.username}"
    
    @property
    def get_picture_url(self):
        """
        Returns the URL for the profile picture.
        Falls back to gender-specific defaults or a general default.
        """
        default_male_url = static('images/male.jpg')
        default_female_url = static('images/female.jpg')
        default_neutral_url = static('images/neutral.jpg') 

        # 1. Check for uploaded picture
        if self.profile_picture and hasattr(self.profile_picture, 'url'):
            try:
                # Check if the file actually exists in storage
                # This might require checking storage directly depending on backend
                # For simple cases, accessing .url might throw ValueError if file missing
                if self.profile_picture.storage.exists(self.profile_picture.name):
                     return self.profile_picture.url
            except ValueError:
                 # Handle cases where the file is missing from storage
                 pass
            except Exception:
                 # Catch other potential storage errors
                 pass # Fall through to defaults

        # 2. Check gender for default (if no picture found/valid)
        if self.gender == 'female':
            return default_female_url
        elif self.gender == 'male':
            return default_male_url

        return default_neutral_url
    