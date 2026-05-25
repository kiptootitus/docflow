"""AI Views Processing Controllers"""
import io
import logging
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated

from .models import AiReview
from .services import ai_provider

logger = logging.getLogger(__name__)

class ContractReviewView(APIView):
    """Processes uploaded images or documents to populate transaction layers."""
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

        # Basic instantiation log tracker
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
                if file.name.lower().endswith('.pdf'):
                    import pdfplumber
                    file.seek(0)
                    with pdfplumber.open(io.BytesIO(file.read())) as pdf:
                        text = "\n".join((page.extract_text() or "") for page in pdf.pages).strip()
                else:
                    try:
                        from PIL import Image as PILImage
                        import pytesseract
                        file.seek(0)
                        img = PILImage.open(io.BytesIO(file.read()))
                        text = pytesseract.image_to_string(img).strip()
                    except ImportError:
                        text = f"[OCR library detached] Raw extraction parameters could not be processed."

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
                "tokens_used": review.tokens_used
            }, status=201)

        except Exception as e:
            logger.exception("AI transactional data pipeline synthesis failed.")
            review.status = AiReview.Status.FAILED
            review.error_message = str(e)
            review.save(update_fields=["status", "error_message"])
            return Response({"error": "AI Extraction synthesis failure."}, status=500)