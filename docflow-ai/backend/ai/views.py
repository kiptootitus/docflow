"""AI Views Processing Controllers"""
import io
import json
import logging
from django.utils import timezone
from django.http import StreamingHttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated

from .models import AiReview
from .services import ai_provider

logger = logging.getLogger(__name__)


# =========================================================
# CONTRACT REVIEW VIEW
# =========================================================

class ContractReviewView(APIView):
    """
    Upload a PDF or image contract for AI review.

    POST /ai/review/
        multipart fields:
            file          (optional) — PDF or image
            company       (required) — company UUID
            instructions  (optional) — extra reviewer instructions

    Returns structured findings: risks, suggestions, compliance notes.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file = request.FILES.get("file")
        company_id = request.data.get("company")
        instructions = request.data.get("instructions", "").strip()

        if not company_id:
            return Response({"error": "Company parameter context is required."}, status=400)

        from apps.companies.models import Company
        try:
            company = Company.objects.get(id=company_id, owner=request.user)
        except Company.DoesNotExist:
            return Response({"error": "Company record mapping not found."}, status=404)

        review = AiReview.objects.create(
            company=company,
            created_by=request.user,
            document_name=file.name if file else "Manual Input Request",
            status=AiReview.Status.PROCESSING,
        )

        if file:
            review.document_file.save(file.name, file, save=True)

        text = ""
        if file:
            try:
                if file.name.lower().endswith(".pdf"):
                    import pdfplumber
                    file.seek(0)
                    with pdfplumber.open(io.BytesIO(file.read())) as pdf:
                        text = "\n".join(
                            (page.extract_text() or "") for page in pdf.pages
                        ).strip()
                else:
                    try:
                        from PIL import Image as PILImage
                        import pytesseract
                        file.seek(0)
                        img = PILImage.open(io.BytesIO(file.read()))
                        text = pytesseract.image_to_string(img).strip()
                    except ImportError:
                        text = "[OCR library detached] Raw extraction parameters could not be processed."

                review.extracted_text = text
                review.save(update_fields=["extracted_text"])
            except Exception as e:
                logger.exception("Text layout extraction layer processing broke.")
                review.status = AiReview.Status.FAILED
                review.error_message = str(e)
                review.save(update_fields=["status", "error_message"])
                return Response({"error": "File layout extraction parameters failed."}, status=500)
        else:
            text = instructions

        try:
            result = ai_provider.review_contract(text, instructions=instructions)

            review.review_results = result.get("findings", [])
            review.model_used = result.get("model")
            review.tokens_used = result.get("tokens")
            review.status = AiReview.Status.COMPLETED
            review.completed_at = timezone.now()
            review.save()

            return Response({
                "id": str(review.id),
                "document_name": review.document_name,
                "review_results": review.review_results,
                "extracted_company_name": result.get("extracted_company_name", ""),
                "extracted_company_address": result.get("extracted_company_address", ""),
                "extracted_company_city": result.get("extracted_company_city", ""),
                "extracted_company_location_number": result.get("extracted_company_location_number", ""),
                "extracted_salutation": result.get("extracted_salutation", "Mr."),
                "extracted_client_name": result.get("extracted_client_name", ""),
                "extracted_currency": result.get("extracted_currency", "KES"),
                "extracted_items": result.get("extracted_items", []),
                "status": review.status,
                "model_used": review.model_used,
                "tokens_used": review.tokens_used,
            }, status=201)

        except Exception as e:
            logger.exception("AI transactional data pipeline synthesis failed.")
            review.status = AiReview.Status.FAILED
            review.error_message = str(e)
            review.save(update_fields=["status", "error_message"])
            return Response({"error": "AI Extraction synthesis failure."}, status=500)


# =========================================================
# DOCUMENT GENERATION VIEW  (non-streaming)
# =========================================================

class DocumentGenerationView(APIView):
    """
    Generate a full document draft from a short wizard prompt.

    POST /ai/generate/
        JSON body:
            document_type  (required) — "nda" | "service" | "freelance" | "employment" | "invoice" | "quotation"
            company        (required) — company UUID
            context        (required) — dict of wizard field values
            instructions   (optional) — extra freeform guidance

    Returns the generated content as a string plus metadata.
    """
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        document_type = request.data.get("document_type", "").strip()
        company_id = request.data.get("company")
        context = request.data.get("context", {})
        instructions = request.data.get("instructions", "").strip()

        # ── Validation ──────────────────────────────────────
        if not document_type:
            return Response({"error": "document_type is required."}, status=400)

        SUPPORTED_TYPES = {"nda", "service", "freelance", "employment", "invoice", "quotation", "custom"}
        if document_type not in SUPPORTED_TYPES:
            return Response(
                {"error": f"Unsupported document_type '{document_type}'. Choose from: {sorted(SUPPORTED_TYPES)}."},
                status=400,
            )

        if not company_id:
            return Response({"error": "company is required."}, status=400)

        if not isinstance(context, dict):
            return Response({"error": "context must be a JSON object."}, status=400)

        from apps.companies.models import Company
        try:
            company = Company.objects.get(id=company_id, owner=request.user)
        except Company.DoesNotExist:
            return Response({"error": "Company not found."}, status=404)

        # ── Log generation attempt ───────────────────────────
        review = AiReview.objects.create(
            company=company,
            created_by=request.user,
            document_name=f"Generated {document_type.upper()}",
            status=AiReview.Status.PROCESSING,
        )

        try:
            result = ai_provider.generate_document(
                document_type=document_type,
                context=context,
                instructions=instructions,
            )

            review.review_results = [{"type": "generation", "content": result.get("content", "")}]
            review.model_used = result.get("model")
            review.tokens_used = result.get("tokens")
            review.status = AiReview.Status.COMPLETED
            review.completed_at = timezone.now()
            review.save()

            return Response({
                "id": str(review.id),
                "document_type": document_type,
                "content": result.get("content", ""),
                "title": result.get("title", ""),
                "model_used": review.model_used,
                "tokens_used": review.tokens_used,
                "status": review.status,
            }, status=201)

        except Exception as e:
            logger.exception("AI document generation failed.")
            review.status = AiReview.Status.FAILED
            review.error_message = str(e)
            review.save(update_fields=["status", "error_message"])
            return Response({"error": "Document generation failed."}, status=500)


# =========================================================
# STREAM GENERATION VIEW  (Server-Sent Events)
# =========================================================

class StreamGenerationView(APIView):
    """
    Stream a document draft token-by-token via Server-Sent Events.

    GET /ai/generate/stream/?document_type=nda&company=<uuid>&context=<json>

    SSE event format:
        data: {"token": "..."}        ← content chunk
        data: {"done": true, ...}     ← final metadata event

    The frontend should open an EventSource or fetch with ReadableStream
    and accumulate tokens as they arrive for the live-typing effect.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        document_type = request.query_params.get("document_type", "").strip()
        company_id = request.query_params.get("company")
        raw_context = request.query_params.get("context", "{}")
        instructions = request.query_params.get("instructions", "").strip()

        # ── Validation ──────────────────────────────────────
        if not document_type:
            return Response({"error": "document_type is required."}, status=400)

        if not company_id:
            return Response({"error": "company is required."}, status=400)

        try:
            context = json.loads(raw_context) if isinstance(raw_context, str) else raw_context
        except json.JSONDecodeError:
            return Response({"error": "context must be valid JSON."}, status=400)

        from apps.companies.models import Company
        try:
            company = Company.objects.get(id=company_id, owner=request.user)
        except Company.DoesNotExist:
            return Response({"error": "Company not found."}, status=404)

        # ── Log before streaming starts ──────────────────────
        review = AiReview.objects.create(
            company=company,
            created_by=request.user,
            document_name=f"Streamed {document_type.upper()}",
            status=AiReview.Status.PROCESSING,
        )

        def event_stream():
            """Generator that yields SSE-formatted chunks."""
            full_content = []
            try:
                for chunk in ai_provider.stream_document(
                    document_type=document_type,
                    context=context,
                    instructions=instructions,
                ):
                    if chunk.get("token"):
                        full_content.append(chunk["token"])
                        yield f"data: {json.dumps({'token': chunk['token']})}\n\n"

                # Persist completed result
                joined = "".join(full_content)
                review.review_results = [{"type": "generation", "content": joined}]
                review.model_used = chunk.get("model", "")
                review.tokens_used = chunk.get("tokens", 0)
                review.status = AiReview.Status.COMPLETED
                review.completed_at = timezone.now()
                review.save()

                yield f"data: {json.dumps({'done': True, 'id': str(review.id), 'model_used': review.model_used, 'tokens_used': review.tokens_used})}\n\n"

            except Exception as e:
                logger.exception("SSE stream generation failed.")
                review.status = AiReview.Status.FAILED
                review.error_message = str(e)
                review.save(update_fields=["status", "error_message"])
                yield f"data: {json.dumps({'error': 'Stream generation failed.'})}\n\n"

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"  # Disable Nginx buffering for SSE
        return response