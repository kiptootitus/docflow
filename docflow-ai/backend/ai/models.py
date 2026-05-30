import uuid
import threading
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import UniqueConstraint, CheckConstraint, Q

# PostgreSQL Engine Specific Imports
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from pgvector.django import VectorField, HnswIndex
from encrypted_model_fields.fields import EncryptedTextField, EncryptedCharField


# =====================================================
# THREAD-SAFE GLOBAL TENANT CONTEXT STORAGE
# =====================================================

_tenant_context = threading.local()

def get_current_company_id():
    """Retrieves the globally scoped company ID injected by isolation middleware."""
    return getattr(_tenant_context, "company_id", None)

def set_current_company_id(company_id):
    """Sets the company ID bound to the active execution thread lifecycle."""
    _tenant_context.company_id = company_id

def clear_current_company_id():
    """Clears the thread-bound tenant configuration context."""
    if hasattr(_tenant_context, "company_id"):
        delattr(_tenant_context, "company_id")


# =====================================================
# SYSTEM STRUCTURAL DEFAULT FACTORIES
# =====================================================

def default_list():
    return []

def default_dict():
    return {}

def default_rbac_permissions():
    """Provides a safe structural fallback schema for corporate RBAC configurations."""
    return {
        "contracts": {"create": False, "read": True, "update": False, "delete": False},
        "ai_tools": {"execute_review": False, "execute_generation": False},
        "compliance": {"view_alerts": True, "resolve_alerts": False},
        "billing": {"view_quotas": False}
    }


# =====================================================
# ADVANCED BASE DATABASE MANAGERS
# =====================================================

class ActiveQuerySet(models.QuerySet):
    """Enforces foundational global filters across extended query chains."""
    def active(self):
        return self.filter(is_deleted=False)


class TenantQuerySet(ActiveQuerySet):
    """Automatically chains tenant-scoping conditions onto active query collections."""
    def filter_by_tenant(self):
        company_id = get_current_company_id()
        if company_id:
            return self.filter(company_id=company_id)
        return self


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """
    Default manager enforcing automatic tenant runtime security boundaries
    and soft-delete validation screens.
    """
    def get_queryset(self):
        return super().get_queryset().active().filter_by_tenant()

class BaseModelManager(models.Manager.from_queryset(ActiveQuerySet)):
    """Default system manager for global, non-tenant shared resources."""
    def get_queryset(self):
        return super().get_queryset().active()

# =====================================================
# CORE SYSTEM ABSTRACT BASE MODELS
# =====================================================

class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Global soft delete manager abstraction layers
    objects = BaseModelManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self):
        """Executes chronological localized state mutation markers."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

    def delete(self, using=None, keep_parents=False):
        """
        Intercepts hard-delete events and cascades soft-delete flags 
        down dependent foreign-key models to preserve data lineage.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

        # Reflective relational traversal loop tracking nested model trees
        for rel in self._meta.related_objects:
            if rel.on_delete == models.CASCADE:
                accessor_name = rel.get_accessor_name()
                related_manager = getattr(self, accessor_name, None)
                if related_manager and hasattr(related_manager, "all_objects"):
                    # Scope specifically to child nodes that aren't already flagged
                    for child_node in related_manager.all_objects.filter(is_deleted=False):
                        child_node.delete()


class TenantBaseModel(BaseModel):
    """
    Enforces automatic thread-level isolation restrictions across 
    multi-tenant enterprise models.
    """
    company = models.ForeignKey("Company", on_delete=models.CASCADE)

    # Scoped Multi-Tenant Isolation Managers
    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True


# =====================================================
# TENANT ORGANIZATIONS, ROLES & QUOTAS
# =====================================================

class Company(BaseModel):
    """
    Core Tenant model representing an enterprise account.
    """
    name = models.CharField(max_length=255)
    domain = models.CharField(max_length=255, unique=True)

    class Meta:
        verbose_name_plural = "Companies"
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["is_deleted"]),
        ]

    def __str__(self):
        return self.name
class TenantQuota(BaseModel):
    """
    Enforces subscription boundaries and usage guardrails per organization.
    """
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="quota")
    max_users = models.PositiveIntegerField(default=5)
    max_documents_storage_gb = models.DecimalField(max_digits=6, decimal_places=2, default=10.00)
    monthly_token_limit = models.PositiveIntegerField(default=5_000_000)
    current_monthly_tokens_used = models.PositiveIntegerField(default=0)
    reset_date = models.DateField(default=timezone.localdate)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(current_monthly_tokens_used__gte=0),
                name="chk_tokens_used_positive"
            )
        ]

class CompanyMembership(BaseModel):
    """
    Handles granular, parameter-driven RBAC mapping assignments.
    """
    class RoleChoices(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        LEGAL_REVIEWER = "legal_reviewer", "Legal Reviewer"
        MEMBER = "member", "Member"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="members")
    role = models.CharField(max_length=50, choices=RoleChoices.choices, default=RoleChoices.MEMBER)
    
    # Structural, deterministic schema fallback replacing generic empty dictionary initializations
    permissions = models.JSONField(default=default_rbac_permissions, blank=True)
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["user", "company"], name="unique_user_per_tenant")
        ]


# =====================================================
# AI MODELS & FALLBACK SUPPORT
# =====================================================

class AiModelTier(BaseModel):
    """
    Maintains a list of dynamic primary models and their fallback chains.
    """
    name = models.CharField(max_length=100, unique=True) 
    primary_model = models.CharField(max_length=100)      
    secondary_fallback = models.CharField(max_length=100, blank=True) 
    tertiary_fallback = models.CharField(max_length=100, blank=True)  
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


# =====================================================
# AI REVIEWS
# =====================================================

class AiReview(TenantBaseModel):

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    document_name = models.CharField(max_length=255)
    
    document_file = models.FileField(upload_to="ai/reviews/", blank=True, null=True)
    extracted_text = models.TextField(blank=True)
    review_results = models.JSONField(default=default_list)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    model_used = models.CharField(max_length=100)
    fallback_triggered = models.BooleanField(default=False)
    tokens_used = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "created_at"]),
            models.Index(fields=["company", "status"]),
            models.Index(fields=["company", "updated_at"]),
        ]


# =====================================================
# DOCUMENT GENERATION
# =====================================================

class PromptTemplate(TenantBaseModel):

    class TemplateType(models.TextChoices):
        NDA = "nda", "NDA"
        SERVICE = "service", "Service Agreement"
        FREELANCE = "freelance", "Freelance Agreement"
        EMPLOYMENT = "employment", "Employment Contract"
        INVOICE = "invoice", "Invoice"

    name = models.CharField(max_length=255)
    template_type = models.CharField(max_length=50, choices=TemplateType.choices)
    system_prompt = models.TextField()
    user_prompt = models.TextField()
    variables = models.JSONField(default=default_list)
    version = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["company", "name", "version"], name="unique_template_version_per_tenant")
        ]


class AiGeneration(TenantBaseModel):
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    template = models.ForeignKey(PromptTemplate, on_delete=models.SET_NULL, null=True)
    input_fields = models.JSONField(default=default_dict)
    generated_content = models.TextField()
    model_used = models.CharField(max_length=100)
    tokens_used = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["company", "created_at"]),
            models.Index(fields=["company", "updated_at"]),
        ]


# =====================================================
# CONTRACTS
# =====================================================
class Contract(TenantBaseModel):

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "Review"
        APPROVED = "approved", "Approved"
        SIGNED = "signed", "Signed"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        TERMINATED = "terminated", "Terminated"

    title = models.CharField(max_length=255)
    contract_number = models.CharField(max_length=100)
    generation = models.OneToOneField(AiGeneration, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    
    # Lifecycle Timestamps for Business Performance Metrics
    drafted_at = models.DateTimeField(null=True, blank=True)
    review_started_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    terminated_at = models.DateTimeField(null=True, blank=True)
    
    effective_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
    renewal_notice_days = models.PositiveIntegerField(default=30)
    
    tags = models.JSONField(default=default_list)
    search_vector = SearchVectorField(null=True, blank=True)
    
    encrypted_value = EncryptedCharField(max_length=255, null=True, blank=True) 
    metadata = models.JSONField(default=default_dict)

    class Meta:
        indexes = [
            GinIndex(fields=["tags"], name="contract_tags_gin"),
            GinIndex(fields=["search_vector"], name="contract_search_vector_gin"),
            models.Index(fields=["company", "created_at"]),
            models.Index(fields=["company", "status"]),
            models.Index(fields=["company", "updated_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "contract_number"], 
                name="unique_contract_number_per_company"
            ),
            models.CheckConstraint(
                condition=models.Q(expiry_date__gt=models.F("effective_date")) | models.Q(expiry_date__isnull=True),
                name="check_expiry_after_effective_date"
            )
        ]
class ContractParty(BaseModel):
    """
    Tracks external/internal corporate entities assigned to sign the transaction artifact.
    """
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="parties")
    name = models.CharField(max_length=255)
    email = models.EmailField()
    role = models.CharField(max_length=100) 
    signed = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["contract", "email"]),
        ]


class DocumentVersion(BaseModel):
    contract = models.ForeignKey(Contract, related_name="versions", on_delete=models.CASCADE)
    version_number = models.PositiveIntegerField()
    
    content = EncryptedTextField()
    searchable_content = models.TextField(blank=True, help_text="Sanitized indexable content block.")
    search_vector = SearchVectorField(null=True, blank=True)
    
    pdf_file = models.FileField(upload_to="contracts/pdf/", blank=True, null=True)
    docx_file = models.FileField(upload_to="contracts/docx/", blank=True, null=True)
    
    checksum = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        indexes = [
            GinIndex(fields=["search_vector"], name="doc_version_search_vector_gin"),
        ]
        constraints = [
            UniqueConstraint(fields=["contract", "version_number"], name="unique_version_per_contract")
        ]


# =====================================================
# DOCUMENT SHARING
# =====================================================

class DocumentShare(BaseModel):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="shares")
    shared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shared_documents")
    shared_with_email = models.EmailField()
    access_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False)
    allow_download = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["access_token"]),
        ]


# =====================================================
# CLAUSES & PGVECTOR SEMANTIC EMBEDDINGS
# =====================================================

class ClauseLibrary(TenantBaseModel):
    """
    Master template library tracking clause items alongside system revisions.
    """
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    jurisdiction = models.CharField(max_length=100)
    content = models.TextField()
    
    version = models.PositiveIntegerField(default=1)
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="historical_versions")
    
    search_vector = SearchVectorField(null=True, blank=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    risk_level = models.CharField(max_length=50)
    approved = models.BooleanField(default=True)

    class Meta:
        indexes = [
            GinIndex(fields=["search_vector"], name="clause_lib_search_vector_gin"),
            HnswIndex(
                name="clause_lib_vector_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"]  # <-- Fixed to plural array
            )
        ]


class ContractClause(BaseModel):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="clauses")
    clause = models.ForeignKey(ClauseLibrary, on_delete=models.SET_NULL, null=True)
    content = models.TextField()
    
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    ai_generated = models.BooleanField(default=False)

    class Meta:
        indexes = [
            HnswIndex(
                name="contract_clause_vector_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"]
            )
        ]


# =====================================================
# CENTRALIZED COMPLIANCE RISK SCORING LAYER
# =====================================================

class RiskScore(BaseModel):
    """
    Centralized analytics ledger that calculates legal risk exposures 
    across arbitrary models, standardizing structural calculations.
    """
    contract = models.OneToOneField(Contract, on_delete=models.CASCADE, related_name="risk_profile", null=True, blank=True)
    clause = models.OneToOneField(ContractClause, on_delete=models.CASCADE, related_name="risk_profile", null=True, blank=True)
    review = models.OneToOneField(AiReview, on_delete=models.CASCADE, related_name="risk_profile", null=True, blank=True)

    score = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )
    risk_breakdown = models.JSONField(default=default_dict, help_text="Structured scoring metrics matrix.")
    mitigation_strategy = models.TextField(blank=True)

    class Meta:
            constraints = [
                CheckConstraint(
                    condition=(
                        Q(contract__isnull=False) | 
                        Q(clause__isnull=False) | 
                        Q(review__isnull=False)
                    ),
                    name="chk_risk_score_polymorphic_target"
                )
            ]

# =====================================================
# APPROVALS, SIGNATURES & OBLIGATIONS
# =====================================================

class ApprovalWorkflow(BaseModel):
    contract = models.OneToOneField(Contract, on_delete=models.CASCADE, related_name="workflow")
    completed = models.BooleanField(default=False)


class ApprovalStep(BaseModel):
    workflow = models.ForeignKey(ApprovalWorkflow, related_name="steps", on_delete=models.CASCADE)
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    order = models.PositiveIntegerField()
    approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            UniqueConstraint(fields=["workflow", "order"], name="unique_step_order_per_workflow")
        ]


class ContractSignature(BaseModel):
    """
    Captures multi-point legal defensibility verification attributes.
    """
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="signatures")
    signer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    signature_hash = models.CharField(max_length=255)
    
    signed_document_checksum = models.CharField(max_length=255)
    signature_provider = models.CharField(max_length=100, default="internal") 
    user_agent = models.CharField(max_length=500, blank=True, null=True)
    geo_location = models.CharField(max_length=255, blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    signed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["contract", "signer", "signature_hash"], 
                name="unique_signature_verification_audit"
            )
        ]


class ContractObligation(BaseModel):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="obligations")
    title = models.CharField(max_length=255)
    due_date = models.DateField()
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)


# =====================================================
# COMPLIANCE ENGINE
# =====================================================

class ComplianceRule(TenantBaseModel):
    jurisdiction = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    rule_type = models.CharField(max_length=50)
    configuration = models.JSONField(default=default_dict)
    active = models.BooleanField(default=True)


class ComplianceAlert(TenantBaseModel):
    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE)
    rule = models.ForeignKey(ComplianceRule, on_delete=models.CASCADE)
    severity = models.CharField(max_length=20, choices=Severity.choices)
    description = models.TextField()
    resolved = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["company", "created_at"]),
            models.Index(fields=["company", "resolved"]),
            models.Index(fields=["company", "updated_at"]),
        ]


# =====================================================
# COMMUNICATIONS (COMMENTS & CHAT)
# =====================================================

class ContractComment(BaseModel):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    comment = models.TextField()
    resolved = models.BooleanField(default=False)


class AIConversation(BaseModel):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="conversations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)


class AIMessage(BaseModel):
    class Role(models.TextChoices):
        SYSTEM = "system", "System"
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(AIConversation, related_name="messages", on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=Role.choices) 
    content = models.TextField()
    tokens_used = models.PositiveIntegerField(default=0)


# =====================================================
# SYSTEM AUDITING & WEBHOOKS
# =====================================================

class WebhookSubscription(TenantBaseModel):
    target_url = models.URLField(max_length=500)
    secret_token = models.CharField(max_length=255) 
    is_active = models.BooleanField(default=True)
    subscribed_events = models.JSONField(default=default_list) 

    class Meta:
        indexes = [
            models.Index(fields=["company", "is_active"]),
        ]


class WebhookDelivery(BaseModel):
    subscription = models.ForeignKey(WebhookSubscription, on_delete=models.CASCADE, related_name="deliveries")
    event_name = models.CharField(max_length=100)
    response_code = models.IntegerField()
    success = models.BooleanField()
    response_body = models.TextField(blank=True)
    delivered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-delivered_at"]
        indexes = [
            models.Index(fields=["subscription", "success"]),
            models.Index(fields=["delivered_at"]),
        ]


class Notification(BaseModel):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        PUSH = "push", "Push Notifications"
        SMS = "sms", "SMS Shortcode"
        IN_APP = "in_app", "In-App Notification Center"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_notifications")
    title = models.CharField(max_length=255)
    message = models.TextField()
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.IN_APP)
    read = models.BooleanField(default=False)
    data = models.JSONField(default=default_dict)


class AuditLog(TenantBaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=255)
    entity_type = models.CharField(max_length=100)
    entity_id = models.UUIDField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=default_dict)

    class Meta:
        indexes = [
            models.Index(fields=["company", "created_at"]), # Re-indexed compound block for scalable analytical data slicing
            models.Index(fields=["entity_type", "entity_id"]),
        ]


class UsageMetric(TenantBaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    model_name = models.CharField(max_length=100)
    tokens_used = models.PositiveIntegerField()
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=6)

    class Meta:
        indexes = [
            models.Index(fields=["company", "created_at"]), # High-volume analytic compound index
        ]


# =====================================================
# SECURITY & ENTERPRISE INFRASTRUCTURE
# =====================================================

class AiPromptLog(TenantBaseModel):
    model_name = models.CharField(max_length=100)
    prompt = EncryptedTextField()
    response = EncryptedTextField()
    tokens_used = models.PositiveIntegerField()
    latency_ms = models.PositiveIntegerField()

    class Meta:
        indexes = [
            models.Index(fields=["company", "created_at"]),
        ]


class TaskExecution(BaseModel):
    task_name = models.CharField(max_length=255)
    celery_task_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=50) 
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["celery_task_id"]),
            models.Index(fields=["status"]),
        ]


class ApiKey(TenantBaseModel):
    name = models.CharField(max_length=255)
    key_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    prefix = models.CharField(max_length=16, unique=True)
    hashed_key = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["prefix", "is_active"]),
            models.Index(fields=["key_id"]),
        ]


class LoginAudit(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="login_audits")
    ip_address = models.GenericIPAddressField()
    user_agent = models.CharField(max_length=500)
    success = models.BooleanField(default=True)
    failure_reason = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]), # Added user-scoped historical performance lookup index
        ]


class DataRetentionPolicy(TenantBaseModel):
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="retention_policy")
    retention_period_months = models.PositiveIntegerField(default=84) 
    legal_hold = models.BooleanField(default=False)
    enforce_hard_delete = models.BooleanField(default=False)

class CreditUsage(TenantBaseModel):
    """
    Centralized financial ledger tracking granular organizational AI credit burns.
    Acts as the primary audit source for financial billing rollups.
    """
    class TransactionType(models.TextChoices):
        DEBIT = "debit", "Consumption Charge"
        CREDIT = "credit", "Quota Allocation Top-Up"
        REFUND = "refund", "Failed Processing Reversal"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=4, help_text="Credit value equivalent consumed.")
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    action_summary = models.CharField(max_length=255, help_text="E.g., Contract Review Extraction Run")
    reference_entity_type = models.CharField(max_length=100, blank=True, null=True)
    reference_entity_id = models.UUIDField(blank=True, null=True)
    meta_telemetry = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "transaction_type"]),
            models.Index(fields=["reference_entity_type", "reference_entity_id"]),
        ]

    def __str__(self):
        return f"{self.company.name} | {self.transaction_type} | {self.amount}"