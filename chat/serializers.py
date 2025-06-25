# chat/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'profile_picture', 'online_status']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        Token.objects.create(user=user)
        return user

class MessageSerializer(serializers.Serializer):
    room_id = serializers.CharField()
    content = serializers.CharField()
    sender = serializers.CharField()

class RoomSerializer(serializers.Serializer):
    name = serializers.CharField()
    participants = serializers.ListField(child=serializers.CharField())