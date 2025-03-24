from django.urls import reverse_lazy, reverse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from .models import Product, ProductImage
from .forms import ProductForm
from django.contrib.auth.decorators import login_required


class HomePage(ListView):
    model = Product
    template_name = 'marketplace/home.html'
    context_object_name = 'products'
    ordering = ['-created_at']
    paginate_by = 10

    def get_queryset(self):
        # Start with public products
        queryset = super().get_queryset().filter(is_public=True)
        
        # Full-text search across title and description
        q = self.request.GET.get('q')
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(description__icontains=q))
        
        # Filtering exact-match fields (using checkboxes)
        categories = self.request.GET.getlist('category')
        if categories:
            queryset = queryset.filter(category__in=categories)
        conditions = self.request.GET.getlist('condition')
        if conditions:
            queryset = queryset.filter(condition__in=conditions)
        is_sold_vals = self.request.GET.getlist('is_sold')
        if is_sold_vals:
            bool_values = []
            for val in is_sold_vals:
                if val.lower() == 'true':
                    bool_values.append(True)
                elif val.lower() == 'false':
                    bool_values.append(False)
            if bool_values:
                queryset = queryset.filter(is_sold__in=bool_values)
        
        # Filtering partial-match fields: size, color, material
        size_filter = self.request.GET.get('size')
        if size_filter:
            queryset = queryset.filter(size__icontains=size_filter)
        color_filter = self.request.GET.get('color')
        if color_filter:
            queryset = queryset.filter(color__icontains=color_filter)
        material_filter = self.request.GET.get('material')
        if material_filter:
            queryset = queryset.filter(material__icontains=material_filter)
        
        # Sorting
        sort_by = self.request.GET.get('sort')
        if sort_by == 'title_asc':
            queryset = queryset.order_by('title')
        elif sort_by == 'title_desc':
            queryset = queryset.order_by('-title')
        elif sort_by == 'price_asc':
            queryset = queryset.order_by('price')
        elif sort_by == 'price_desc':
            queryset = queryset.order_by('-price')
        elif sort_by == 'created_at_asc':
            queryset = queryset.order_by('created_at')
        elif sort_by == 'created_at_desc':
            queryset = queryset.order_by('-created_at')
        
        # Attach computed attributes for each product
        for product in queryset:
            product.primary_image = product.images.filter(is_primary=True).first()
            if product.price is not None:
                product.formatted_price = f"₱{product.price:.2f}"
            else:
                product.formatted_price = "N/A"
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Build filter options from all public products
        qs = Product.objects.filter(is_public=True)
        context['categories'] = qs.values_list('category', flat=True).distinct()
        context['conditions'] = qs.values_list('condition', flat=True).distinct()
        context['is_sold_options'] = [True, False]  # Boolean options for sold status
        
        # For fields that might have many values, use checkboxes if fewer than 5 unique values
        sizes = list(qs.values_list('size', flat=True).distinct().exclude(size__isnull=True).exclude(size__exact=''))
        colors = list(qs.values_list('color', flat=True).distinct().exclude(color__isnull=True).exclude(color__exact=''))
        materials = list(qs.values_list('material', flat=True).distinct().exclude(material__isnull=True).exclude(material__exact=''))
        context['sizes'] = sizes if len(sizes) < 5 else None
        context['colors'] = colors if len(colors) < 5 else None
        context['materials'] = materials if len(materials) < 5 else None

        # Pass current GET parameters for filter state preservation
        context['current_filters'] = self.request.GET
        context['filter_category'] = self.request.GET.getlist("category")
        context['filter_condition'] = self.request.GET.getlist("condition")
        context['filter_is_sold'] = self.request.GET.getlist("is_sold")
        return context

class ProductDetailView(DetailView):
    model = Product
    template_name = 'marketplace/product_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        context['primary_image'] = product.images.filter(is_primary=True).first()
        if product.price is not None:
            context['formatted_price'] = f"₱{product.price:.2f}"
        else:
            context['formatted_price'] = "N/A"
        return context

class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'marketplace/product_create.html'

    def form_valid(self, form):
        form.instance.seller = self.request.user
        response = super().form_valid(form)
        if self.object.images.count() == 0:
            # Store the product ID in session so that image scanning flow can attach the image
            self.request.session['attach_product_id'] = self.object.id
            messages.info(self.request, "You must add an image for your product. Please scan/upload an image.")
            return redirect('image_scanning:upload_image')
        return response

    def get_success_url(self):
        return reverse_lazy('marketplace:product-detail', kwargs={'pk': self.object.pk})

class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'marketplace/product_update.html'

    def get_queryset(self):
        return Product.objects.filter(seller=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        context['primary_image'] = product.images.filter(is_primary=True).first()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.object.is_public and self.object.images.count() == 0:
            messages.info(self.request, "Please upload or scan an image for your product.")
            return redirect('image_scanning:upload_image')
        return response

    def get_success_url(self):
        if not self.object.is_public:
            return reverse_lazy('marketplace:my-closet')
        return reverse_lazy('marketplace:home')

class ProductDeleteView(LoginRequiredMixin, DeleteView):
    model = Product
    template_name = 'marketplace/product_confirm_delete.html'
    success_url = reverse_lazy('marketplace:home')

    def get_queryset(self):
        return Product.objects.filter(seller=self.request.user)

class MyClosetView(LoginRequiredMixin, ListView):
    model = Product
    template_name = 'marketplace/my_closet.html'
    context_object_name = 'closet_products'
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = Product.objects.filter(seller=self.request.user, is_public=False)
        for product in queryset:
            product.primary_image = product.images.filter(is_primary=True).first()
        return queryset

@login_required
def replace_product_image(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    messages.info(request, "Please scan or upload a new image for product replacement.")
    request.session['replace_product_id'] = product.id
    return redirect('image_scanning:upload_image')

import os
@login_required
def finalize_product_image(request, product_id, uploaded_id):
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    from image_scanning.models import UploadedImage
    uploaded = get_object_or_404(UploadedImage, id=uploaded_id, user=request.user)

    dir_path = os.path.dirname(uploaded.original_image.path)
    base_name = os.path.splitext(os.path.basename(uploaded.original_image.path))[0]
    processed_filename = f"processed_{base_name}.png"
    processed_path = os.path.join(dir_path, processed_filename)

    # Delete any existing primary images for this product
    ProductImage.objects.filter(product=product, is_primary=True).delete()
    # Create a new primary ProductImage using the processed image file.
    ProductImage.objects.create(product=product, image=processed_path, is_primary=True)
    messages.success(request, "Product image attached successfully!")
    request.session.pop('attach_product_id', None)
    return redirect('marketplace:product-update', pk=product_id)
