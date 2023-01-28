from django.apps import apps
from django.contrib import admin


for m in apps.all_models['server'].values():
    admin.site.register(m)
