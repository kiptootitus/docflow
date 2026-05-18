from django.urls import path
from .views import ContractReviewView, DocumentGenerationView, StreamGenerationView

urlpatterns = [
    path("review/", ContractReviewView.as_view(), name="ai-review"),
    path("generate/", DocumentGenerationView.as_view(), name="ai-generate"),
    path("generate/stream/", StreamGenerationView.as_view(), name="ai-generate-stream"),
]
