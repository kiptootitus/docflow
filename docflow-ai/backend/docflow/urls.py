"""
DocFlow AI - Root URL Configuration

This module defines the top-level URL patterns for the entire application.
All API endpoints are mounted under /api/v1/ following REST conventions.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

# API Documentation
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

# JWT Authentication
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

# ----------------------------------------------------------------------
# URL Patterns
# ----------------------------------------------------------------------

urlpatterns = [

    # ------------------------------------------------------------------
    # Django Admin
    # ------------------------------------------------------------------
    path("admin/", admin.site.urls),

    # ------------------------------------------------------------------
    # API Documentation
    # ------------------------------------------------------------------
    path(
        "api/schema/",
        SpectacularAPIView.as_view(),
        name="schema",
    ),

    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),

    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),

    # ------------------------------------------------------------------
    # Stripe Webhooks
    # ------------------------------------------------------------------
    path(
        "webhooks/stripe/",
        include("djstripe.urls", namespace="djstripe"),
    ),

    # ------------------------------------------------------------------
    # API v1
    # ------------------------------------------------------------------
    path(
        "api/v1/",
        include([

            # ----------------------------------------------------------
            # Authentication & Users
            # ----------------------------------------------------------
            path("auth/", include("users.urls")),

            # JWT Tokens
            path(
                "auth/token/",
                TokenObtainPairView.as_view(),
                name="token_obtain_pair",
            ),

            path(
                "auth/token/refresh/",
                TokenRefreshView.as_view(),
                name="token_refresh",
            ),

            path(
                "auth/token/verify/",
                TokenVerifyView.as_view(),
                name="token_verify",
            ),

            # ----------------------------------------------------------
            # Companies
            # ----------------------------------------------------------
            path("companies/", include("companies.urls")),

            # ----------------------------------------------------------
            # Documents
            # ----------------------------------------------------------
            path("documents/", include("documents.urls")),

            # ----------------------------------------------------------
            # Billing
            # ----------------------------------------------------------
            path("billing/", include("billing.urls")),

            # ----------------------------------------------------------
            # AI Services
            # ----------------------------------------------------------
            path("ai/", include("ai.urls")),

            # ----------------------------------------------------------
            # Notifications (Future)
            # ----------------------------------------------------------
            # path("notifications/", include("notifications.urls")),

        ])
    ),
]

# ----------------------------------------------------------------------
# Static & Media Files (Development Only)
# ----------------------------------------------------------------------

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )

    urlpatterns += static(
        settings.STATIC_URL,
        document_root=settings.STATIC_ROOT,
    )