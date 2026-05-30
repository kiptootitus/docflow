from django.contrib import admin
from .models import AiReview, AiGeneration


@admin.register(AiReview)
class AiReviewAdmin(admin.ModelAdmin):
    list_display = ["document_name", "company", "status", "model_used", "tokens_used", "created_at"]
    list_filter = ["status", "model_used"]
    readonly_fields = ["extracted_text", "review_results", "tokens_used", "completed_at"]


@admin.register(AiGeneration)
class AiGenerationAdmin(admin.ModelAdmin):
    list_display = ['model_used', 'created_by', 'tokens_used', 'created_at']
    list_filter = ['model_used', 'company']