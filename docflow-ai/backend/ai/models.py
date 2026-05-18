"""AI app — Contract review, document generation via Claude API"""
import uuid
import json
import logging
from django.db import models
from django.conf import settings

logger = logging.getLogger(__name__)


class AiReview(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    document_name = models.CharField(max_length=255)
    document_file = models.FileField(upload_to="ai_reviews/", null=True, blank=True)
    extracted_text = models.TextField(blank=True)
    review_results = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    model_used = models.CharField(max_length=100, default="claude-sonnet-4-20250514")
    tokens_used = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ai_reviews"
        ordering = ["-created_at"]

    def __str__(self):
        return f"AI Review: {self.document_name}"


class AiGeneration(models.Model):
    class DocType(models.TextChoices):
        NDA = "nda", "Non-Disclosure Agreement"
        SERVICE = "service", "Service Agreement"
        FREELANCE = "freelance", "Freelance Contract"
        EMPLOYMENT = "employment", "Employment Contract"
        INVOICE = "invoice", "Invoice"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    input_fields = models.JSONField(default=dict)
    generated_content = models.TextField(blank=True)
    model_used = models.CharField(max_length=100)
    tokens_used = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_generations"
        ordering = ["-created_at"]
