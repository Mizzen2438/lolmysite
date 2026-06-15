from django.contrib import admin

from .models import Block


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("user", "blocked_user", "created_at")
    raw_id_fields = ("user", "blocked_user")
