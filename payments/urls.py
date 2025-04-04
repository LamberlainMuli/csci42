from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('webhook/xendit/', views.xendit_webhook, name='xendit_webhook'),
    path('callback/<str:status>/', views.payment_callback_view, name='payment_callback'),
]