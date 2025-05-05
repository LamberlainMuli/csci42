# chat/forms.py

from django import forms
from .models import ChatMessage

class ChatMessageForm(forms.Form):
    """Form for sending a chat message."""
    content = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Type your message here...',
            'class': 'form-control', # Add bootstrap class
            'aria-label': 'Chat message input'
        }),
        label="" # Hide the default label
    )