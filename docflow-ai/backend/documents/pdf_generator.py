"""
DocFlow AI — documents/pdf_generator.py
=========================================
WeasyPrint-based PDF generation for Invoice, Quotation, and Contract.

Pipeline
────────
  1. Fetch document + all related data from DB.
  2. Build a rich template context via _build_context().
  3. Render the HTML template with Django's template engine.
  4. Inject per-company CSS (brand colors, font, font size) as a WeasyPrint CSS sheet.
  5. Convert HTML → PDF via WeasyPrint with font configuration.
  6. Upload the PDF bytes to S3 via django-storages.
  7. Update the model's pdf_file field.
  8. Return the raw bytes.

Public API
──────────
  render_html(doc_type, doc)          → HTML string   (live preview endpoint)
  generate_pdf(doc_type, doc)         → bytes          (saves to storage)
  generate_pdf_by_id(doc_type, doc_id) → bytes         (used by Celery tasks)
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

# Map document type → (model import path, template name)
_DOC_CONFIG: dict[str, tuple[str, str]] = {
    "invoice":   ("documents.models.Invoice",   "documents/invoice.html"),
    "quotation": ("documents.models.Quotation", "documents/quotation.html"),
    "contract":  ("documents.models.Contract",  "documents/contract.html"),
}


class PDFGenerationError(Exception):
    """Raised when WeasyPrint fails to produce a PDF."""


# ===========================================================================
# HELPERS
# ===========================================================================

def _import_model(dotted: str):
    module_path, class_name = dotted.rsplit(".", 1)
    import importlib
    return getattr(importlib.import_module(module_path), class_name)


def _safe_url(field) -> str | None:
    """Return a file field URL or None — never raises."""
    try:
        return field.url if field else None
    except Exception:
        return None


def _build_context(doc: "DocumentInstance") -> dict:
    """
    Build the complete template rendering context for any document type.

    Provides:
        doc         — the document instance (Invoice / Quotation / Contract)
        company     — doc.company
        branding    — company.branding  (or None)
        vat         — company.vat_config (or None)
        logo_url    — absolute URL to company logo (or None)
        stamp_url   — absolute URL to company stamp image (or None)
        sig_url     — absolute URL to company signature image (or None)
        line_items  — list of LineItem instances (empty for Contract)
        STATIC_URL  — settings.STATIC_URL
        request     — None (WeasyPrint has no request context)
    """
    company  = doc.company
    branding = getattr(company, "branding", None)
    vat      = getattr(company, "vat_config", None)

    logo_url  = _safe_url(getattr(company, "logo", None))
    stamp_url = _safe_url(getattr(branding, "stamp", None)) if branding else None
    sig_url   = _safe_url(getattr(branding, "signature", None)) if branding else None

    # Line items — present on Invoice and Quotation, not on Contract
    if hasattr(doc, "line_items"):
        line_items = list(doc.line_items.select_related().all())
    else:
        line_items = []

    return {
        "doc":        doc,
        "company":    company,
        "branding":   branding,
        "vat":        vat,
        "logo_url":   logo_url,
        "stamp_url":  stamp_url,
        "sig_url":    sig_url,
        "line_items": line_items,
        "STATIC_URL": getattr(settings, "STATIC_URL", "/static/"),
        "request":    None,
    }


def _branding_css(doc: "DocumentInstance") -> str:
    """
    Build a WeasyPrint CSS string from the company's branding config.
    Overrides the CSS variables declared in the HTML template.
    """
    branding = getattr(doc.company, "branding", None)

    primary_color = (
        getattr(branding, "primary_color", None) or "#1A56DB"
    )
    font_family = (
        getattr(branding, "font_family", None) or "Inter"
    )
    font_size = (
        getattr(branding, "font_size_body", None) or 10
    )

    # Derive a darker shade for headers (simple approach: darken by 15%)
    def _darken(hex_color: str, factor: float = 0.85) -> str:
        try:
            h = hex_color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            r2 = max(0, int(r * factor))
            g2 = max(0, int(g * factor))
            b2 = max(0, int(b * factor))
            return f"#{r2:02x}{g2:02x}{b2:02x}"
        except Exception:
            return hex_color

    primary_dark  = _darken(primary_color, 0.82)
    primary_light = "#eff6ff"  # reasonable default — can be set in branding

    # Google Fonts import for WeasyPrint (font config handles it)
    safe_font = font_family.replace(" ", "+")
    google_import = (
        f"@import url('https://fonts.googleapis.com/css2?"
        f"family={safe_font}:wght@400;500;600;700;800&display=swap');"
    )

    css = f"""
{google_import}

:root {{
  --primary:       {primary_color};
  --primary-dark:  {primary_dark};
  --primary-light: {primary_light};
  --font-body:     '{font_family}', 'Inter', 'Helvetica Neue', Arial, sans-serif;
  --font-size:     {font_size}pt;
}}

body {{
  font-family: var(--font-body);
  font-size:   var(--font-size);
}}
"""
    return css


# ===========================================================================
# PUBLIC API
# ===========================================================================

def render_html(doc_type: str, doc: "DocumentInstance") -> str:
    """
    Render the document as an HTML string.
    Used by the live-preview endpoint (InvoiceViewSet.preview).
    Does NOT generate or save any files.
    """
    if doc_type not in _DOC_CONFIG:
        raise ValueError(f"Unknown document type: {doc_type!r}")

    _, template_name = _DOC_CONFIG[doc_type]
    context = _build_context(doc)
    return render_to_string(template_name, context)


def generate_pdf(doc_type: str, doc: "DocumentInstance") -> bytes:
    """
    Render the document as a PDF and save to the model's pdf_file field.

    Returns the raw PDF bytes.
    Raises PDFGenerationError if WeasyPrint fails.
    """
    try:
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
    except ImportError as exc:
        raise ImportError(
            "WeasyPrint is required: pip install weasyprint"
        ) from exc

    if doc_type not in _DOC_CONFIG:
        raise ValueError(f"Unknown document type: {doc_type!r}")

    # ── Render HTML ────────────────────────────────────────────────────
    html_string = render_html(doc_type, doc)

    # ── Build CSS ──────────────────────────────────────────────────────
    font_config = FontConfiguration()
    brand_css   = _branding_css(doc)

    extra_css = CSS(string=brand_css, font_config=font_config)

    # ── Base URL ───────────────────────────────────────────────────────
    # WeasyPrint uses base_url to resolve relative asset paths.
    # In production, this is typically your MEDIA_URL origin.
    base_url = getattr(settings, "SITE_URL", None) or (
        getattr(settings, "BASE_DIR", None) and str(settings.BASE_DIR)
    ) or "."

    # ── Render PDF ─────────────────────────────────────────────────────
    try:
        html_doc  = HTML(string=html_string, base_url=base_url)
        pdf_bytes: bytes = html_doc.write_pdf(
            stylesheets=[extra_css],
            font_config=font_config,
            presentational_hints=True,  # respect HTML width/height attrs
        )
    except Exception as exc:
        logger.exception("[PDF] WeasyPrint render failed for %s %s: %s", doc_type, doc.pk, exc)
        raise PDFGenerationError(f"WeasyPrint failed: {exc}") from exc

    if not pdf_bytes:
        raise PDFGenerationError("WeasyPrint produced an empty PDF")

    # ── Persist to storage ──────────────────────────────────────────────
    filename = f"{doc.number or str(doc.pk)}.pdf"
    content  = ContentFile(pdf_bytes, name=filename)

    try:
        doc.pdf_file.save(filename, content, save=True)
    except Exception as exc:
        logger.exception("[PDF] Storage save failed for %s %s: %s", doc_type, doc.pk, exc)
        raise

    logger.info(
        "[PDF] Generated %s %s — %d bytes → %s",
        doc_type, doc.pk, len(pdf_bytes), doc.pdf_file.name,
    )
    return pdf_bytes


def generate_pdf_by_id(doc_type: str, doc_id: str) -> bytes:
    """
    Fetch the document by PK and generate its PDF.
    Convenience wrapper used by generate_pdf_task (Celery).
    """
    if doc_type not in _DOC_CONFIG:
        raise ValueError(f"Unknown doc_type: {doc_type!r}")

    Model = _import_model(_DOC_CONFIG[doc_type][0])
    doc   = (
        Model.objects
        .select_related(
            "company",
            "company__branding",
            "company__vat_config",
        )
        .prefetch_related("line_items")
        .get(pk=doc_id)
    )
    return generate_pdf(doc_type, doc)


def get_or_generate_pdf(doc_type: str, doc_id: str, force: bool = False) -> tuple[bytes, bool]:
    """
    Return (pdf_bytes, was_generated).

    If the document already has a pdf_file and force=False, downloads and
    returns the existing file.  Otherwise re-generates.
    Useful for download endpoints that want to avoid redundant generation.
    """
    if doc_type not in _DOC_CONFIG:
        raise ValueError(f"Unknown doc_type: {doc_type!r}")

    Model = _import_model(_DOC_CONFIG[doc_type][0])
    doc   = Model.objects.select_related(
        "company", "company__branding", "company__vat_config"
    ).prefetch_related("line_items").get(pk=doc_id)

    if doc.pdf_file and not force:
        try:
            doc.pdf_file.open("rb")
            data = doc.pdf_file.read()
            doc.pdf_file.close()
            return data, False
        except Exception:
            pass  # fall through to regeneration

    return generate_pdf(doc_type, doc), True