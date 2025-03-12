# image_scanning/admin.py
from django.contrib import admin
from .models import UploadedImage, ProcessedClothingItem

@admin.register(UploadedImage)
class UploadedImageAdmin(admin.ModelAdmin):
    list_display = ('user', 'original_image', 'upload_date')

@admin.register(ProcessedClothingItem)
class ProcessedClothingItemAdmin(admin.ModelAdmin):
    list_display = ('user', 'processed_image', 'product', 'created_at')
