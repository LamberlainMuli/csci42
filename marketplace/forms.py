from django import forms
from .models import Product
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Submit

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'title', 'description', 'price', 'quantity', 'size', 'color', 
            'material', 'category', 'condition', 'is_sold', 'is_public'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize Crispy Forms helper
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Field('title'),
            Field('description'),
            Field('price'),
            Field('quantity'),
            Field('size'),
            Field('color'),
            Field('material'),
            Field('category'),
            Field('condition'),
            Field('is_sold'),
            Field('is_public'),
            Submit('submit', 'Save', css_class='btn btn-primary')
        )

    def clean(self):
        cleaned_data = super().clean()
        is_public = cleaned_data.get('is_public', True)
        price = cleaned_data.get('price')
        if is_public and (price is None):
            self.add_error('price', 'Price is required for public products.')
        return cleaned_data
