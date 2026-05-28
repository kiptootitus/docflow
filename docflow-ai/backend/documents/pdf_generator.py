"""
DocFlow AI — documents/pdf_generator.py

WeasyPrint-based PDF generation for Invoice, Quotation, and Contract.

Usage:
    from documents.pdf_generator import generate_pdf
    pdf_bytes = generate_pdf("invoice", invoice_instance)

The generator:
  1. Loads the correct HTML template (templates/documents/<type>.html).
  2. Injects the document + company branding context.
  3. Renders HTML → PDF via WeasyPrint.
  4. Uploads the PDF to S3 via django-storages.
  5. Updates the model's pdf_file field.
  6. Returns the S3 key and a presigned URL.

Dependencies: weasyprint, django-storages, boto3
"""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Union

from django.conf import settings
from django.core.files.base import ContentFile
from django.template.loader import render_to_string

if TYPE_CHECKING:
    from .models import Contract, Invoice, Quotation

    DocumentInstance = Union[Invoice, Quotation, Contract]

logger = logging.getLogger(__name__)

# Map document type strings → (model import path, template name)
_DOC_CONFIG: dict[str, tuple[str, str]] = {
    "invoice":   ("documents.models.Invoice",   "documents/invoice.html"),
    "quotation": ("documents.models.Quotation", "documents/quotation.html"),
    "contract":  ("documents.models.Contract",  "documents/contract.html"),
}


def _import_model(dotted: str):
    module_path, class_name = dotted.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _build_context(doc: "DocumentInstance") -> dict:
    """Build the template context dict for a document."""
    company = doc.company

    branding = getattr(company, "branding", None)
    vat      = getattr(company, "vat_config", None)

    logo_url = None
    if company.logo:
        try:
            logo_url = company.logo.url
        except Exception:
            pass

    stamp_url = None
    sig_url   = None
    if branding:
        if getattr(branding, "stamp", None):
            try:
                stamp_url = branding.stamp.url
            except Exception:
                pass
        if getattr(branding, "signature", None):
            try:
                sig_url = branding.signature.url
            except Exception:
                pass

    # Line items (not applicable to Contract)
    line_items = list(getattr(doc, "line_items", type("_", (), {"all": lambda self: []})()).all()) if hasattr(doc, "line_items") else []

    return {
        "doc":       doc,
        "company":   company,
        "branding":  branding,
        "vat":       vat,
        "logo_url":  logo_url,
        "stamp_url": stamp_url,
        "sig_url":   sig_url,
        "line_items": line_items,
        "STATIC_URL": getattr(settings, "STATIC_URL", "/static/"),
    }


def render_html(doc_type: str, doc: "DocumentInstance") -> str:
    """Render the document HTML string — useful for live preview endpoint."""
    if doc_type not in _DOC_CONFIG:
        raise ValueError(f"Unknown document type: {doc_type!r}")

    _, template_name = _DOC_CONFIG[doc_type]
    context = _build_context(doc)
    return render_to_string(template_name, context)


def generate_pdf(doc_type: str, doc: "DocumentInstance") -> bytes:
    """
    Render the document as PDF bytes.
    Saves the result to the model's pdf_file field and returns raw bytes.
    """
    try:
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
    except ImportError as exc:
        raise ImportError("WeasyPrint is required: pip install weasyprint") from exc

    html_string = render_html(doc_type, doc)

    font_config = FontConfiguration()

    # Base CSS injected programmatically (override per branding)
    branding = getattr(doc.company, "branding", None)
    primary_color = getattr(branding, "primary_color", "#1A56DB") if branding else "#1A56DB"
    font_family   = getattr(branding, "font_family",   "Inter")   if branding else "Inter"
    font_size     = getattr(branding, "font_size_body", 10)        if branding else 10

    extra_css = CSS(string=f"""
        @import url('https://fonts.googleapis.com/css2?family={font_family.replace(' ', '+')}:wght@400;600;700&display=swap');
        :root {{
            --primary: {primary_color};
            --font-body: '{font_family}', sans-serif;
            --font-size: {font_size}pt;
        }}
        body {{ font-family: var(--font-body); font-size: var(--font-size); }}
    """, font_config=font_config)

    pdf_bytes: bytes = (
        HTML(string=html_string, base_url=settings.BASE_DIR if hasattr(settings, "BASE_DIR") else ".")
        .write_pdf(stylesheets=[extra_css], font_config=font_config)
    )

    # Persist to storage
    filename = f"{doc.number or str(doc.pk)}.pdf"
    content  = ContentFile(pdf_bytes, name=filename)
    doc.pdf_file.save(filename, content, save=True)

    logger.info("PDF generated for %s %s (%d bytes)", doc_type, doc.pk, len(pdf_bytes))
    return pdf_bytes


def generate_pdf_by_id(doc_type: str, doc_id: str) -> bytes:
    """Convenience wrapper used by Celery tasks."""
    if doc_type not in _DOC_CONFIG:
        raise ValueError(f"Unknown doc_type: {doc_type!r}")

    Model = _import_model(_DOC_CONFIG[doc_type][0])
    doc   = Model.objects.select_related(
        "company", "company__branding", "company__vat_config"
    ).get(pk=doc_id)
    return generate_pdf(doc_type, doc)
