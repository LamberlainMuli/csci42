# dashboard/urls.py
from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('transactions/', views.all_wallet_transactions, name='all_transactions'),
    path('my-orders/', views.all_my_orders, name='all_my_orders'),
    path('sales-history/', views.all_sales_history, name='all_sales'),
]