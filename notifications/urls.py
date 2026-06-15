from django.urls import path

from . import views

urlpatterns = [
    path("notifications/", views.notification_list, name="notification_list"),
    path("notifications/read/", views.mark_all_read, name="notifications_mark_read"),
]
