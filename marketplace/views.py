from django.shortcuts import render
from .models import Product
from django.views.generic import ListView

class HomePage(ListView):
    model = Product
    template_name = 'marketplace/home.html'
    context_object_name = 'products'
    ordering = ['-created_at']
    paginate_by = 10