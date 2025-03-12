# marketplace/forms.py
from django import forms
from .models import Product

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'title', 'description', 'price', 'size', 'color', 
            'material', 'category', 'condition', 'is_sold', 'is_public'
        ]

    def clean(self):
        cleaned_data = super().clean()
        is_public = cleaned_data.get('is_public', True)
        price = cleaned_data.get('price')
        if is_public and (price is None):
            self.add_error('price', 'Price is required for public products.')
        return cleaned_data
