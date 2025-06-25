import json
import datetime
import base64
import os
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async
from jwt import decode as jwt_decode
from jwt.exceptions import InvalidTokenError
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from .mongo_utils import get_messages_collection, get_direct_messages_collection

User = get_user_model()


class BaseChatConsumer(AsyncWebsocketConsumer):
    @staticmethod
    def get_token_from_query(query_string):
        if 'token=' in query_string:
            return query_string.split('token=')[1]
        return ''

    @database_sync_to_async
    def get_user_from_token(self, token):
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            payload = jwt_decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            return User.objects.get(id=payload['user_id'])
        except (InvalidTokenError, User.DoesNotExist):
            return AnonymousUser()

    def save_file(self, file_data):
        # In production, replace with S3 or secure storage
        file_bytes = base64.b64decode(file_data['content'])
        filename = file_data['name']
        ext = filename.split('.')[-1]
        filepath = os.path.join('media/uploads', filename)

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(file_bytes)

        file_url = f'/media/uploads/{filename}'
        return file_url, ext


class RoomChatConsumer(BaseChatConsumer):
    async def connect(self):
        token_key = self.get_token_from_query(self.scope['query_string'].decode())
        user = await self.get_user_from_token(token_key)

        if not user or isinstance(user, AnonymousUser):
            await self.close()
            return

        self.scope['user'] = user
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'room_{self.room_id}'

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data.get('message', '')
        file_data = data.get('file')
        sender = str(self.scope['user'].id)

        saved_msg = await self.save_room_message(self.room_id, sender, message, file_data)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': saved_msg['message'],
                'sender': sender,
                'timestamp': saved_msg['timestamp'],
                'file_url': saved_msg.get('file_url'),
                'file_type': saved_msg.get('file_type'),
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def save_room_message(self, room_id, sender_id, message, file_data):
        collection = get_messages_collection()
        timestamp = datetime.datetime.utcnow()
        file_url, file_type = (None, None)

        if file_data:
            file_url, file_type = self.save_file(file_data)

        msg = {
            'room_id': room_id,
            'sender_id': sender_id,
            'message': message,
            'timestamp': timestamp,
            'file_url': file_url,
            'file_type': file_type
        }
        collection.insert_one(msg)
        msg['timestamp'] = str(timestamp)
        return msg


class DirectMessageConsumer(BaseChatConsumer):
    async def connect(self):
        token_key = self.get_token_from_query(self.scope['query_string'].decode())
        user = await self.get_user_from_token(token_key)

        if not user or isinstance(user, AnonymousUser):
            await self.close()
            return

        self.scope['user'] = user
        self.user_id = str(user.id)
        self.recipient_id = self.scope['url_route']['kwargs']['recipient_id']
        sorted_ids = sorted([self.user_id, self.recipient_id])
        self.chat_id = f'dm_{sorted_ids[0]}_{sorted_ids[1]}'

        await self.channel_layer.group_add(self.chat_id, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.chat_id, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data.get('message', '')
        file_data = data.get('file')
        sender_id = self.user_id
        recipient_id = self.recipient_id

        saved_msg = await self.save_direct_message(sender_id, recipient_id, message, file_data)

        await self.channel_layer.group_send(
            self.chat_id,
            {
                'type': 'chat_message',
                'message': saved_msg['message'],
                'sender': sender_id,
                'recipient': recipient_id,
                'timestamp': saved_msg['timestamp'],
                'file_url': saved_msg.get('file_url'),
                'file_type': saved_msg.get('file_type'),
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def save_direct_message(self, sender_id, recipient_id, message, file_data):
        collection = get_direct_messages_collection()
        timestamp = datetime.datetime.utcnow()
        file_url, file_type = (None, None)

        if file_data:
            file_url, file_type = self.save_file(file_data)

        msg = {
            'sender_id': sender_id,
            'recipient_id': recipient_id,
            'message': message,
            'timestamp': timestamp,
            'file_url': file_url,
            'file_type': file_type
        }
        collection.insert_one(msg)
        msg['timestamp'] = str(timestamp)
        return msg
