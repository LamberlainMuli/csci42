# chat/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import Http404, HttpResponseForbidden
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from .models import ChatRoom, ChatMessage
from .forms import ChatMessageForm

User = get_user_model()

@login_required
def chat_list_view(request):
    """Displays the list of active chat rooms for the logged-in user."""
    chat_rooms = ChatRoom.objects.get_user_chat_rooms(request.user)

    rooms_with_details = []
    for room in chat_rooms:
        other_participant = room.get_other_participant(request.user)
        last_message = room.get_last_message()
        # Optional: Add unread count later
        rooms_with_details.append({
            'room': room,
            'other_participant': other_participant,
            'last_message': last_message,
        })

    context = {
        'chat_rooms': rooms_with_details,
    }
    return render(request, 'chat/chat_list.html', context)


@login_required
def start_chat_with_seller(request, seller_id):
    """Initiates or finds a chat with a specific seller and redirects to the room."""
    seller = get_object_or_404(User, id=seller_id)

    if request.user == seller:
        # Prevent users from chatting with themselves
        # Redirect to chat list or show a message
        return redirect('chat:chat_list')

    # Use the manager method to find or create the room
    chat_room = ChatRoom.objects.get_or_create_chat(request.user, seller)

    # Redirect to the chat room view
    return redirect('chat:chat_room', room_id=chat_room.id)


login_required
def chat_room_view(request, room_id):
    """Displays messages in a chat room and handles sending new messages."""
    try:
        # Fetch the room and participants' profiles
        chat_room = ChatRoom.objects.select_related(
            'participant1__profile', 'participant2__profile'
        ).get(id=room_id)

        # Check if the current user is a participant
        if request.user not in [chat_room.participant1, chat_room.participant2]:
             raise Http404("Chat room not found or you are not a participant.")

    except ChatRoom.DoesNotExist:
        raise Http404("Chat room not found.")

    other_participant = chat_room.get_other_participant(request.user)

    # --- Mark messages from the other participant as read ---
    # Do this *before* fetching messages for display to ensure the count updates
    with transaction.atomic(): # Ensure update happens reliably
        unread_messages = chat_room.messages.filter(
            sender=other_participant,
            is_read=False
        ).select_for_update() # Lock rows before updating

        updated_count = unread_messages.update(is_read=True)
        if updated_count > 0:
            print(f"Marked {updated_count} messages as read in room {room_id} for user {request.user.username}") # Use logger

    # --- Fetch messages for display ---
    messages = chat_room.messages.select_related('sender__profile').order_by('timestamp')

    # --- Handle sending new messages ---
    if request.method == 'POST':
        form = ChatMessageForm(request.POST)
        if form.is_valid():
            content = form.cleaned_data['content']
            # Create and save the new message
            ChatMessage.objects.create(
                room=chat_room,
                sender=request.user,
                content=content
                # is_read defaults to False
            )
            # No need to update room timestamp if ordering list by annotation
            return redirect('chat:chat_room', room_id=room_id)
        # else: form invalid, fall through to render with errors
    else:
        form = ChatMessageForm()

    context = {
        'chat_room': chat_room,
        'other_participant': other_participant,
        'chat_messages': messages,
        'form': form,
    }
    return render(request, 'chat/chat_room.html', context)