# chat/urls.py

from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_list_view, name='chat_list'),
    path('start/<uuid:seller_id>/', views.start_chat_with_seller, name='start_chat'), # Use UUID for user ID
    path('room/<int:room_id>/', views.chat_room_view, name='chat_room'),
]