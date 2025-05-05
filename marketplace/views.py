# marketplace/views.py
from django.urls import reverse_lazy, reverse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count
from django.db import transaction
from .models import Product, ProductImage
from .forms import ProductForm
from django.contrib.auth.decorators import login_required
import os
from django.templatetags.static import static 
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
import base64
from django.shortcuts import render
from django.conf import settings
# Assuming UploadedImage is needed elsewhere, keep imports
# from image_scanning.models import UploadedImage
# from image_scanning.views import get_processed_paths

from django.core.files import File
import logging
# Add JsonResponse
from django.http import JsonResponse


logger = logging.getLogger(__name__)

# --- HomePage View remains largely the same, context data generation is still useful ---
class HomePage(ListView):
    model = Product
    template_name = 'marketplace/home.html'
    context_object_name = 'products'
    paginate_by = 12

    def get_queryset(self):
        # Start with public, available products by default
        queryset = super().get_queryset().filter(is_public=True)

        # --- Availability Filtering (Apply Default or User Choice) ---
        is_sold_param = 'is_sold'
        if is_sold_param in self.request.GET:
            is_sold_vals = self.request.GET.getlist(is_sold_param)
            bool_values = []
            include_available = False
            include_sold = False
            for val in is_sold_vals:
                if val.lower() == 'true':
                    bool_values.append(True)
                    include_sold = True
                elif val.lower() == 'false':
                    bool_values.append(False)
                    include_available = True

            if bool_values:
                queryset = queryset.filter(is_sold__in=bool_values)
                if include_available and not include_sold:
                    queryset = queryset.filter(quantity__gt=0)
            else: # Parameter exists but no valid values checked
                 queryset = queryset.none() # Show nothing if filter applied with no selection
        else:
            # DEFAULT: Show only available & in stock if no filter applied
            queryset = queryset.filter(is_sold=False, quantity__gt=0)
        # --- End Availability Filtering ---

        # Full-text search
        q = self.request.GET.get('q')
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(description__icontains=q))

        # Filtering other fields (Keep existing logic)
        categories = self.request.GET.getlist('category')
        if categories:
            queryset = queryset.filter(category__in=categories)
        conditions = self.request.GET.getlist('condition')
        if conditions:
            queryset = queryset.filter(condition__in=conditions)
        size_filter = self.request.GET.get('size')
        if size_filter:
            queryset = queryset.filter(size__icontains=size_filter)
        color_filter = self.request.GET.get('color')
        if color_filter:
            queryset = queryset.filter(color__icontains=color_filter)
        material_filter = self.request.GET.get('material')
        if material_filter:
            queryset = queryset.filter(material__icontains=material_filter)

        # Sorting (Keep existing logic)
        sort_by = self.request.GET.get('sort')
        if sort_by == 'title_asc':
            queryset = queryset.order_by('title')
        elif sort_by == 'title_desc':
            queryset = queryset.order_by('-title')
        elif sort_by == 'price_asc':
            queryset = queryset.filter(price__isnull=False).order_by('price')
        elif sort_by == 'price_desc':
            queryset = queryset.filter(price__isnull=False).order_by('-price')
        elif sort_by == 'created_at_asc':
            queryset = queryset.order_by('created_at')
        else: # Default to newest first
            queryset = queryset.order_by('-created_at')

        # --- EFFICIENTLY FETCH RELATED DATA ---
        queryset = queryset.select_related(
            'seller__profile' # Select seller and their profile
        ).prefetch_related(
            'images' # Prefetch images
        ).annotate(
            # Annotate counts using the related_names we added
            saved_count=Count('saved_by_users', distinct=True), # Count distinct users who saved
            cart_count=Count('in_carts', distinct=True) # Count distinct carts containing the item
        )
        # --- END FETCHING RELATED DATA ---

        # Attach primary image URL and formatted price after filtering/sorting/annotating
        # Note: Annotations must usually come before slicing (pagination)
        # This loop is okay here *before* pagination happens internally
        for product in queryset:
             # Find primary image from prefetched data
             product.primary_image = next((img for img in product.images.all() if img.is_primary), product.images.first())
             product.primary_image_url = product.primary_image.image.url if product.primary_image and hasattr(product.primary_image, 'image') else static('images/placeholder.png')

             # Format price
             if product.price is not None:
                 product.formatted_price = f"\u20B1{product.price:.2f}" # PHP Peso sign
             else:
                 product.formatted_price = "N/A (Private)" if not product.is_public else "Price N/A"

        return queryset # Return the prepared queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # --- Filter options needed for the modal (Keep existing logic) ---
        qs_all_public = Product.objects.filter(is_public=True) # Use this for filter options
        context['categories'] = Product.CATEGORY_CHOICES
        context['conditions'] = Product.CONDITION_CHOICES
        context['availability_options'] = [('false', 'Available'), ('true', 'Sold')]

        distinct_sizes = list(qs_all_public.values_list('size', flat=True).distinct().exclude(size__isnull=True).exclude(size__exact='').order_by('size'))
        distinct_colors = list(qs_all_public.values_list('color', flat=True).distinct().exclude(color__isnull=True).exclude(color__exact='').order_by('color'))
        distinct_materials = list(qs_all_public.values_list('material', flat=True).distinct().exclude(material__isnull=True).exclude(material__exact='').order_by('material'))

        context['show_size_checkboxes'] = len(distinct_sizes) < 10
        context['sizes'] = distinct_sizes
        context['show_color_checkboxes'] = len(distinct_colors) < 15
        context['colors'] = distinct_colors
        context['show_material_checkboxes'] = len(distinct_materials) < 10
        context['materials'] = distinct_materials

        # Pass current GET parameters (Keep existing logic)
        context['current_filters'] = self.request.GET
        context['filter_category'] = self.request.GET.getlist("category")
        context['filter_condition'] = self.request.GET.getlist("condition")
        context['filter_is_sold'] = self.request.GET.getlist("is_sold")
        context['filter_size'] = self.request.GET.get("size", "")
        context['filter_color'] = self.request.GET.get("color", "")
        context['filter_material'] = self.request.GET.get("material", "")
        context['filter_sort'] = self.request.GET.get("sort", "")

        # Default Availability (Keep existing logic)
        if 'is_sold' not in self.request.GET:
             context['filter_is_sold_default'] = ['false']
        else:
             context['filter_is_sold_default'] = context['filter_is_sold']

        return context


# --- NEW AUTOCOMPLETE VIEW ---
def autocomplete_suggestions(request):
    query = request.GET.get('term', '')
    if len(query) > 1: # Only search if query is reasonably long
        # Query public products where title starts with the query
        suggestions = Product.objects.filter(
            title__istartswith=query,
            is_public=True
        ).values_list('title', flat=True)[:10] # Limit suggestions
        return JsonResponse(list(suggestions), safe=False)
    return JsonResponse([], safe=False)


# --- Other Views (ProductDetailView, Create, Update, Delete, MyClosetView, etc.) remain the same ---
# Make sure MyClosetView filters by is_public=False and seller=request.user
class MyClosetView(LoginRequiredMixin, ListView):
    model = Product
    template_name = 'marketplace/my_closet.html'
    context_object_name = 'closet_products'
    paginate_by = 12 # Or your preferred number

    def get_queryset(self):
        # Base queryset: User's private items
        queryset = Product.objects.filter(
            seller=self.request.user,
            is_public=False
        )

        # --- Apply Search ---
        q = self.request.GET.get('q')
        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) | Q(description__icontains=q)
            )

        # --- Apply Filters (Category, Size, Color, Material) ---
        # (Keep filter logic as implemented previously)
        categories = self.request.GET.getlist('category')
        if categories:
            queryset = queryset.filter(category__in=categories)
        size_filter = self.request.GET.get('size')
        if size_filter:
            queryset = queryset.filter(size__icontains=size_filter)
        color_filter = self.request.GET.get('color')
        if color_filter:
            queryset = queryset.filter(color__icontains=color_filter)
        material_filter = self.request.GET.get('material')
        if material_filter:
            queryset = queryset.filter(material__icontains=material_filter)


        # --- Apply Sorting ---
        # (Keep sorting logic as implemented previously)
        sort_by = self.request.GET.get('sort')
        if sort_by == 'title_asc':
            queryset = queryset.order_by('title')
        elif sort_by == 'title_desc':
            queryset = queryset.order_by('-title')
        elif sort_by == 'created_at_asc':
            queryset = queryset.order_by('created_at')
        else: # Default: Newest first
            queryset = queryset.order_by('-created_at')


        # --- Prefetch related data and return UNEVALUATED queryset ---
        return queryset.prefetch_related('images')

    def get_context_data(self, **kwargs):
        # Get base context from ListView (includes paginator, page_obj, is_paginated)
        # This sets context['closet_products'] = page_obj.object_list (the items for the current page)
        context = super().get_context_data(**kwargs)

        # --- Attach primary_image_url to the objects for the CURRENT page ---
        # Access the list of objects for the current page from the context
        products_on_page = context.get(self.context_object_name) # Use context_object_name
        if products_on_page: # Check if there are objects on the page
            for product in products_on_page:
                # Find the primary image using prefetched data
                primary_image = next((img for img in product.images.all() if img.is_primary), product.images.first())
                # Set the attribute directly on the product object IN THE CONTEXT
                product.primary_image_url = primary_image.image.url if primary_image and hasattr(primary_image, 'image') and primary_image.image else static('images/placeholder.png')

        # --- Filter Options for Modal ---
        # (Keep the logic for populating context['categories'], etc.)
        closet_qs_base = Product.objects.filter(seller=self.request.user, is_public=False)
        context['categories'] = sorted(list(
            closet_qs_base.exclude(category__isnull=True).exclude(category__exact='')
            .values_list('category', flat=True).distinct()
        ))
        context['sizes'] = sorted(list(
             closet_qs_base.exclude(size__isnull=True).exclude(size__exact='')
             .values_list('size', flat=True).distinct()
        ))
        context['colors'] = sorted(list(
             closet_qs_base.exclude(color__isnull=True).exclude(color__exact='')
             .values_list('color', flat=True).distinct()
        ))
        context['materials'] = sorted(list(
             closet_qs_base.exclude(material__isnull=True).exclude(material__exact='')
             .values_list('material', flat=True).distinct()
        ))
        context['show_size_checkboxes'] = len(context['sizes']) < 15
        context['show_color_checkboxes'] = len(context['colors']) < 20
        context['show_material_checkboxes'] = len(context['materials']) < 15


        # --- Pass current filter values ---
        context['current_filters'] = self.request.GET # Pass the whole GET dict
        context['filter_q'] = self.request.GET.get('q', '')
        context['filter_category'] = self.request.GET.getlist("category")
        context['filter_size'] = self.request.GET.get("size", "")
        context['filter_color'] = self.request.GET.get("color", "")
        context['filter_material'] = self.request.GET.get("material", "")
        context['filter_sort'] = self.request.GET.get("sort", "")

        return context

class ProductDetailView(DetailView):
    model = Product
    template_name = 'marketplace/product_detail.html'
    # context_object_name = 'product' # Default is 'object'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()

        # --- Get Images (Primary First) ---
        all_images = list(product.images.order_by('-is_primary').all()) # Order by is_primary descending
        context['product_images'] = all_images
        context['primary_image'] = all_images[0] if all_images else None

        # --- Format Price ---
        if product.price is not None:
            # Using PHP currency symbol as requested previously
            context['formatted_price'] = f"\u20B1{product.price:.2f}"
        else:
            context['formatted_price'] = "N/A (Private)" if not product.is_public else "Price not set"

        # --- Flags for Template Logic ---
        context['is_seller'] = self.request.user.is_authenticated and (product.seller == self.request.user)
        context['can_purchase'] = (
            product.is_public and
            not product.is_sold and
            product.quantity > 0 and
            (not self.request.user.is_authenticated or product.seller != self.request.user)
        )

        # --- Brand Colors for Template ---
        context['brand_colors'] = {
            'primary': '#6aad6c',
            'secondary': '#cf899b', # Using pink as secondary button example
            'accent1': '#efaca4',   # Original "secondary" as accent
            'navbar_bg': '#2c2c47',
            'body_bg': '#fffef7',
            'button_text': '#faffda', # Light text for colored buttons
            'light_accent': '#E7F1BF',
        }
        # You can add more colors from your palette here if needed

        # --- Seller Profile Picture (Handle potential missing profile) ---
        seller_profile_pic_url = None
        if hasattr(product.seller, 'userprofile') and product.seller.userprofile.profile_picture:
            seller_profile_pic_url = product.seller.userprofile.profile_picture.url
        context['seller_profile_pic_url'] = seller_profile_pic_url

        return context


class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'marketplace/product_create.html'

    def get_initial(self):
        initial = super().get_initial()
        # Default to private (closet) unless specified otherwise
        is_public = self.request.GET.get('is_public', 'false') # Default to false
        if is_public.lower() == 'true':
            initial['is_public'] = True
        else:
            initial['is_public'] = False # Explicitly set to false for closet
        return initial

    def form_valid(self, form):
        form.instance.seller = self.request.user
        response = super().form_valid(form)
        # Image handling logic remains the same
        if self.object.images.count() == 0:
            self.request.session['attach_product_id'] = self.object.id
            messages.info(self.request, "Item saved! Now, please add an image.")
            return redirect('image_scanning:upload_image') # Redirect to image upload
        return response

    def get_success_url(self):
        # Redirect to closet if private, otherwise product detail
        if not self.object.is_public:
             messages.success(self.request, f'"{self.object.title}" added to your closet.')
             return reverse_lazy('marketplace:my-closet')
        messages.success(self.request, f'"{self.object.title}" listed successfully.')
        return reverse_lazy('marketplace:product-detail', kwargs={'pk': self.object.pk})


class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'marketplace/product_update.html' # Will update this template below

    def get_queryset(self):
        # Ensure users can only edit their own products
        return Product.objects.filter(seller=self.request.user)

    def get_initial(self):
        """ Set initial form values, check for make_public flag. """
        initial = super().get_initial()
        # Check if redirected from detail page to make item public
        if self.request.GET.get('make_public') == 'true':
            initial['is_public'] = True
            # Optionally pre-fill price if missing and making public? Or let form validation handle it.
            if self.object and self.object.price is None:
                 messages.info(self.request, "Please set a price to make this item public.")
                 # initial['price'] = 0.00 # Example pre-fill
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        # Pass primary image and brand colors
        context['primary_image'] = product.images.filter(is_primary=True).first()
        context['brand_colors'] = {
            'primary': '#6aad6c', 'secondary': '#cf899b', 'accent1': '#efaca4',
            'navbar_bg': '#2c2c47', 'body_bg': '#fffef7', 'button_text': '#faffda',
            'light_accent': '#E7F1BF',
        }
        return context

    def form_valid(self, form):
        # Add message on successful save
        messages.success(self.request, f'"{form.instance.title}" updated successfully.')
        return super().form_valid(form)

    def get_success_url(self):
         # Always redirect back to detail view after update
        return reverse_lazy('marketplace:product-detail', kwargs={'pk': self.object.pk})



class ProductDeleteView(LoginRequiredMixin, DeleteView):
    model = Product
    template_name = 'marketplace/product_confirm_delete.html'

    def get_queryset(self):
        # Users can only delete their own products
        return Product.objects.filter(seller=self.request.user)

    def get_success_url(self):
        # Determine redirect based on whether item was public or private
        if not self.object.is_public:
            return reverse_lazy('marketplace:my-closet')
        return reverse_lazy('marketplace:home')

    def post(self, request, *args, **kwargs):
        # Add success message after deletion
        # Get object before it's deleted by super().post()
        self.object = self.get_object()
        item_title = self.object.title
        response = super().post(request, *args, **kwargs)
        messages.success(request, f'"{item_title}" deleted successfully.')
        # Success URL is handled by get_success_url
        return response

    # --- Add this method ---
    def get_context_data(self, **kwargs):
        """Add the primary image to the context."""
        context = super().get_context_data(**kwargs)
        # self.object is available here (the product being deleted)
        primary_image = self.object.images.filter(is_primary=True).first()
        context['primary_image'] = primary_image
        return context
    # --- End added method ---

# Image handling views (replace_product_image, finalize_product_image) remain the same
@login_required
def replace_product_image(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    # Redirect to image scanning app to handle upload/scan
    messages.info(request, "Please scan or upload the new image for your item.")
    request.session['replace_product_id'] = product.id
    return redirect('image_scanning:upload_image')


@login_required
def finalize_product_image(request, product_id, uploaded_id):
    # Logic remains the same: attach processed image, cleanup original
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    # Needs UploadedImage model and get_processed_paths helper
    try:
        from image_scanning.models import UploadedImage
        from image_scanning.views import get_processed_paths # Adjust import if moved
    except ImportError:
         logger.error("Image Scanning app components not found.")
         messages.error(request,"Could not finalize image due to configuration error.")
         return redirect('marketplace:product-update', pk=product_id)


    uploaded = get_object_or_404(UploadedImage, id=uploaded_id, user=request.user)
    processed_relative_path, full_processed_path, _ = get_processed_paths(uploaded)

    if not full_processed_path or not os.path.exists(full_processed_path):
        logger.error(f"Processed image file not found at finalize step: {full_processed_path}")
        messages.error(request, "Processed image could not be found. Please re-upload.")
        # Redirect back to update page, allowing user to retry image replacement
        return redirect('marketplace:product-update', pk=product_id)

    try:
        # --- Atomically replace or create the primary image ---
        with transaction.atomic(): # Ensure DB operations succeed or fail together
            # Delete existing primary image(s) for this product
            ProductImage.objects.filter(product=product, is_primary=True).delete()
            # Create the new primary image record
            ProductImage.objects.create(
                product=product,
                image=processed_relative_path, # Store relative path from MEDIA_ROOT
                is_primary=True
            )
        logger.info(f"Successfully attached image '{processed_relative_path}' to Product {product_id}")

        # --- Cleanup Original Uploaded Image and Record ---
        try:
            original_file_path = uploaded.original_image.path
            logger.info(f"Attempting cleanup for UploadedImage {uploaded_id}. Original: {original_file_path}")
            # Delete original file if it exists
            if os.path.exists(original_file_path):
                 os.remove(original_file_path)
                 logger.info("Deleted original file.")
            else: logger.warning("Original file not found for deletion.")
            # Delete DB record for original upload
            uploaded.delete()
            logger.info(f"Deleted UploadedImage record {uploaded_id}")
        except Exception as cleanup_e:
            logger.error(f"Error during cleanup for UploadedImage {uploaded_id}: {cleanup_e}", exc_info=True)
            # Don't fail the whole operation for cleanup error, but log it.

        messages.success(request, "Product image updated successfully!")
        # Clear session flags
        request.session.pop('attach_product_id', None)
        request.session.pop('replace_product_id', None)
        # Redirect to the update page to show the new image
        return redirect('marketplace:product-update', pk=product_id)

    except IOError as e:
        logger.error(f"IOError during finalize for Product {product_id}: {e}", exc_info=True)
        messages.error(request, "Error accessing image file during finalization.")
        return redirect('marketplace:product-update', pk=product_id)
    except Exception as e:
        logger.error(f"Error creating ProductImage for Product {product_id}: {e}", exc_info=True)
        messages.error(request, "An unexpected error occurred attaching the image.")
        return redirect('marketplace:product-update', pk=product_id)

@login_required
def edit_existing_product_image(request, pk):
    """
    Loads an existing primary product image into the TUI editor and saves changes.
    """
    product = get_object_or_404(Product, pk=pk)

    # --- Authorization Check ---
    if product.seller != request.user:
        raise PermissionDenied("You do not have permission to edit this product's image.")

    # --- Find the primary image ---
    primary_image = product.images.filter(is_primary=True).first()

    if not primary_image or not primary_image.image:
        messages.error(request, "No primary image found to edit for this product.")
        return redirect('marketplace:product-update', pk=product.pk)

    if request.method == 'POST':
        edited_data = request.POST.get('edited_image_data')
        if edited_data:
            try:
                # Decode base64 data
                format, imgstr = edited_data.split(';base64,')
                ext = format.split('/')[-1] # e.g., png
                image_bytes = base64.b64decode(imgstr)
                image_content_file = ContentFile(image_bytes)

                # Overwrite the existing image file associated with the ProductImage instance
                # Construct a new filename or keep the old one (keeping old one might cause caching issues)
                # Let's create a slightly modified name to potentially avoid cache issues
                current_filename = os.path.basename(primary_image.image.name)
                name, _ = os.path.splitext(current_filename)
                new_filename = f"{name}_edited.{ext}"

                # Save the new content under the existing ImageField instance
                # This will replace the file on the storage backend
                primary_image.image.save(new_filename, image_content_file, save=True) # Save=True updates the model instance

                logger.info(f"Overwrote existing image for ProductImage {primary_image.id} with edited version: {new_filename}")
                messages.success(request, "Image edited and saved successfully!")
                return redirect('marketplace:product-update', pk=product.pk) # Redirect back to update page

            except Exception as e:
                 logger.error(f"Error saving edited image for Product {pk}, ProductImage {primary_image.id}: {e}", exc_info=True)
                 messages.error(request, "Could not save edited image.")
                 # Fall through to render editor again with error
        else:
            messages.error(request, "No edited image data received.")
            # Fall through to render editor again
    # --- End POST Handling ---

    # --- GET Request ---
    context = {
        'product': product,
        'image_to_edit': primary_image,
        'image_url': primary_image.image.url, # Pass URL to load into editor
        'brand_colors': { # Pass brand colors if needed by editor template
            'body_bg': '#fffef7',
        }
    }
    # Use a dedicated template for editing existing images
    return render(request, 'marketplace/product_image_edit.html', context)