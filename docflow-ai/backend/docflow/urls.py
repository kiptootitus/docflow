"""DocFlow AI — Root URL Configuration"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # API v1
    path("api/v1/", include([
        # Auth
        path("auth/", include("apps.users.urls")),
        # Resources
        path("companies/", include("apps.companies.urls")),
        path("documents/", include("apps.documents.urls")),
        path("billing/", include("apps.billing.urls")),
        path("ai/", include("apps.ai.urls")),
    ])),

    # JWT
    path("api/v1/auth/token/", include("rest_framework_simplejwt.urls")),

    # Stripe webhooks
    path("webhooks/stripe/", include("djstripe.urls", namespace="djstripe")),

    # API Docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
