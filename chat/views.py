from django.shortcuts import render
from datetime import datetime
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from .serializers import UserSerializer, MessageSerializer, RoomSerializer
from .mongo_utils import get_messages_collection, get_rooms_collection
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
User = get_user_model()

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
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
            user.save()
            
            # Add additional user data to the response
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
        room_data = serializer.validated_data
        
        # Add additional fields
        room_data['created_by'] = request.user.username
        room_data['created_at'] = datetime.now()
        
        # Insert into MongoDB
        result = rooms_collection.insert_one(room_data)
        room_data['id'] = str(result.inserted_id)
        
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
        message_data['id'] = str(result.inserted_id)
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

class MessageHistoryView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        room_id = request.query_params.get('room_id')
        # start_date = request.query_params.get('start_date')
        # end_date = request.query_params.get('end_date')

        # query = {"room_id": room_id}

        # if start_date:
        #     start = datetime.fromisoformat(start_date)
        #     query["timestamp"] = {"$gte": start}
            
        # if end_date:
        #     end = datetime.fromisoformat(end_date)
        #     if "timestamp" in query:
        #         query["timestamp"]["$lte"] = end
        #     else:
        #         query["timestamp"] = {"$lte": end}

        # messages = messages_collection.find(query).sort("timestamp", -1)
        if not room_id:
            return Response(
                {"error": "room_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        messages_collection = get_messages_collection()
        messages = list(messages_collection.find(
            {"room_id": room_id}
        ).sort("timestamp", 1))
        formatted_messages = []
        for msg in messages:
            msg['_id'] = str(msg['_id'])
            msg['timestamp'] = msg['timestamp'].isoformat()
            formatted_messages.append(msg)
        
        return Response(formatted_messages)