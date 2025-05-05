# wallet/urls.py
from django.urls import path
from . import views

app_name = 'wallet'

urlpatterns = [
    path('topup/', views.top_up_view, name='top_up'),
    # Optional: Add view/url for the VA details page if needed separately
    # path('topup/details/', views.top_up_va_details_view, name='top_up_va_details'),
    # Optional: Add view/url for full transaction history
    # path('transactions/', views.transaction_history_view, name='transaction_history'),
]