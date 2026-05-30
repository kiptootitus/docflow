"""
DocFlow AI — documents/docx_generator.py
==========================================
python-docx DOCX export for Invoice, Quotation, and Contract.

Pipeline
────────
  1. Open a blank python-docx Document.
  2. Apply page margins.
  3. Build a branded header table (company name + doc type/number).
  4. Add parties block (From / Bill To).
  5. Add document meta grid (dates, currency, status).
  6. For Invoice / Quotation — add line items table and totals.
  7. For Contract           — add body text and signature block.
  8. Add Notes / Terms sections.
  9. Add footer with branding text.
 10. Serialise to bytes, save to model's docx_file field, return bytes.

Public API
──────────
  generate_docx(doc_type, doc)          → bytes
  generate_docx_by_id(doc_type, doc_id) → bytes   (used by Celery tasks)
"""

from __future__ import annotations

import io
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Union

from django.conf import settings
from django.core.files.base import ContentFile

if TYPE_CHECKING:
    from .models import Contract, Invoice, Quotation
    DocumentInstance = Union[Invoice, Quotation, Contract]

logger = logging.getLogger(__name__)

_DOC_MODEL_PATHS = {
    "invoice":   "documents.models.Invoice",
    "quotation": "documents.models.Quotation",
    "contract":  "documents.models.Contract",
}


# ===========================================================================
# HELPERS
# ===========================================================================

def _import_model(dotted: str):
    module_path, class_name = dotted.rsplit(".", 1)
    import importlib
    return getattr(importlib.import_module(module_path), class_name)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#RRGGBB' to (R, G, B) tuple of ints."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (26, 86, 219)  # fallback blue
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _set_cell_bg(cell, hex_color: str) -> None:
    """Set a table cell background colour via low-level OOXML."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement("w:shd")
    shd.set(qn("w:val"),   "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"),  hex_color.lstrip("#").upper())
    tcPr.append(shd)


def _set_cell_border(cell, border: str = "single", size: int = 4, color: str = "E5E7EB") -> None:
    """Apply a border to all four sides of a cell."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"),   border)
        el.set(qn("w:sz"),    str(size))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color.lstrip("#"))
        tcBorders.append(el)
    tcPr.append(tcBorders)


def _white_run(paragraph, text: str, bold: bool = False, font_size_pt: int | None = None):
    """Add a white-coloured run to a paragraph (used in dark header cells)."""
    from docx.shared import Pt, RGBColor
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.color.rgb = RGBColor(255, 255, 255)
    if font_size_pt:
        run.font.size = Pt(font_size_pt)
    return run


def _heading_run(paragraph, text: str, color_hex: str, font_size_pt: int = 10, bold: bool = True):
    """Add a dark-colored bold run for section headings."""
    from docx.shared import Pt, RGBColor
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.size = Pt(font_size_pt)
    r, g, b = _hex_to_rgb(color_hex)
    run.font.color.rgb = RGBColor(r, g, b)
    return run


def _get_branding_colors(doc: "DocumentInstance") -> tuple[str, str]:
    """
    Returns (primary_hex, primary_hex_no_hash) from company branding.
    Falls back to DocFlow default blue.
    """
    branding = getattr(doc.company, "branding", None)
    raw = (getattr(branding, "primary_color", None) or "#1A56DB").lstrip("#")
    if len(raw) != 6:
        raw = "1A56DB"
    return f"#{raw}", raw.upper()


# ===========================================================================
# DOCUMENT SECTIONS
# ===========================================================================

def _add_header(document, doc, doc_type: str, primary_hex: str, primary_raw: str) -> None:
    """Top band: company name (left) + DOC TYPE / number (right)."""
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    tbl = document.add_table(rows=1, cols=2)
    tbl.style = "Table Grid"
    lc, rc = tbl.cell(0, 0), tbl.cell(0, 1)
    _set_cell_bg(lc, f"#{primary_raw}")
    _set_cell_bg(rc, f"#{primary_raw}")

    # Left — company name
    lp = lc.paragraphs[0]
    lp.paragraph_format.space_before = Pt(6)
    lp.paragraph_format.space_after  = Pt(6)
    _white_run(lp, doc.company.name, bold=True, font_size_pt=16)

    # Right — doc type + number
    rp = rc.paragraphs[0]
    rp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    rp.paragraph_format.space_before = Pt(4)
    _white_run(rp, f"{doc_type.upper()}\n", bold=True, font_size_pt=20)
    _white_run(rp, f"#{doc.number}", bold=False, font_size_pt=11)


def _add_parties(document, doc, vat) -> None:
    """FROM / BILL-TO (or PREPARED FOR) two-column block."""
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    tbl = document.add_table(rows=1, cols=2)
    tbl.style = "Table Grid"
    fc, tc = tbl.cell(0, 0), tbl.cell(0, 1)

    def _fill(cell, label: str, name: str, lines: list[str]) -> None:
        p = cell.paragraphs[0]
        run = p.add_run(f"{label}\n")
        run.bold = True
        run.font.size = Pt(8)
        np = cell.add_paragraph(name)
        np.runs[0].bold = True
        for line in lines:
            if line:
                cell.add_paragraph(line)

    company = doc.company
    from_lines = [
        company.email or "",
        company.phone or "",
        getattr(company, "full_address", "") or "",
        f"VAT: {vat.vat_number}" if vat and getattr(vat, "vat_number", "") else "",
    ]
    to_label = "BILL TO" if doc.__class__.__name__ == "Invoice" else "PREPARED FOR"
    to_lines = [
        doc.client_email or "",
        doc.client_phone or "",
        doc.client_address or "",
        f"VAT: {doc.client_vat_number}" if doc.client_vat_number else "",
    ]

    _fill(fc, "FROM", company.name, from_lines)
    _fill(tc, to_label, doc.client_formal_name, to_lines)


def _add_meta_row(document, doc, doc_type: str) -> None:
    """Details row: issue date, due date, currency, status."""
    from docx.shared import Pt

    labels = ["Issue Date", "Due Date", "Currency", "Status"]
    values = [
        str(doc.issue_date),
        str(getattr(doc, "due_date", None) or
            getattr(doc, "valid_until", None) or "—"),
        doc.currency,
        doc.status.upper(),
    ]

    tbl = document.add_table(rows=1, cols=len(labels))
    tbl.style = "Table Grid"
    for i, (label, val) in enumerate(zip(labels, values)):
        cell = tbl.cell(0, i)
        p = cell.paragraphs[0]
        r = p.add_run(f"{label}\n")
        r.bold = True
        r.font.size = Pt(7)
        cell.add_paragraph(val)


def _add_line_items_table(document, doc, line_items, primary_raw: str) -> None:
    """Full line-items table with branded header row."""
    from docx.shared import Pt, RGBColor

    if not line_items:
        return

    cols   = ["#", "Description", "Qty", "Unit Price", "Disc %", "Line Total"]

    tbl = document.add_table(rows=1, cols=len(cols))
    tbl.style = "Table Grid"

    # Header row
    hdr = tbl.rows[0]
    for i, col in enumerate(cols):
        cell = hdr.cells[i]
        _set_cell_bg(cell, f"#{primary_raw}")
        p = cell.paragraphs[0]
        run = p.add_run(col)
        run.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)
        run.font.size = Pt(8)

    # Data rows
    for idx, item in enumerate(line_items):
        row = tbl.add_row()
        bg  = "F9FAFB" if idx % 2 == 0 else "FFFFFF"

        # Format quantity
        if item.unit_label and item.unit_of_measure != Decimal("1"):
            qty_str = f"{item.quantity} × {item.unit_of_measure}{item.unit_label}"
        else:
            qty_str = f"{item.quantity} {item.unit_label}".strip() or str(item.quantity)

        prefix = "–" if item.item_type == "discount" else ""
        data = [
            str(idx + 1),
            f"[{item.item_type.upper()}] {item.description}",
            qty_str,
            f"{doc.currency} {item.unit_price:,.2f}",
            f"{item.discount_percent:.1f}%" if item.discount_percent else "—",
            f"{prefix}{doc.currency} {item.line_total:,.2f}",
        ]
        for i, val in enumerate(data):
            row.cells[i].text = val
            _set_cell_bg(row.cells[i], bg)


def _add_totals(document, doc, doc_type: str, vat, primary_raw: str) -> None:
    """Right-aligned totals block: subtotal → discount → tax → TOTAL → balance due."""
    from docx.shared import Pt, RGBColor
    from docx.enum.table import WD_TABLE_ALIGNMENT

    vat_label = (getattr(vat, "vat_label", None) or "VAT") if vat else "VAT"
    vat_rate  = float(getattr(vat, "vat_rate", 0) or 0)

    rows = [
        ("Subtotal",               f"{doc.currency} {doc.subtotal:,.2f}",        False),
        (f"Discount",              f"- {doc.currency} {doc.discount_amount:,.2f}", False),
        (f"{vat_label} ({vat_rate:.1f}%)", f"{doc.currency} {doc.tax_amount:,.2f}", False),
        ("TOTAL",                  f"{doc.currency} {doc.total:,.2f}",             True),
    ]
    if doc_type == "invoice":
        rows += [
            ("Amount Paid",        f"{doc.currency} {doc.amount_paid:,.2f}",      False),
            ("Balance Due",        f"{doc.currency} {doc.balance_due:,.2f}",      True),
        ]

    tbl = document.add_table(rows=0, cols=2)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.RIGHT

    for label, val, is_total in rows:
        row = tbl.add_row()
        lc, rc = row.cells[0], row.cells[1]
        if is_total:
            _set_cell_bg(lc, f"#{primary_raw}")
            _set_cell_bg(rc, f"#{primary_raw}")
            lr = lc.paragraphs[0].add_run(label)
            lr.bold = True
            lr.font.color.rgb = RGBColor(255, 255, 255)
            rr = rc.paragraphs[0].add_run(val)
            rr.bold = True
            rr.font.color.rgb = RGBColor(255, 255, 255)
        else:
            lc.text = label
            rc.text = val


def _add_contract_body(document, doc) -> None:
    """Render the contract body text with basic paragraph splitting."""
    from docx.shared import Pt
    document.add_heading("Contract Terms", level=2)
    for line in (doc.body or "").splitlines():
        if line.strip():
            p = document.add_paragraph(line.strip())
            p.paragraph_format.space_after = Pt(4)


def _add_contract_signature(document, doc) -> None:
    """Two-column signature block for contracts."""
    from docx.shared import Pt

    document.add_heading("Authorisation & Signatures", level=2)
    tbl = document.add_table(rows=1, cols=2)
    tbl.style = "Table Grid"
    fc, tc = tbl.cell(0, 0), tbl.cell(0, 1)

    # Service provider
    fc.add_paragraph(doc.company.name).runs[0].bold = True
    for _ in range(3):
        fc.add_paragraph("")
    fc.add_paragraph("Signature: ________________________")
    fc.add_paragraph("Name:      ________________________")
    fc.add_paragraph("Date:      ________________________")

    # Client
    tc.add_paragraph(doc.client_formal_name).runs[0].bold = True
    if doc.status == "signed" and doc.signed_by_name:
        tc.add_paragraph(f"✓ Signed electronically by: {doc.signed_by_name}")
        if doc.signed_at:
            tc.add_paragraph(f"Date: {doc.signed_at}")
        if doc.signature_ip:
            tc.add_paragraph(f"IP: {doc.signature_ip}")
    else:
        for _ in range(3):
            tc.add_paragraph("")
        tc.add_paragraph("Signature: ________________________")
        tc.add_paragraph("Name:      ________________________")
        tc.add_paragraph("Date:      ________________________")


def _add_notes_and_terms(document, doc) -> None:
    """Notes and Terms & Conditions text blocks."""
    from docx.shared import Pt
    if doc.notes:
        document.add_heading("Notes", level=3)
        document.add_paragraph(doc.notes)
    if doc.terms:
        document.add_heading("Terms & Conditions", level=3)
        document.add_paragraph(doc.terms)


def _add_footer_text(document, doc, doc_type: str) -> None:
    """Optional branded footer text from company branding config."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    branding = getattr(doc.company, "branding", None)
    if not branding:
        return
    field_map = {
        "invoice":   "invoice_footer_text",
        "quotation": "quotation_footer_text",
        "contract":  "contract_footer_text",
    }
    footer_text = getattr(branding, field_map.get(doc_type, ""), "") or ""
    if footer_text:
        p = document.add_paragraph(footer_text)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _spacer(document) -> None:
    document.add_paragraph()


# ===========================================================================
# PUBLIC API
# ===========================================================================

def generate_docx(doc_type: str, doc: "DocumentInstance") -> bytes:
    """
    Generate a DOCX file for the given document instance.
    Saves to doc.docx_file (S3 via django-storages).
    Returns raw bytes.
    """
    try:
        from docx import Document
        from docx.shared import Cm
    except ImportError as exc:
        raise ImportError("python-docx is required: pip install python-docx") from exc

    if doc_type not in _DOC_MODEL_PATHS:
        raise ValueError(f"Unknown doc_type: {doc_type!r}")

    company  = doc.company
    vat      = getattr(company, "vat_config", None)
    primary_hex, primary_raw = _get_branding_colors(doc)

    # ── Line items ────────────────────────────────────────────────────────
    if hasattr(doc, "line_items"):
        line_items = list(doc.line_items.all())
    else:
        line_items = []

    # ── Build document ────────────────────────────────────────────────────
    document = Document()

    # Page margins — A4 with standard margins
    section = document.sections[0]
    section.top_margin    = Cm(1.5)
    section.bottom_margin = Cm(1.5)
    section.left_margin   = Cm(2.0)
    section.right_margin  = Cm(2.0)

    # ── Header band ───────────────────────────────────────────────────────
    _add_header(document, doc, doc_type, primary_hex, primary_raw)
    _spacer(document)

    # ── Parties ───────────────────────────────────────────────────────────
    _add_parties(document, doc, vat)
    _spacer(document)

    # ── Meta row ──────────────────────────────────────────────────────────
    _add_meta_row(document, doc, doc_type)
    _spacer(document)

    # ── Subject ───────────────────────────────────────────────────────────
    if doc.subject:
        p = document.add_paragraph()
        run = p.add_run(doc.subject)
        run.bold = True

    # ── Contract-specific ─────────────────────────────────────────────────
    if doc_type == "contract":
        _spacer(document)
        if doc.body:
            _add_contract_body(document, doc)
        _spacer(document)
        _add_notes_and_terms(document, doc)
        _spacer(document)
        _add_contract_signature(document, doc)

    # ── Invoice / Quotation line items + totals ───────────────────────────
    else:
        if line_items:
            _spacer(document)
            document.add_paragraph("Line Items").runs[0].bold = True if False else None  # heading only
            _add_line_items_table(document, doc, line_items, primary_raw)
            _spacer(document)

        _add_totals(document, doc, doc_type, vat, primary_raw)

        # Payment link (Invoice only)
        if doc_type == "invoice" and getattr(doc, "stripe_payment_link_url", ""):
            _spacer(document)
            p = document.add_paragraph()
            run = p.add_run(f"Pay online: {doc.stripe_payment_link_url}")
            from docx.shared import RGBColor
            run.font.color.rgb = RGBColor(26, 86, 219)

        _spacer(document)
        _add_notes_and_terms(document, doc)

    # ── Footer ────────────────────────────────────────────────────────────
    _spacer(document)
    _add_footer_text(document, doc, doc_type)

    # ── Serialise ─────────────────────────────────────────────────────────
    buffer     = io.BytesIO()
    document.save(buffer)
    docx_bytes = buffer.getvalue()

    # ── Persist to storage ─────────────────────────────────────────────────
    filename = f"{doc.number or str(doc.pk)}.docx"
    doc.docx_file.save(filename, ContentFile(docx_bytes, name=filename), save=True)

    logger.info(
        "[DOCX] Generated %s %s — %d bytes → %s",
        doc_type, doc.pk, len(docx_bytes), doc.docx_file.name,
    )
    return docx_bytes


def generate_docx_by_id(doc_type: str, doc_id: str) -> bytes:
    """
    Fetch the document by PK and generate its DOCX.
    Convenience wrapper used by generate_docx_task (Celery).
    """
    if doc_type not in _DOC_MODEL_PATHS:
        raise ValueError(f"Unknown doc_type: {doc_type!r}")

    Model = _import_model(_DOC_MODEL_PATHS[doc_type])
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
    return generate_docx(doc_type, doc)