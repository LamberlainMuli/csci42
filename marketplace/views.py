# marketplace/views.py
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.shortcuts import redirect
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.urls import reverse
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
        queryset = super().get_queryset()
        # Only show public products
        queryset = queryset.filter(is_public=True)
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(title__icontains=query)
        # Annotate each product with its primary image (if any)
        for product in queryset:
            product.primary_image = product.images.filter(is_primary=True).first()
        return queryset
    
class ProductDetailView(DetailView):
    model = Product
    template_name = 'marketplace/product_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        # Attach the primary image to the context
        context['primary_image'] = product.images.filter(is_primary=True).first()
        return context


# marketplace/views.py
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
            # Redirect to the image scanning upload view.
            return redirect('image_scanning:upload_image')
        return response

    def get_success_url(self):
        return reverse_lazy('marketplace:product-detail', kwargs={'pk': self.object.pk})

class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'marketplace/product_update.html'

    def get_queryset(self):
        # Only allow editing products that belong to the current user
        return Product.objects.filter(seller=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        # Attach the primary image to the context
        context['primary_image'] = product.images.filter(is_primary=True).first()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        # If the product is set to public, ensure it has an image
        if self.object.is_public and self.object.images.count() == 0:
            messages.info(self.request, "Please upload or scan an image for your product.")
            return redirect('image_scanning:upload_image')
        return response

    def get_success_url(self):
        # If the product is private, redirect to the closet page; otherwise, to home.
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
        # Attach primary_image attribute for each product
        for product in queryset:
            product.primary_image = product.images.filter(is_primary=True).first()
        return queryset

@login_required
def replace_product_image(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user)

    # We simply redirect to scanning with an indication that we want to attach the final result to this product.
    messages.info(request, "Please scan or upload a new image for product replacement.")
    # We can store product.id in session or pass it in the scanning URL.
    request.session['replace_product_id'] = product.id
    return redirect('image_scanning:upload_image')  # The scanning flow can check this ID from session

import os
@login_required
def finalize_product_image(request, product_id, uploaded_id):
    """
    Finalizes product creation by attaching the scanned image to the product.
    Retrieves the processed image from the image_scanning app and creates a ProductImage.
    Then, removes the session variable and redirects back to product update.
    """
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

    # Remove session variable used for product attachment
    request.session.pop('attach_product_id', None)
    # Redirect to product update page so the user can finalize details.
    return redirect('marketplace:product-update', pk=product_id)
