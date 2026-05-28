"""
DocFlow AI — notifications/urls.py

URL configuration for the notifications app.

Mount in your project urls.py as:
    path("api/v1/notifications/", include("notifications.urls")),
"""

from django.urls import path

from .views import (
    NotificationListView,
    NotificationDetailView,
    MarkReadView,
    MarkAllReadView,
    DeleteNotificationView,
    UnreadCountView,
    PreferenceListView,
    PreferenceUpdateView,
    PushTokenListView,
    PushTokenCreateView,
    PushTokenUpdateView,
    PushTokenDeleteView,
)

urlpatterns = [
    # ── Notifications ──────────────────────────────────────────────────────
    path("",                               NotificationListView.as_view(),   name="notification-list"),
    path("unread-count/",                  UnreadCountView.as_view(),         name="notification-unread-count"),
    path("read-all/",                      MarkAllReadView.as_view(),         name="notification-read-all"),
    path("<uuid:pk>/",                     NotificationDetailView.as_view(),  name="notification-detail"),
    path("<uuid:pk>/read/",                MarkReadView.as_view(),            name="notification-mark-read"),
    path("<uuid:pk>/delete/",              DeleteNotificationView.as_view(),  name="notification-delete"),

    # ── Preferences ────────────────────────────────────────────────────────
    path("preferences/",                   PreferenceListView.as_view(),      name="notification-preferences"),
    path("preferences/<str:category>/",    PreferenceUpdateView.as_view(),    name="notification-preference-update"),

    # ── Push Tokens ────────────────────────────────────────────────────────
    path("push-tokens/",                   PushTokenListView.as_view(),       name="push-token-list"),
    path("push-tokens/register/",          PushTokenCreateView.as_view(),     name="push-token-create"),
    path("push-tokens/<uuid:pk>/",         PushTokenUpdateView.as_view(),     name="push-token-update"),
    path("push-tokens/<uuid:pk>/delete/",  PushTokenDeleteView.as_view(),     name="push-token-delete"),
]