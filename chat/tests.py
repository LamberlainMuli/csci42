# chat/models.py

from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q, Max

# Ensure your CustomUser model is correctly referenced
User = settings.AUTH_USER_MODEL

class ChatRoomManager(models.Manager):
    def get_or_create_chat(self, user1, user2):
        """
        Gets or creates a chat room between two users.
        Ensures only one room exists per pair, regardless of order.
        """
        if user1 == user2:
            raise ValueError("Cannot create chat room with the same user.")

        # Canonical ordering: smaller user ID first
        p1, p2 = sorted([user1, user2], key=lambda u: u.pk)

        room = self.filter(participant1=p1, participant2=p2).first()
        if not room:
            room = self.create(participant1=p1, participant2=p2)
            print(f"Created new chat room between {p1.username} and {p2.username}")
        return room

    def get_user_chat_rooms(self, user):
        """
        Gets all chat rooms a user participates in, ordered by last message.
        """
        return self.filter(
            Q(participant1=user) | Q(participant2=user)
        ).annotate(
            last_message_time=Max('messages__timestamp') # Annotate with the timestamp of the latest message
        ).order_by('-last_message_time') # Order by the latest message first


class ChatRoom(models.Model):
    """Represents a conversation between two users."""
    # Store participants with canonical ordering (smaller ID first)
    participant1 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='chat_rooms_as_p1'
    )
    participant2 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='chat_rooms_as_p2'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Optional: Track last message time for ordering chat list
    # last_updated = models.DateTimeField(auto_now=True) # Can use annotation instead

    objects = ChatRoomManager()

    class Meta:
        unique_together = ('participant1', 'participant2')
        ordering = ['-created_at'] # Default ordering

    def __str__(self):
        return f"Chat between {self.participant1.username} and {self.participant2.username}"

    def get_absolute_url(self):
        return reverse('chat:chat_room', kwargs={'room_id': self.pk})

    def get_other_participant(self, user):
        """Given one user, return the other participant."""
        if self.participant1 == user:
            return self.participant2
        elif self.participant2 == user:
            return self.participant1
        else:
            # This should not happen if the user is correctly part of the chat
            return None

    def get_last_message(self):
        """Returns the most recent message in the room, or None."""
        return self.messages.order_by('-timestamp').first()


class ChatMessage(models.Model):
    """Represents a single message within a chat room."""
    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False) # Optional: track read status

    class Meta:
        ordering = ['timestamp'] # Order messages chronologically

    def __str__(self):
        return f"Msg by {self.sender.username} in Room {self.room.id} at {self.timestamp:%Y-%m-%d %H:%M}"