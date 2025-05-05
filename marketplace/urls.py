# marketplace/urls.py
from django.urls import path
from .views import (
    HomePage, ProductDetailView, ProductCreateView,
    ProductUpdateView, ProductDeleteView, MyClosetView,
    replace_product_image, finalize_product_image,
    autocomplete_suggestions, edit_existing_product_image
)

app_name = 'marketplace'
urlpatterns = [
    path('', HomePage.as_view(), name='home'),
    path('my-closet/', MyClosetView.as_view(), name='my-closet'),
    path('product/<int:pk>/', ProductDetailView.as_view(), name='product-detail'), # Added 'product/' prefix for clarity
    path('product/new/', ProductCreateView.as_view(), name='product-create'),
    path('product/<int:pk>/edit/', ProductUpdateView.as_view(), name='product-update'),
    path('product/<int:pk>/delete/', ProductDeleteView.as_view(), name='product-delete'),
    path('product/<int:pk>/replace-image/', replace_product_image, name='replace_product_image'), # Renamed slightly
    path('product/finalize-image/<int:product_id>/<int:uploaded_id>/', finalize_product_image, name='finalize-product-image'), # Renamed slightly
    path('autocomplete-suggestions/', autocomplete_suggestions, name='autocomplete-suggestions'),
    path('product/<int:pk>/edit-image/', edit_existing_product_image, name='edit_existing_product_image'),
]
