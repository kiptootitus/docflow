"""
DocFlow AI — users/urls.py

All auth + user management routes.
Mount this under /api/v1/auth/ in your root urls.py:

    path("api/v1/auth/", include("users.urls")),
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ChangePasswordView,
    GoogleLoginView,
    LoginView,
    LogoutView,
    MeView,
    MyAuditLogsView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ResendVerificationView,
    TOTPVerifyLoginView,
    UserDetailView,
    UserListView,
    UserRegistrationView,
    UserRestoreView,
    VerifyEmailView,
)

urlpatterns = [
    # ── Auth ────────────────────────────────────────────────────────────────
    path("register/",               UserRegistrationView.as_view(),  name="user-register"),
    path("login/",                  LoginView.as_view(),              name="user-login"),
    path("login/verify-totp/",      TOTPVerifyLoginView.as_view(),    name="user-login-totp"),
    path("logout/",                 LogoutView.as_view(),             name="user-logout"),   # ← ADDED
    path("google/",                 GoogleLoginView.as_view(),        name="user-google-login"),

    # ── Token refresh ────────────────────────────────────────────────────────
    path("token/refresh/",          TokenRefreshView.as_view(),       name="token-refresh"),

    # ── Email verification ───────────────────────────────────────────────────
    path("verify-email/",           VerifyEmailView.as_view(),        name="user-verify-email"),
    path("resend-verification/",    ResendVerificationView.as_view(), name="user-resend-verification"),

    # ── Password reset ───────────────────────────────────────────────────────
    path("password-reset/",         PasswordResetRequestView.as_view(), name="user-password-reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="user-password-reset-confirm"),

    # ── Authenticated user ───────────────────────────────────────────────────
    path("me/",                     MeView.as_view(),                 name="user-me"),
    path("me/change-password/",     ChangePasswordView.as_view(),     name="user-change-password"),
    path("me/audit-logs/",          MyAuditLogsView.as_view(),        name="user-audit-logs"),

    # ── Admin ────────────────────────────────────────────────────────────────
    path("users/",                  UserListView.as_view(),           name="user-list"),
    path("users/<uuid:pk>/",        UserDetailView.as_view(),         name="user-detail"),
    path("users/<uuid:pk>/restore/",UserRestoreView.as_view(),        name="user-restore"),
]