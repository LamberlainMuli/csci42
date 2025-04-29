from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import CustomUser, UserProfile

# Inline for UserProfile to show within CustomUser admin
class UserProfileInline(admin.StackedInline):
    """Inline admin descriptor for UserProfile"""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'

# Define a new User admin
@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    """Admin configuration for the CustomUser model."""
    # Use the default BaseUserAdmin fieldsets and add custom fields
    # Add 'role' to the list display and filters
    list_display = ('email', 'username', 'role', 'is_staff', 'is_active', 'date_created')
    list_filter = ('role', 'is_staff', 'is_active', 'date_created')
    search_fields = ('email', 'username')
    ordering = ('-date_created',)

    # Customize fieldsets if needed, adding 'role' perhaps to personal info
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('username', 'role')}), # Added role here
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_created')}), # Changed date_joined to date_created
    )
    readonly_fields = ('last_login', 'date_created') # Add date_created here

    # Add the UserProfile inline
    inlines = (UserProfileInline,)

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        return super().get_inline_instances(request, obj)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'first_name', 'last_name', 'contact_number', 'location')
    search_fields = ('user__username', 'user__email', 'first_name', 'last_name', 'contact_number')