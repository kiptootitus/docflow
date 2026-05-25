from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from .views import (
    RegisterView, ProfileView, ChangePasswordView, logout_view,
    GoogleLoginView, PasswordResetRequestView, PasswordResetConfirmView
)

urlpatterns = [
    # Auth Basics & JWT
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", TokenObtainPairView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token-verify"),
    path("logout/", logout_view, name="logout"),

    # Profile management
    path("me/", ProfileView.as_view(), name="profile"),
    path("me/change-password/", ChangePasswordView.as_view(), name="change-password"),

    # Password Reset flow
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),

    # Social Login Flow
    path("google/", GoogleLoginView.as_view(), name="google-login"),
]