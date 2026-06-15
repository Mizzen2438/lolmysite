from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("dev-login/", views.dev_login, name="dev_login"),
    path("post-login/", views.post_login, name="post_login"),
    path("onboarding/terms/", views.terms, name="terms"),
    path("onboarding/profile/", views.profile_setup, name="profile_setup"),
    path("onboarding/riot/", views.riot_link, name="riot_link"),
    path("mypage/", views.mypage, name="mypage"),
    path("mypage/profile/", views.profile_edit, name="profile_edit"),
    path("mypage/riot/refresh/", views.riot_refresh, name="riot_refresh"),
]
