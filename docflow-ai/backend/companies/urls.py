from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CompanyViewSet, ClientViewSet

router = DefaultRouter()
# Explicitly separate the base routes
router.register("companies", CompanyViewSet, basename="company")
router.register("clients", ClientViewSet, basename="client")
urlpatterns = [path("", include(router.urls))]
