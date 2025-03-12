from django.urls import path
from .views import *

app_name = 'marketplace'  # This registers the namespace

urlpatterns = [
    path('', HomePage.as_view(), name='home'),
    path('<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('new/', ProductCreateView.as_view(), name='product-create'),
    path('<int:pk>/edit/', ProductUpdateView.as_view(), name='product-update'),
    path('<int:pk>/delete/', ProductDeleteView.as_view(), name='product-delete'),
]