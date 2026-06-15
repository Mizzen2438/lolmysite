from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("post-login/", views.post_login, name="post_login"),
    path("onboarding/terms/", views.terms, name="terms"),
    path("onboarding/profile/", views.profile_setup, name="profile_setup"),
    path("mypage/", views.mypage, name="mypage"),
    path("mypage/profile/", views.profile_edit, name="profile_edit"),
]
