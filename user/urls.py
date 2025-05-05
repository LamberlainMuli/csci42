from django.urls import path
from . import views

app_name = 'user'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('register/pending/', views.registration_pending_view, name='registration_pending'),
    path('verify/<str:uidb64>/<str:token>/', views.verify_email_view, name='verify_email'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/update/', views.update_profile_view, name='update_profile'),
    path('profile/<str:username>/', views.public_profile_view, name='public_profile'),
]

app_name = 'user'