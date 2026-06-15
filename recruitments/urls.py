from django.urls import path

from . import views

urlpatterns = [
    path("recruitments/", views.recruitment_list, name="recruitment_list"),
    path("recruitments/new/", views.recruitment_create, name="recruitment_create"),
    path("recruitments/<int:pk>/", views.recruitment_detail, name="recruitment_detail"),
    path("recruitments/<int:pk>/edit/", views.recruitment_edit, name="recruitment_edit"),
    path("recruitments/<int:pk>/close/", views.recruitment_close, name="recruitment_close"),
    path("recruitments/<int:pk>/delete/", views.recruitment_delete, name="recruitment_delete"),
]
