from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # re_path(r'ws/chat/room/(?P<room_id>\w+)/$', consumers.RoomChatConsumer.as_asgi()),
    # re_path(r'ws/chat/(?P<recipient_id>\w+)/$', consumers.DirectMessageConsumer.as_asgi()),
    re_path(r'ws/test/$', consumers.RoomChatConsumer.as_asgi()),
]

