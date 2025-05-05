# mix_and_match/urls.py
from django.urls import path
# Import the views needed
from .views import (
    create_outfit, preview_outfit, recommendations,
    download_outfit, edit_outfit, ai_generate_view, delete_outfit, toggle_outfit_privacy, public_outfit_preview
)
# Removed uuid import as default ID is likely integer

app_name = 'mix_and_match'

urlpatterns = [
    path('create/', create_outfit, name='create_outfit'),
    # --- Use int path converter for default IDs ---
    path('edit/<int:outfit_id>/', edit_outfit, name='edit_outfit'),
    path('preview/<int:outfit_id>/', preview_outfit, name='preview_outfit'),
    path('download/<int:outfit_id>/', download_outfit, name='download_outfit'),
    path('recommendations/', recommendations, name='recommendations'),
    path('outfit/<int:outfit_id>/generate-ai/', ai_generate_view, name='ai_generate'),
    path('outfit/<int:outfit_id>/delete/', delete_outfit, name='delete_outfit'),
    path('outfit/<int:outfit_id>/toggle-privacy/', toggle_outfit_privacy, name='toggle_outfit_privacy'),
    path('outfit/<int:outfit_id>/view/', public_outfit_preview, name='public_outfit_preview'),
]