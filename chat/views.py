from django.shortcuts import render
from datetime import datetime, time, timedelta
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from .serializers import UserSerializer, MessageSerializer, RoomSerializer
from .mongo_utils import get_messages_collection, get_rooms_collection
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from collections import defaultdict
User = get_user_model()

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.pagination import PageNumberPagination

class MessagePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100

class CustomAuthToken(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        
        if response.status_code == status.HTTP_200_OK:
            user = User.objects.get(username=request.data['username'])
            user.online_status = True
            user.is_staff = True
            user.save()
            response.data['user_id'] = user.pk
            response.data['username'] = user.username
        
        return response

class UserCreateView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        
        if response.status_code == status.HTTP_201_CREATED:
            user = User.objects.get(username=request.data['username'])
            refresh = RefreshToken.for_user(user)
            
            response.data['tokens'] = {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        
        return response

class UserListView(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

class RoomCreateView(generics.CreateAPIView):
    serializer_class = RoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        rooms_collection = get_rooms_collection()
        room_data = serializer.validated_data.copy()
        
        room_data['created_by'] = request.user.username
        room_data['created_at'] = datetime.now()
        result = rooms_collection.insert_one(room_data)
        room_data['_id'] = str(result.inserted_id)

        room_data['created_at'] = room_data['created_at'].isoformat()
        
        return Response(room_data, status=status.HTTP_201_CREATED)

class MessageCreateView(generics.CreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        messages_collection = get_messages_collection()
        message_data = serializer.validated_data
        message_data['sender'] = request.user.username
        message_data['timestamp'] = datetime.now()
        result = messages_collection.insert_one(message_data)
        message_data['_id'] = str(result.inserted_id)
        self.notify_room(message_data['room_id'], message_data)
        
        return Response(message_data, status=status.HTTP_201_CREATED)

    def notify_room(self, room_id, message):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'chat_{room_id}',
            {
                'type': 'chat_message',
                'message': message['content'],
                'sender': message['sender'],
                'timestamp': str(message['timestamp'])
            }
        )

class MessageHistoryView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = MessagePagination

    def get(self, request, *args, **kwargs):
        room_id = request.query_params.get('room_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not room_id:
            return Response(
                {"error": "room_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        query = {"room_id": room_id}

        # If no date range is provided, default to today
        if not start_date and not end_date:
            today = datetime.now().date()
            start = datetime.combine(today, time.min)
            end = datetime.combine(today, time.max)
        else:
            try:
                start = datetime.fromisoformat(start_date) if start_date else datetime.min
                end = datetime.fromisoformat(end_date) if end_date else datetime.max
            except ValueError:
                return Response(
                    {"error": "start_date and end_date must be in ISO format"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        query["timestamp"] = {"$gte": start, "$lte": end}

        messages_collection = get_messages_collection()
        messages_cursor = messages_collection.find(query).sort("timestamp", -1)
        messages = list(messages_cursor)

        # Format and group messages
        grouped = defaultdict(list)
        now = datetime.now()
        today = now.date()
        yesterday = today - timedelta(days=1)

        for msg in messages:
            msg['_id'] = str(msg['_id'])
            ts = msg['timestamp']
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            msg['timestamp'] = ts.isoformat()

            msg_date = ts.date()
            if msg_date == today:
                group_key = "today"
            elif msg_date == yesterday:
                group_key = "yesterday"
            else:
                group_key = msg_date.strftime("%d-%m-%Y")

            grouped[group_key].append(msg)

        # Optional pagination: flatten all messages if needed
        all_messages = []
        for date_key in grouped:
            all_messages.extend(grouped[date_key])

        page = self.paginate_queryset(all_messages)
        if page is not None:
            # Re-group paginated results
            paginated_grouped = defaultdict(list)
            for msg in page:
                ts = datetime.fromisoformat(msg['timestamp'])
                msg_date = ts.date()
                if msg_date == today:
                    group_key = "today"
                elif msg_date == yesterday:
                    group_key = "yesterday"
                else:
                    group_key = msg_date.strftime("%d-%m-%Y")
                paginated_grouped[group_key].append(msg)

            return self.get_paginated_response(paginated_grouped)

        return Response(grouped)