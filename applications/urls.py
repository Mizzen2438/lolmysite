from django.urls import path

from . import views

urlpatterns = [
    path("recruitments/<int:pk>/apply/", views.apply_view, name="application_apply"),
    path("applications/<int:pk>/approve/", views.approve_view, name="application_approve"),
    path("applications/<int:pk>/reject/", views.reject_view, name="application_reject"),
    path("applications/<int:pk>/withdraw/", views.withdraw_view, name="application_withdraw"),
    path("applications/<int:pk>/decline/", views.decline_view, name="application_decline"),
]
