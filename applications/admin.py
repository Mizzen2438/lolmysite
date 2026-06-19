from django.contrib import admin

from .models import Application


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("id", "recruitment", "applicant", "desired_lane", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("applicant__discord_name",)
    raw_id_fields = ("recruitment", "applicant")
