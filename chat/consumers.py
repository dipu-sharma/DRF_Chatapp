# chat/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .mongo_utils import get_messages_collection, get_rooms_collection
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async
from jwt import decode as jwt_decode
from jwt.exceptions import InvalidTokenError
from django.contrib.auth.models import AnonymousUser
from django.conf import settings
import datetime

User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
            # Get token from query string
        query_string = self.scope['query_string'].decode()
        token_key = query_string.split('token=')[1]
        
        user = await self.get_user_from_token(token_key)
        
        if not user.is_authenticated:
            await self.close()
            return
        
        self.scope['user'] = user
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_id}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        sender = text_data_json['sender']

        # Save message to MongoDB
        await self.save_message(self.room_id, sender, message)

        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'sender': sender
            }
        )

    async def chat_message(self, event):
        message = event['message']
        sender = event['sender']

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'sender': sender
        }))

    @database_sync_to_async
    def get_user_from_token(token):
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            payload = jwt_decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            return User.objects.get(id=payload['user_id'])
        except (InvalidTokenError, User.DoesNotExist):
            return AnonymousUser()