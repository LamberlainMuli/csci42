# image_scanning/urls.py
from django.urls import path
from . import views

app_name = 'image_scanning'

urlpatterns = [
    path('guide/', views.scanning_guide, name='scanning_guide'),
    path('upload/', views.upload_image, name='upload_image'),
    path('process/<int:uploaded_id>/', views.process_image, name='process_image'),
    path('preview/<int:uploaded_id>/', views.process_preview, name='process_preview'),
    path('edit/<int:uploaded_id>/', views.edit_image, name='edit_image'),
]