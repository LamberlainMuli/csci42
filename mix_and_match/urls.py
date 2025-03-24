from django.urls import path
from .views import create_outfit, preview_outfit, recommendations, download_outfit, edit_outfit

app_name = 'mix_and_match'

urlpatterns = [
    path('create/', create_outfit, name='create_outfit'),
    path('create/<int:outfit_id>/', create_outfit, name='create_outfit'),
    path('edit/<int:outfit_id>/', edit_outfit, name='edit_outfit'),
    path('preview/<int:outfit_id>/', preview_outfit, name='preview_outfit'),
    path('download/<int:outfit_id>/', download_outfit, name='download_outfit'),
    path('recommendations/', recommendations, name='recommendations'),
]
