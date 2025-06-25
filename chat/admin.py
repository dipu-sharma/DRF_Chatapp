from django.contrib import admin

from django.apps import apps
from django.contrib.admin.sites import AlreadyRegistered

# Replace 'your_app_name' with the actual name of your Django app
app_models = apps.get_app_config('chat').get_models()

for model in app_models:
    try:
        admin.site.register(model)
    except AlreadyRegistered:
        pass