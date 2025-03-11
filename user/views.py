from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import (
    login as auth_login, 
    authenticate
)
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import CustomUserRegistrationForm, UserProfileForm
from .models import CustomUser, UserProfile


def register(request):
    if request.method == 'POST':
        form = CustomUserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(user=user) # Create UserProfile for user
            auth_login(request, user)
            messages.success(request, "Registration succcessful!")
            return redirect('profile')
    else:
        form = CustomUserRegistrationForm()
    return render(request, 'user-management/register.html', {'form': form})

def login(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            return redirect('profile')
    else:
        form = AuthenticationForm()
    return render(request, 'user-management/login.html', {'form': form})

def profile(request):
    profile = request.user.profile
    return render(request, 'user-management/profile.html', {'profile': profile})

def update_profile(request):
    # Get the profile of the current user
    profile = get_object_or_404(UserProfile, user=request.user)

    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=profile)

    return render(request, 'user-management/profile_update.html', {'form': form})
