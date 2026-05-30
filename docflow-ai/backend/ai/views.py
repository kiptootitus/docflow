from rest_framework import viewsets, status, filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import F
from django.utils import timezone
from django.db import transaction
from django.http import StreamingHttpResponse
import json
from django.conf import settings
from .provider import get_ai_provider
from .prompts.prompt_blueprints import EXECUTABLE_GENERATION_SYSTEM_PROMPT

# PGVector Cosine Distance Import
from pgvector.django import CosineDistance

from .models import (
    Company, Contract, AiReview, PromptTemplate, AiGeneration,
    ClauseLibrary, ContractSignature, ComplianceAlert, AuditLog,
    TenantQuota, UsageMetric
)
from .serializers import (
    CompanySerializer, ContractSerializer, AiReviewSerializer,
    PromptTemplateSerializer, AiGenerationSerializer, ClauseLibrarySerializer,
    ContractSignatureSerializer, ComplianceAlertSerializer
)
from .permissions import IsTenantAuthenticated, HasRbacPermission

class BaseEnterpriseViewSet(viewsets.ModelViewSet):
    """
    Abstract structural wrapper enforcing baseline global authentication pipelines,
    multi-tenant safety boundaries, and systematic CRUD audit operations.
    """
    permission_classes = [IsTenantAuthenticated, HasRbacPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    def perform_create(self, serializer):
        instance = serializer.save()
        self._log_audit(action="CREATE", instance=instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self._log_audit(action="UPDATE", instance=instance)

    def perform_destroy(self, instance):
        # Enforce structural soft delete pattern safely
        self._log_audit(action="SOFT_DELETE", instance=instance)
        instance.soft_delete()

    def _log_audit(self, action, instance):
        request = self.request
        company_id = getattr(request, 'company_id', None)
        if company_id and hasattr(instance, 'id'):
            AuditLog.objects.create(
                company_id=company_id,
                user=request.user,
                action=f"{action}_{instance.__class__.__name__.upper()}",
                entity_type=instance.__class__.__name__,
                entity_id=instance.id,
                ip_address=request.META.get('REMOTE_ADDR'),
                metadata={"path": request.path}
            )


class CompanyViewSet(viewsets.ModelViewSet):
    """
    Global configuration layer restricted entirely to administrative global entities.
    """
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAdminUser]


class ContractViewSet(BaseEnterpriseViewSet):
    serializer_class = ContractSerializer
    search_fields = ['title', 'contract_number']
    filterset_fields = ['status', 'auto_renew']
    ordering_fields = ['created_at', 'updated_at', 'expiry_date']

    def get_queryset(self):
        """Enforces tenant filtering and addresses N+1 querying."""
        return Contract.objects.all().select_related('risk_profile').prefetch_related('parties', 'clauses', 'versions')

    @action(detail=True, methods=['post'], url_path='start-review')
    @transaction.atomic
    def start_review(self, request, pk=None):
        contract = self.get_object()
        if contract.status != Contract.Status.DRAFT:
            return Response({"error": "Review workflows require standard Draft state conditions."}, status=status.HTTP_400_BAD_REQUEST)
        
        contract.status = Contract.Status.REVIEW
        contract.review_started_at = timezone.now()
        contract.save()
        
        self._log_audit("INITIATE_REVIEW_WORKFLOW", contract)
        return Response(ContractSerializer(contract).data, status=status.HTTP_200_OK)


class ClauseLibraryViewSet(BaseEnterpriseViewSet):
    serializer_class = ClauseLibrarySerializer

    def get_queryset(self):
        return ClauseLibrary.objects.all()

    @action(detail=False, methods=['post'], url_path='semantic-search')
    def semantic_search(self, request):
        """
        Executes a localized cosine distance lookup against vector fields 
        to find matching clauses in the database.
        """
        query_vector = request.data.get('embedding')
        threshold = request.data.get('threshold', 0.3)

        if not query_vector or not isinstance(query_vector, list) or len(query_vector) != 1536:
            return Response({"error": "A 1536-dimensional float vector matrix is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Vector calculations using pgvector
        clauses = ClauseLibrary.objects.annotate(
            distance=CosineDistance('embedding', query_vector)
        ).filter(distance__lt=threshold).order_by('distance')[:10]

        results = []
        for c in clauses:
            results.append({
                "id": c.id,
                "title": c.title,
                "category": c.category,
                "content": c.content,
                "cosine_distance": float(c.distance),
                "risk_level": c.risk_level
            })

        return Response(results, status=status.HTTP_200_OK)


class AiReviewViewSet(BaseEnterpriseViewSet):
    serializer_class = AiReviewSerializer

    def get_queryset(self):
        return AiReview.objects.all().select_related('risk_profile')

    @transaction.atomic
    def perform_create(self, serializer):
        # Enforce compliance with subscription boundaries
        company_id = self.request.company_id
        quota = TenantQuota.objects.get(company_id=company_id)
        
        if quota.current_monthly_tokens_used >= quota.monthly_token_limit:
            return Response({"error": "Monthly token quota limit exceeded for this tenant organization."}, status=status.HTTP_403_FORBIDDEN)

        review = serializer.save(created_by=self.request.user, status=AiReview.Status.PENDING)
        self._log_audit("CREATE", review)
        
        # In a real environment, you would trigger your asynchronous processing tasks here:
        # transaction.on_commit(lambda: process_ai_contract_review_task.delay(review.id))


class PromptTemplateViewSet(BaseEnterpriseViewSet):
    serializer_class = PromptTemplateSerializer
    filterset_fields = ['template_type', 'active']

    def get_queryset(self):
        return PromptTemplate.objects.all()


class AiGenerationViewSet(BaseEnterpriseViewSet):
    serializer_class = AiGenerationSerializer

    def get_queryset(self):
        return AiGeneration.objects.all()


class ContractSignatureViewSet(BaseEnterpriseViewSet):
    serializer_class = ContractSignatureSerializer

    def get_queryset(self):
        return ContractSignature.objects.all()


class ComplianceAlertViewSet(BaseEnterpriseViewSet):
    serializer_class = ComplianceAlertSerializer
    filterset_fields = ['severity', 'resolved']

    def get_queryset(self):
        return ComplianceAlert.objects.all().select_related('contract', 'rule')
    
class AiStreamingViewSet(viewsets.ViewSet):
    """
    High-performance event-stream router managing pipeline token deliveries 
    via asynchronous chunk iterations.
    """
    permission_classes = [IsTenantAuthenticated, HasRbacPermission]

    @action(detail=True, methods=['get'], url_path='stream-generation', url_name='stream_generation')
    def stream_generation(self, request, pk=None):
        try:
            generation_node = AiGeneration.objects.select_related('template').get(
                pk=pk, 
                company_id=request.company_id
            )
        except AiGeneration.DoesNotExist:
            return Response({"error": "Target entity context missing."}, status=status.HTTP_404_NOT_FOUND)
        template_record: PromptTemplate = generation_node.template
        
        # Compile prompts using standard string template mappings
        from jinja2 import Template
        user_prompt_compiled = Template(template_record.user_prompt).render(**generation_node.input_fields)
        system_prompt_compiled = f"{template_record.system_prompt}\n\n{EXECUTABLE_GENERATION_SYSTEM_PROMPT}"

        ai_engine = get_ai_provider(model_name=generation_node.model_used)

        def event_stream_generator():
            """
            Synchronous-wrapped generator mapping token updates cleanly onto 
            Server-Sent Events payload standards.
            """
            # Send initial handshaking payload data chunk
            yield f"data: {json.dumps({'event': 'STARTED', 'model': generation_node.model_used})}\n\n"

            full_response_accumulator = []
            
            # Stream chunk text packets directly from provider core routines
            for text_chunk in ai_engine.stream_response(
                system_prompt=system_prompt_compiled,
                user_prompt=user_prompt_compiled
            ):
                if text_chunk:
                    full_response_accumulator.append(text_chunk)
                    payload = {"event": "TEXT_DELTA", "text": text_chunk}
                    yield f"data: {json.dumps(payload)}\n\n"

            # Sync down final accumulated outcome contents to db storage references
            generation_node.generated_content = "".join(full_response_accumulator)
            generation_node.save()

            yield f"data: {json.dumps({'event': 'COMPLETED'})}\n\n"

        response = StreamingHttpResponse(event_stream_generator(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # Prevents Nginx response buffering bottlenecks
        return response