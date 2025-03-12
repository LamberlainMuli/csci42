# image_scanning/forms.py
from django import forms
from .models import UploadedImage, ProcessedClothingItem

class UploadedImageForm(forms.ModelForm):
    class Meta:
        model = UploadedImage
        fields = ['original_image']
        widgets = {
            'original_image': forms.ClearableFileInput(attrs={
                'accept': "image/*", 
                'capture': "camera"
            })
        }

class ProcessedClothingItemForm(forms.ModelForm):
    class Meta:
        model = ProcessedClothingItem
        fields = ['processed_image', 'product']
