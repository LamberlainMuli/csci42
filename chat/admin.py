# chat/admin.py

from django.contrib import admin
from .models import ChatRoom, ChatMessage

class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    fields = ('sender', 'content', 'timestamp', 'is_read')
    readonly_fields = ('sender', 'content', 'timestamp')
    extra = 0
    ordering = ('timestamp',)

@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'participant1', 'participant2', 'created_at', 'last_message_timestamp')
    search_fields = ('participant1__username', 'participant2__username', 'participant1__email', 'participant2__email')
    list_filter = ('created_at',)
    readonly_fields = ('created_at',)
    inlines = [ChatMessageInline]

    def last_message_timestamp(self, obj):
        last_msg = obj.get_last_message()
        return last_msg.timestamp if last_msg else None
    last_message_timestamp.short_description = 'Last Message Time'

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'room_id', 'sender', 'content_snippet', 'timestamp', 'is_read')
    search_fields = ('sender__username', 'content', 'room__id')
    list_filter = ('timestamp', 'is_read', 'sender')
    readonly_fields = ('timestamp',)
    list_editable = ('is_read',) # Allow marking as read from admin

    def content_snippet(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_snippet.short_description = 'Content'

    def room_id(self, obj):
        return obj.room.id
    room_id.short_description = 'Room ID'