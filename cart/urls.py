# cart/urls.py
from django.urls import path
from . import views

app_name = 'cart'

urlpatterns = [
    path('', views.cart_list, name='cart_list'),  # /cart/
    path('add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    
    path('saved/', views.saved_list, name='saved_list'),
    path('saved/add/<int:product_id>/', views.add_to_saved, name='add_to_saved'),
    path('saved/remove/<int:saved_item_id>/', views.remove_from_saved, name='remove_from_saved'),
    
    path('checkout/', views.checkout_view, name='checkout'),
]
