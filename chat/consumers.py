import json
import base64
import logging
from bson import ObjectId
from datetime import datetime
from django.core.cache import cache
from django.core.files.base import ContentFile
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from jwt import decode as jwt_decode
from jwt.exceptions import InvalidTokenError
from urllib.parse import parse_qs
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from chat.mongo_utils import get_messages_collection

logger = logging.getLogger(__name__)
User = get_user_model()


class ChatConsumer(WebsocketConsumer):
    """WebSocket consumer for chat functionality following original structure."""

    def connect(self):
        """Handle WebSocket connection."""
        try:
            query_string = self.scope["query_string"].decode()
            query_params = parse_qs(query_string)
            token = query_params.get("token", [None])[0]

            user = self.get_user_from_token(token)
            if not user or not user.is_authenticated:
                logger.warning("Unauthorized connection attempt")
                self.close()
                return

            self.scope["user"] = user
            self.user = user
            self.username = user.username

            async_to_sync(self.channel_layer.group_add)(
                self.username, self.channel_name
            )
            self.accept()

            cache.set(f"user_status_{self.username}", "online", timeout=None)
            cache.set(
                f"user_last_seen_{self.username}", datetime.utcnow(), timeout=None
            )

            self.send(
                text_data=json.dumps(
                    {
                        "source": "connection",
                        "data": {
                            "message": "connected",
                            "username": self.username,
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                    }
                )
            )

            # Send any pending messages
            self.send_pending_messages()

        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            self.close()

    def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        try:
            if hasattr(self, "username"):
                async_to_sync(self.channel_layer.group_discard)(
                    self.username, self.channel_name
                )
                cache.set(f"user_status_{self.username}", "offline", timeout=None)
                cache.set(
                    f"user_last_seen_{self.username}",
                    datetime.utcnow(),
                    timeout=60 * 60 * 24 * 30,
                )
                logger.info(f"User {self.username} disconnected")
        except Exception as e:
            logger.error(f"Disconnection error: {str(e)}")

    def receive(self, text_data):
        """Receive and route incoming messages."""
        try:
            data = json.loads(text_data)
            source = data.get("source")

            if not source:
                raise ValueError("Missing message source")

            handler_name = f'receive_{source.replace(".", "_")}'
            if not hasattr(self, handler_name):
                raise ValueError(f"Unknown message source: {source}")

            handler = getattr(self, handler_name)
            handler(data)

        except json.JSONDecodeError:
            self.send_error("invalid_json", "Invalid JSON format")
        except ValueError as e:
            self.send_error("invalid_request", str(e))
        except Exception as e:
            logger.error(f"Message handling error: {str(e)}")
            self.send_error("server_error", "Internal server error")

    # -------------------------------
    # Message Handlers (following original structure)
    # -------------------------------

    def receive_message_send(self, data):
        """Handle sending a new message."""
        required_fields = ["room_id", "sender", "receiver", "message"]
        if not all(field in data.get("data", {}) for field in required_fields):
            self.send_error("validation_error", "Missing required fields")
            return

        message_data = data["data"]
        if message_data["sender"] != self.username:
            self.send_error("permission_denied", "Cannot send messages as another user")
            return

        messages_collection = get_messages_collection()
        message_doc = {
            "room_id": message_data["room_id"],
            "sender": message_data["sender"],
            "receiver": message_data["receiver"],
            "message": message_data["message"],
            "timestamp": datetime.utcnow(),
            "is_read": False,
            "delivered": False,
        }

        # Handle file attachment
        if message_data.get("file") and message_data.get("filename"):
            try:
                file_data = base64.b64decode(message_data["file"])
                message_doc["file"] = {
                    "filename": message_data["filename"],
                    "size": len(file_data),
                    "data": file_data,
                    "content_type": message_data.get(
                        "content_type", "application/octet-stream"
                    ),
                }
            except Exception as e:
                logger.error(f"File processing error: {str(e)}")
                self.send_error("file_error", "Invalid file data")
                return

        # Store message
        result = messages_collection.insert_one(message_doc)
        message_id = str(result.inserted_id)

        # Prepare response
        payload = {
            "source": "message.send",
            "data": {
                "message_id": message_id,
                "room_id": message_data["room_id"],
                "sender": message_data["sender"],
                "receiver": message_data["receiver"],
                "message": message_data["message"],
                "timestamp": message_doc["timestamp"].isoformat(),
                "delivered": False,
            },
        }

        # Add file info if present
        if "file" in message_doc:
            payload["data"]["file"] = {
                "filename": message_doc["file"]["filename"],
                "size": message_doc["file"]["size"],
                "content_type": message_doc["file"]["content_type"],
            }

        # Send to sender (echo)
        self.send(text_data=json.dumps(payload))

        # Send to receiver
        self.send_group(message_data["receiver"], payload)

        # Update delivery status
        messages_collection.update_one(
            {"_id": ObjectId(message_id)}, {"$set": {"delivered": True}}
        )

    def receive_message_read(self, data):
        """Handle marking message as read."""
        if "message_id" not in data.get("data", {}):
            self.send_error("validation_error", "Missing message_id")
            return

        message_id = data["data"]["message_id"]
        messages_collection = get_messages_collection()

        result = messages_collection.update_one(
            {"_id": ObjectId(message_id), "receiver": self.username},
            {"$set": {"is_read": True, "read_at": datetime.utcnow()}},
        )

        if result.modified_count == 0:
            self.send_error("not_found", "Message not found or already read")
            return

        self.send_group(
            self.username,
            {
                "source": "message.read",
                "data": {
                    "message_id": message_id,
                    "status": "read",
                    "read_at": datetime.utcnow().isoformat(),
                },
            },
        )

    def receive_message_edit(self, data):
        """Handle editing a message."""
        required_fields = ["message_id", "new_message"]
        if not all(field in data.get("data", {}) for field in required_fields):
            self.send_error("validation_error", "Missing required fields")
            return

        message_data = data["data"]
        messages_collection = get_messages_collection()

        result = messages_collection.update_one(
            {"_id": ObjectId(message_data["message_id"]), "sender": self.username},
            {
                "$set": {
                    "message": message_data["new_message"],
                    "edited": True,
                    "edited_at": datetime.utcnow(),
                }
            },
        )

        if result.modified_count == 0:
            self.send_error("not_found", "Message not found or not authorized to edit")
            return

        # Get updated message to broadcast
        updated_message = messages_collection.find_one(
            {"_id": ObjectId(message_data["message_id"])}
        )

        payload = {
            "source": "message.edit",
            "data": {
                "message_id": message_data["message_id"],
                "room_id": updated_message["room_id"],
                "sender": updated_message["sender"],
                "receiver": updated_message["receiver"],
                "new_message": message_data["new_message"],
                "edited_at": updated_message.get(
                    "edited_at", datetime.utcnow()
                ).isoformat(),
            },
        }

        self.send_group(updated_message["sender"], payload)
        self.send_group(updated_message["receiver"], payload)

    def receive_message_delete(self, data):
        """Handle deleting a message."""
        if "message_id" not in data.get("data", {}):
            self.send_error("validation_error", "Missing message_id")
            return

        message_id = data["data"]["message_id"]
        messages_collection = get_messages_collection()

        # First get the message to determine participants
        message = messages_collection.find_one({"_id": ObjectId(message_id)})

        if not message:
            self.send_error("not_found", "Message not found")
            return

        if message["sender"] != self.username:
            self.send_error(
                "permission_denied", "Not authorized to delete this message"
            )
            return

        # Delete the message
        result = messages_collection.delete_one({"_id": ObjectId(message_id)})

        if result.deleted_count == 0:
            self.send_error("server_error", "Failed to delete message")
            return

        payload = {
            "source": "message.delete",
            "data": {
                "message_id": message_id,
                "room_id": message["room_id"],
                "deleted_by": self.username,
                "deleted_at": datetime.utcnow().isoformat(),
            },
        }

        self.send_group(message["sender"], payload)
        self.send_group(message["receiver"], payload)

    def receive_message_type(self, data):
        """Handle typing indicators."""
        required_fields = ["room_id", "receiver"]
        if not all(field in data.get("data", {}) for field in required_fields):
            self.send_error("validation_error", "Missing required fields")
            return

        self.send_group(
            data["data"]["receiver"],
            {
                "source": "message.type",
                "data": {
                    "room_id": data["data"]["room_id"],
                    "sender": self.username,
                    "is_typing": data["data"].get("is_typing", True),
                },
            },
        )

    def receive_user_status(self, data):
        """Handle user status requests."""
        if "username" not in data.get("data", {}):
            self.send_error("validation_error", "Missing username")
            return

        username = data["data"]["username"]
        status = cache.get(f"user_status_{username}", "offline")
        last_seen = cache.get(f"user_last_seen_{username}")

        self.send(
            text_data=json.dumps(
                {
                    "source": "user.status",
                    "data": {
                        "username": username,
                        "status": status,
                        "last_seen": last_seen.isoformat() if last_seen else None,
                    },
                }
            )
        )

    def receive_user_list(self, data):
        """Handle request for user list."""
        try:
            current_user_id = self.scope["user"].id
            users = User.objects.exclude(id=current_user_id).only(
                "username", "email", "first_name", "last_name"
            )

            user_list = []
            for user in users:
                status = cache.get(f"user_status_{user.username}", "offline")
                last_seen = cache.get(f"user_last_seen_{user.username}")

                user_list.append(
                    {   
                        "id": str(user.id),
                        "username": user.username,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "status": status,
                        "last_seen": last_seen.isoformat() if last_seen else None,
                    }
                )

            self.send(text_data=json.dumps({"source": "user.list", "data": user_list}))
        except Exception as e:
            logger.error(f"User list error: {str(e)}")
            self.send_error("server_error", "Failed to fetch users")

    def receive_message_list(self, data):
        """Handle request for message history."""
        try:
            room_id = data.get("data", {}).get("room_id")
            if not room_id:
                self.send_error("validation_error", "Missing room_id")
                return

            page = int(data.get("data", {}).get("page", 0))
            page_size = min(int(data.get("data", {}).get("page_size", 20)), 100)
            skip = page * page_size

            messages_collection = get_messages_collection()
            query = {
                "room_id": room_id,
                "$or": [{"sender": self.username}, {"receiver": self.username}],
            }

            total_count = messages_collection.count_documents(query)
            messages_cursor = (
                messages_collection.find(query)
                .sort("timestamp", -1)
                .skip(skip)
                .limit(page_size)
            )

            messages = []
            for msg in messages_cursor:
                message_data = {
                    "message_id": str(msg["_id"]),
                    "room_id": msg["room_id"],
                    "sender": msg["sender"],
                    "receiver": msg["receiver"],
                    "message": msg["message"],
                    "timestamp": msg["timestamp"].isoformat(),
                    "is_read": msg.get("is_read", False),
                    "delivered": msg.get("delivered", False),
                    "edited": msg.get("edited", False),
                    "edited_at": (
                        msg.get("edited_at", "").isoformat()
                        if msg.get("edited_at")
                        else None
                    ),
                }

                if "file" in msg:
                    message_data["file"] = {
                        "filename": msg["file"]["filename"],
                        "size": msg["file"]["size"],
                        "content_type": msg["file"]["content_type"],
                    }

                messages.append(message_data)

            messages.reverse()  # Return in chronological order

            self.send(
                text_data=json.dumps(
                    {
                        "source": "message.list",
                        "data": {
                            "messages": messages,
                            "page": page,
                            "page_size": page_size,
                            "total": total_count,
                            "has_more": (skip + page_size) < total_count,
                        },
                    }
                )
            )

        except Exception as e:
            logger.error(f"Message list error: {str(e)}")
            self.send_error("server_error", "Failed to fetch messages")

    def receive_ping(self, data):
        """Handle ping/pong keepalive."""
        self.send(text_data=json.dumps({"source": "pong"}))

    # -------------------------------
    # Utility Methods
    # -------------------------------

    def get_user_from_token(self, token):
        """Authenticate user from JWT token."""
        try:
            if not token:
                return AnonymousUser()

            if token.startswith("Bearer "):
                token = token[7:]

            payload = jwt_decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            user = User.objects.get(id=payload["user_id"])

            if not user.is_active:
                raise InvalidTokenError("User account is disabled")

            return user
        except Exception as e:
            logger.warning(f"Token validation failed: {str(e)}")
            return AnonymousUser()

    def send_group(self, group, payload):
        """Send message to a channel group."""
        async_to_sync(self.channel_layer.group_send)(
            group, {"type": "broadcast_group", **payload}
        )

    def broadcast_group(self, event):
        """Handle messages sent to groups."""
        event.pop("type", None)
        self.send(text_data=json.dumps(event))

    def send_error(self, error_type, message):
        """Send error message to client."""
        self.send(
            text_data=json.dumps(
                {"source": "error", "error": {"type": error_type, "message": message}}
            )
        )

    def send_pending_messages(self):
        """Send any undelivered messages to user upon connection."""
        if not hasattr(self, "username"):
            return

        messages_collection = get_messages_collection()
        pending_messages = messages_collection.find(
            {"receiver": self.username, "delivered": False}
        ).sort("timestamp", 1)

        for msg in pending_messages:
            payload = {
                "source": "message.send",
                "data": {
                    "message_id": str(msg["_id"]),
                    "room_id": msg["room_id"],
                    "sender": msg["sender"],
                    "receiver": msg["receiver"],
                    "message": msg["message"],
                    "timestamp": msg["timestamp"].isoformat(),
                    "delivered": True,
                },
            }

            if "file" in msg:
                payload["data"]["file"] = {
                    "filename": msg["file"]["filename"],
                    "size": msg["file"]["size"],
                    "content_type": msg["file"]["content_type"],
                }

            self.send(text_data=json.dumps(payload))

            # Update delivery status
            messages_collection.update_one(
                {"_id": msg["_id"]}, {"$set": {"delivered": True}}
            )
