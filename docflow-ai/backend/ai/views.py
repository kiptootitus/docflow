"""
AI Views:
- Contract review (PDF analysis)
- Document generation
- SSE streaming generation
- Structured quote generation (LangChain + Anthropic)
"""

import json
import logging
import io

from django.utils import timezone
from django.http import StreamingHttpResponse

from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from .models import AiReview, AiGeneration
from .services import ai_provider

logger = logging.getLogger(__name__)

# =========================
# SERIALIZER
# =========================

class ContractReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = AiReview
        fields = [
            "id",
            "document_name",
            "review_results",
            "status",
            "model_used",
            "tokens_used",
            "created_at",
            "completed_at",
        ]


# =========================
# CONTRACT REVIEW VIEW
# =========================

class ContractReviewView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file = request.FILES.get("file")
        company_id = request.data.get("company")

        if not file:
            return Response({"error": "No file uploaded."}, status=400)

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

        # -------------------------
        # Extract PDF text safely
        # -------------------------
        try:
            import pdfplumber

            file.seek(0)
            with pdfplumber.open(io.BytesIO(file.read())) as pdf:
                text = "\n".join(
                    (page.extract_text() or "") for page in pdf.pages
                ).strip()

            review.extracted_text = text
            review.save(update_fields=["extracted_text"])

        except Exception as e:
            logger.exception("PDF extraction failed")

            review.status = AiReview.Status.FAILED
            review.error_message = str(e)
            review.save(update_fields=["status", "error_message"])

            return Response({"error": "Text extraction failed."}, status=500)

        # -------------------------
        # AI REVIEW
        # -------------------------
        try:
            result = ai_provider.review_contract(text)

            review.review_results = result.get("findings", {})
            review.model_used = result.get("model")
            review.tokens_used = result.get("tokens")
            review.status = AiReview.Status.COMPLETED
            review.completed_at = timezone.now()
            review.save()

            return Response(ContractReviewSerializer(review).data, status=201)

        except Exception as e:
            logger.exception("AI review failed")

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


# =========================
# DOCUMENT GENERATION
# =========================

class DocumentGenerationView(APIView):

    def post(self, request):
        doc_type = request.data.get("doc_type")
        fields = request.data.get("fields", {})
        company_id = request.data.get("company")

        if not doc_type or not company_id:
            return Response(
                {"error": "doc_type and company are required."},
                status=400,
            )

        from apps.companies.models import Company

        try:
            company = Company.objects.get(id=company_id, owner=request.user)
        except Company.DoesNotExist:
            return Response({"error": "Company not found."}, status=404)

        try:
            result = ai_provider.generate_document(doc_type, fields)

        except ValueError as e:
            return Response({"error": str(e)}, status=400)

        except Exception:
            logger.exception("AI generation failed")
            return Response({"error": "AI generation failed."}, status=500)

        generation = AiGeneration.objects.create(
            company=company,
            created_by=request.user,
            doc_type=doc_type,
            input_fields=fields,
            generated_content=result.get("content"),
            model_used=result.get("model"),
            tokens_used=result.get("tokens"),
        )

        return Response(
            {
                "id": str(generation.id),
                "content": generation.generated_content,
                "model": generation.model_used,
                "tokens_used": generation.tokens_used,
            },
            status=201,
        )


# =========================
# SSE STREAMING GENERATION
# =========================

def generate_stream(prompt: str):
    """
    SSE streaming generator
    """
    import anthropic
    from django.conf import settings

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        with client.messages.stream(
            model=settings.AI_MODEL_PRIMARY,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:

            for chunk in stream.text_stream:
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

        # proper JSON close event
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        logger.exception("Streaming failed")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


class StreamGenerationView(APIView):

    def post(self, request):
        doc_type = request.data.get("doc_type")
        fields = request.data.get("fields", {})
        company_id = request.data.get("company")

        if not company_id:
            return Response({"error": "company is required."}, status=400)

        from apps.companies.models import Company
        from .services import DOCUMENT_GENERATION_PROMPTS

        try:
            company = Company.objects.get(id=company_id, owner=request.user)
        except Company.DoesNotExist:
            return Response({"error": "Company not found."}, status=404)

        template = DOCUMENT_GENERATION_PROMPTS.get(
            doc_type,
            "Generate a professional {doc_type} document.",
        )

        try:
            prompt = template.format(**fields)
        except Exception:
            prompt = f"Generate a professional {doc_type} document."

        response = StreamingHttpResponse(
            generate_stream(prompt),
            content_type="text/event-stream",
        )

        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


# =========================
# LANGCHAIN QUOTE GENERATOR
# =========================

from rest_framework.permissions import IsAuthenticated
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing import List


class LineItem(BaseModel):
    description: str
    quantity: int
    unit_price: float
    amount: float


class QuoteOutput(BaseModel):
    title: str
    line_items: List[LineItem]
    notes: str
    validity_days: int = 30


SYSTEM_PROMPT = """
You are a professional business document assistant.
Return ONLY valid JSON matching schema.
No markdown, no explanation.
"""

USER_PROMPT = """
Generate quotation:

Client: {client_name}
Project: {project_type}
Budget: {budget} {currency}
Timeline: {timeline}
Scope: {scope}
"""


class GenerateQuoteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data

        if not data.get("project_type") or not data.get("currency"):
            return Response(
                {"error": "project_type and currency required."},
                status=400,
            )

        try:
            llm = ChatAnthropic(
                model="claude-sonnet-4-20250514",
                temperature=0.4,
                max_tokens=2000,
            )

            prompt = ChatPromptTemplate.from_messages([
                ("system", SYSTEM_PROMPT),
                ("human", USER_PROMPT),
            ])

            parser = JsonOutputParser(pydantic_object=QuoteOutput)

            chain = prompt | llm | parser

            result = chain.invoke({
                "client_name": data.get("client_name", "Client"),
                "project_type": data.get("project_type"),
                "budget": data.get("budget", "N/A"),
                "currency": data.get("currency"),
                "timeline": data.get("timeline", "TBD"),
                "scope": data.get("scope", "General work"),
            })

            # fix amounts
            for item in result.get("line_items", []):
                item["amount"] = round(
                    item["quantity"] * item["unit_price"], 2
                )

            return Response(result, status=200)

        except Exception as e:
            logger.exception("Quote generation failed")
            return Response(
                {"error": "AI generation failed", "detail": str(e)},
                status=500,
            )