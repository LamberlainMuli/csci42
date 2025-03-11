from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser, UserProfile


class CustomUserRegistrationForm(UserCreationForm):
    email = forms.EmailField()
    username = forms.CharField(max_length=255)

    # Only allow 'buyer' and 'seller' roles for registration
    role = forms.ChoiceField(choices=[('buyer', 'Buyer'), ('seller', 'Seller')], required=True) 

    # Modify labels for password1 and password2
    # password1 is Password
    # password2 is Confirm Password
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter your password'})
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Re-enter your password'})
    )

    class Meta:
        model = CustomUser
        fields = ['email', 'username', 'role', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = self.cleaned_data['role']
        if commit:
            user.save()
        return user

    def confirm_password(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 != password2:
            raise forms.ValidationError("Password do not match.")
        return password2

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = '__all__'
