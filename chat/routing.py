from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(
        r"api/chat/(?P<room_id>[0-9a-fA-F]{24})/$", consumers.ChatConsumer.as_asgi()
    ),
    re_path(
        r"api/chat/$", consumers.ChatConsumer.as_asgi()
    ),
]
