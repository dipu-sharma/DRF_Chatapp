# chat/mongo_utils.py
from pymongo import MongoClient
from django.conf import settings

def get_mongodb_connection():
    client = MongoClient(settings.MONGODB_SETTINGS['host'])
    db = client[settings.MONGODB_SETTINGS['db']]
    return db

def get_messages_collection():
    db = get_mongodb_connection()
    return db['messages']

def get_rooms_collection():
    db = get_mongodb_connection()
    return db['rooms']

def get_direct_messages_collection():
    db = get_mongodb_connection()
    return db['dm_message']