# marketplace/urls.py
from django.urls import path
from .views import (
    HomePage, ProductDetailView, ProductCreateView, 
    ProductUpdateView, ProductDeleteView, MyClosetView, replace_product_image, finalize_product_image
)

app_name = 'marketplace'
urlpatterns = [
    path('', HomePage.as_view(), name='home'),
    path('my-closet/', MyClosetView.as_view(), name='my-closet'),
    path('<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('new/', ProductCreateView.as_view(), name='product-create'),
    path('<int:pk>/edit/', ProductUpdateView.as_view(), name='product-update'),
    path('<int:pk>/delete/', ProductDeleteView.as_view(), name='product-delete'),
    path('<int:pk>/replace_image/', replace_product_image, name='replace_product_image'),
    path('finalize_product_image/<int:product_id>/<int:uploaded_id>/', finalize_product_image, name='finalize-product-image'),
]
