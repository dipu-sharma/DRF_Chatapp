# chat_project/urls.py
from django.urls import path, include
from rest_framework.authtoken.views import obtain_auth_token
from chat.views import UserCreateView, CustomAuthToken, UserListView, RoomCreateView, MessageCreateView, MessageHistoryView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
urlpatterns = [
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/register/', UserCreateView.as_view(), name='register'),
    path('api/login/', CustomAuthToken.as_view(), name='login'),
    path('api/users/', UserListView.as_view(), name='user-list'),
    path('api/rooms/', RoomCreateView.as_view(), name='room-create'),
    path('api/messages/', MessageCreateView.as_view(), name='message-list'),
    path('api/messages/history/', MessageHistoryView.as_view(), name='message-history'),
]