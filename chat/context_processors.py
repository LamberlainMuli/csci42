# chat/context_processors.py

from .models import ChatMessage, ChatRoom
from django.db.models import Q

def unread_chat_count(request):
    """
    Provides the count of unread chat messages for the logged-in user
    to the template context.
    """
    count = 0
    if request.user.is_authenticated:
        try:
            # Efficiently count unread messages where the user is a participant but not the sender
            count = ChatMessage.objects.filter(
                # Message is in a room where the user is participant1 OR participant2
                Q(room__participant1=request.user) | Q(room__participant2=request.user),
                # Message is unread
                is_read=False
            ).exclude(
                # Message was NOT sent by the current user
                sender=request.user
            ).count()
        except Exception as e:
            # Log error maybe, but don't break page load
            print(f"Error calculating unread chat count: {e}") # Replace with logging
            count = 0
            
    return {'unread_chat_count': count}