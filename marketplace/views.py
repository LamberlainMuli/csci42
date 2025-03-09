from .models import Product
from django.urls import reverse_lazy
from django.views.generic import *

class HomePage(ListView):
    model = Product
    template_name = 'marketplace/home.html'
    context_object_name = 'products'
    ordering = ['-created_at']
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get('q')

        for product in queryset:
            product.primary_image = product.images.filter(is_primary=True).first()
        if query:
            queryset = queryset.filter(title__icontains=query) 
        return queryset

class ProductDetailView(DetailView):
    model = Product
    template_name = 'marketplace/product_detail.html'

class ProductCreateView(CreateView):
    model = Product
    template_name = 'marketplace/product_form.html'
    fields = ['title', 'description', 'price', 'size', 'color', 'material', 'category', 'condition', 'is_sold']
    
class ProductUpdateView(UpdateView):
    model = Product
    template_name = 'marketplace/product_form.html'
    fields = ['title', 'description', 'price', 'size', 'color', 'material', 'category', 'condition', 'is_sold']
    
    def get_queryset(self):
        return Product.objects.filter(seller=self.request.user)

class ProductDeleteView(DeleteView):
    model = Product
    template_name = 'marketplace/product_confirm_delete.html'
    success_url = reverse_lazy('product-list')
    
    def get_queryset(self):
        return Product.objects.filter(seller=self.request.user)