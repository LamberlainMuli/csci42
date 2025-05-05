from django.contrib import admin
from .models import UserOutfit, OutfitItem, OutfitRecommendation

class OutfitItemInline(admin.TabularInline):
    """Inline view for Outfit Items within the UserOutfit admin."""
    model = OutfitItem
    fields = ('product', 'position_x', 'position_y', 'scale', 'z_index')
    extra = 1 # Show one extra form for adding items easily
    autocomplete_fields = ['product'] # Use autocomplete for product selection

@admin.register(UserOutfit)
class UserOutfitAdmin(admin.ModelAdmin):
    """Admin configuration for the UserOutfit model."""
    list_display = ('id', 'user', 'created_at', 'item_count')
    list_filter = ('created_at',)
    search_fields = ('id', 'user__username', 'user__email')
    readonly_fields = ('created_at', 'preview_image') # Preview might be auto-generated
    inlines = [OutfitItemInline]

    def item_count(self, obj):
        # Method to display the number of items in the outfit
        return obj.items.count()
    item_count.short_description = 'No. of Items' # Column header

@admin.register(OutfitRecommendation)
class OutfitRecommendationAdmin(admin.ModelAdmin):
    """Admin configuration for the OutfitRecommendation model."""
    list_display = ('id', 'user', 'criteria_summary', 'item_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('id', 'user__username', 'user__email', 'criteria')
    readonly_fields = ('created_at',)
    filter_horizontal = ('recommended_items',) # Better UI for ManyToManyField

    def item_count(self, obj):
        return obj.recommended_items.count()
    item_count.short_description = 'Recommended Items'

    def criteria_summary(self, obj):
        # Show a truncated version of criteria
        return (obj.criteria[:75] + '...') if len(obj.criteria) > 75 else obj.criteria
    criteria_summary.short_description = 'Criteria'

