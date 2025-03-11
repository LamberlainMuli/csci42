import uuid
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import (
    AbstractUser,
    BaseUserManager,
	PermissionsMixin,
)
from django.core.validators import RegexValidator


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Please specify a valid email.")
        email = self.normalize_email(email) # Normalize email (lowercase)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        user = self.create_user(email, password)
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user

class CustomUser(AbstractUser, PermissionsMixin):
    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=255, unique=True)
	
    ROLE_CHOICES = [
        ('buyer', 'Buyer'),
        ('seller', 'Seller'),
        ('admin', 'Admin'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='buyer')
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_created = models.DateTimeField(auto_now_add=True)
    
    objects = CustomUserManager()
    
    USERNAME_FIELD = 'email' # Email for auth
    REQUIRED_FIELDS = ['username'] # Require username when creating user
    
    def __str__(self):
        return self.email

    @property
    def account_age(self):
        return (timezone.now() - self.date_created).days

class UserProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='profile')

    # Optional fields
    # Similar concept as Carousell
    first_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        validators=[RegexValidator(r'^[a-zA-Z\s\-]+$', 'First name must contain only letters, spaces, or hyphens')]
    )
    last_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        validators=[RegexValidator(r'^[a-zA-Z\s\-]+$', 'Last name must contain only letters, spaces, or hyphens')]
    )
    bio = models.TextField(null=True, blank=True)
    profile_picture = models.ImageField(null=True, blank=True, upload_to="profile_pictures/")
    contact_number = models.CharField(
        max_length=11,
        null=True,
        blank=True,
        validators=[RegexValidator(r'^09\d{9}$', 'Enter a valid mobile number starting with 09 followed by 9 digits')]
    )
    location = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.user.username