from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CompanyViewSet, ContractViewSet, ClauseLibraryViewSet, AiReviewViewSet,
    PromptTemplateViewSet, AiGenerationViewSet, ContractSignatureViewSet,
    ComplianceAlertViewSet,
    AiStreamingViewSet  # 1. ADD THIS IMPORT
)

# Core Enterprise Router instantiation config
router = DefaultRouter()

router.register(r'companies', CompanyViewSet, basename='company')
router.register(r'contracts', ContractViewSet, basename='contract')
router.register(r'clause-library', ClauseLibraryViewSet, basename='clause-library')
router.register(r'ai-reviews', AiReviewViewSet, basename='ai-review')
router.register(r'prompt-templates', PromptTemplateViewSet, basename='prompt-template')
router.register(r'ai-generations', AiGenerationViewSet, basename='ai-generation')
router.register(r'signatures', ContractSignatureViewSet, basename='signature')
router.register(r'compliance-alerts', ComplianceAlertViewSet, basename='compliance-alert')

# 2. REGISTER THE STREAMING VIEWSET
# URL path prefix will be 'ai-streams', name prefix will be 'ai-stream'
router.register(r'ai-streams', AiStreamingViewSet, basename='ai-stream')

urlpatterns = [
    path('api/v1/', include(router.urls)),
]