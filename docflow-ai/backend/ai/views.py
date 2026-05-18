"""AI views — contract review, document generation, SSE streaming"""
import json
import logging
from django.utils import timezone
from django.http import StreamingHttpResponse
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import AiReview, AiGeneration
from .services import ai_provider

logger = logging.getLogger(__name__)


class ContractReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = AiReview
        fields = ["id", "document_name", "review_results", "status", "model_used",
                  "tokens_used", "created_at", "completed_at"]


class ContractReviewView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file uploaded."}, status=400)

        company_id = request.data.get("company")
        if not company_id:
            return Response({"error": "company is required."}, status=400)

        from apps.companies.models import Company
        try:
            company = Company.objects.get(id=company_id, owner=request.user)
        except Company.DoesNotExist:
            return Response({"error": "Company not found."}, status=404)

        review = AiReview.objects.create(
            company=company,
            created_by=request.user,
            document_name=file.name,
            status=AiReview.Status.PROCESSING,
        )
        review.document_file.save(file.name, file, save=True)

        # Extract text from PDF
        try:
            import pdfplumber
            import io
            file.seek(0)
            with pdfplumber.open(io.BytesIO(file.read())) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            review.extracted_text = text
            review.save(update_fields=["extracted_text"])
        except Exception as e:
            review.status = AiReview.Status.FAILED
            review.error_message = str(e)
            review.save(update_fields=["status", "error_message"])
            return Response({"error": f"Text extraction failed: {e}"}, status=500)

        # Run AI review
        try:
            result = ai_provider.review_contract(text)
            review.review_results = result["findings"]
            review.model_used = result["model"]
            review.tokens_used = result["tokens"]
            review.status = AiReview.Status.COMPLETED
            review.completed_at = timezone.now()
            review.save()
            return Response(ContractReviewSerializer(review).data, status=201)
        except Exception as e:
            review.status = AiReview.Status.FAILED
            review.error_message = str(e)
            review.save(update_fields=["status", "error_message"])
            return Response({"error": "AI review failed."}, status=500)

    def get(self, request):
        company_id = request.query_params.get("company")
        reviews = AiReview.objects.filter(company__owner=request.user)
        if company_id:
            reviews = reviews.filter(company_id=company_id)
        return Response(ContractReviewSerializer(reviews, many=True).data)


class DocumentGenerationView(APIView):
    def post(self, request):
        doc_type = request.data.get("doc_type")
        fields = request.data.get("fields", {})
        company_id = request.data.get("company")

        if not all([doc_type, fields, company_id]):
            return Response({"error": "doc_type, fields, and company are required."}, status=400)

        from apps.companies.models import Company
        try:
            company = Company.objects.get(id=company_id, owner=request.user)
        except Company.DoesNotExist:
            return Response({"error": "Company not found."}, status=404)

        try:
            result = ai_provider.generate_document(doc_type, fields)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)
        except Exception as e:
            return Response({"error": "AI generation failed."}, status=500)

        generation = AiGeneration.objects.create(
            company=company,
            created_by=request.user,
            doc_type=doc_type,
            input_fields=fields,
            generated_content=result["content"],
            model_used=result["model"],
            tokens_used=result["tokens"],
        )

        return Response({
            "id": str(generation.id),
            "content": generation.generated_content,
            "model": generation.model_used,
            "tokens_used": generation.tokens_used,
        }, status=201)


def generate_stream(prompt: str, company, user):
    """SSE streaming generator for real-time AI responses."""
    import anthropic
    from django.conf import settings

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    with client.messages.stream(
        model=settings.AI_MODEL_PRIMARY,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            data = json.dumps({"type": "chunk", "content": text})
            yield f"data: {data}\n\n"
    yield "data: {\"type\": \"done\"}\n\n"


class StreamGenerationView(APIView):
    def post(self, request):
        doc_type = request.data.get("doc_type")
        fields = request.data.get("fields", {})
        company_id = request.data.get("company")

        from apps.companies.models import Company
        try:
            company = Company.objects.get(id=company_id, owner=request.user)
        except Company.DoesNotExist:
            return Response({"error": "Company not found."}, status=404)

        from .services import DOCUMENT_GENERATION_PROMPTS
        template = DOCUMENT_GENERATION_PROMPTS.get(doc_type, "Generate a {doc_type} document.")
        try:
            prompt = template.format(**fields)
        except (KeyError, TypeError):
            prompt = f"Generate a professional {doc_type} document."

        response = StreamingHttpResponse(
            generate_stream(prompt, company, request.user),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
