from django.urls import path
# from . import views # Create views in orders/views.py
from . import views
app_name = 'orders'

urlpatterns = [
    path('<uuid:order_id>/', views.order_detail_view, name='order_detail'),
    path('', views.order_list_view, name='order_list'),
]