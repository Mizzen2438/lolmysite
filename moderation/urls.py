from django.urls import path

from . import views

urlpatterns = [
    path("report/<str:target_type>/<int:target_id>/", views.report_create, name="report_create"),
    path("block/<int:user_id>/", views.block_user, name="block_user"),
    path("unblock/<int:user_id>/", views.unblock_user, name="unblock_user"),
    path("mypage/blocked/", views.blocked_list, name="blocked_list"),
]
