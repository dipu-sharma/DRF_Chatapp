# chat/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'profile_picture', 'online_status']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)  # Hashes the password
        user.save()
        return user

class MessageSerializer(serializers.Serializer):
    room_id = serializers.CharField()
    content = serializers.CharField()
    # sender = serializers.CharField()

class RoomSerializer(serializers.Serializer):
    _id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    participants = serializers.ListField(child=serializers.CharField())
    created_by = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)