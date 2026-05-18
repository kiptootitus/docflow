from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CompanyViewSet, ClientViewSet

router = DefaultRouter()
router.register("", CompanyViewSet, basename="company")
router.register("clients", ClientViewSet, basename="client")

urlpatterns = [path("", include(router.urls))]
