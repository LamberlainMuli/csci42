# user/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
# Import the updated forms
from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import CustomUser, UserProfile

# Inline for UserProfile to show within CustomUser admin
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'
    # Define fields shown in the inline view
    fields = (
        'first_name', 'last_name', 'bio', 'profile_picture', 'contact_number', 'location',
        'height_cm', 'weight_kg', 'ethnicity_ai', 'body_type_ai', 'appearance_prompt_notes','gender', 'age'
    )
    # Make some fields readonly if preferred in inline view
    # readonly_fields = ('height_cm', 'weight_kg') # Example

# Define a new User admin
@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    # Use the custom forms
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm

    # Remove 'role' from list_display and list_filter
    list_display = ('email', 'username', 'is_staff', 'is_active', 'is_email_verified', 'date_created')
    list_filter = ('is_staff', 'is_active', 'is_email_verified', 'date_created')
    search_fields = ('email', 'username')
    ordering = ('-date_created',)

    # Remove 'role' from fieldsets
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('username', )}), # Removed role
        ('Permissions', {'fields': ('is_active', 'is_email_verified', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}), # Added is_email_verified
        ('Important dates', {'fields': ('last_login', 'date_created')}),
    )
    # Add fields shown only when adding a user
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (None, {'fields': ('email', 'username')}), # Ensure email/username are in add form
    )
    readonly_fields = ('last_login', 'date_created')

    # Add the UserProfile inline
    inlines = (UserProfileInline,)

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        return super().get_inline_instances(request, obj)

# Remove the separate UserProfileAdmin if the inline is sufficient
# admin.site.unregister(UserProfile)