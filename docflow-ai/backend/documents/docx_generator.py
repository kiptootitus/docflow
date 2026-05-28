"""
DocFlow AI — documents/docx_generator.py

python-docx DOCX export for Invoice and Quotation.
Contracts use their `body` field (rich text) — rendered separately.

Usage:
    from documents.docx_generator import generate_docx
    docx_bytes = generate_docx("invoice", invoice_instance)
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

_DOC_MODELS = {
    "invoice":   "documents.models.Invoice",
    "quotation": "documents.models.Quotation",
    "contract":  "documents.models.Contract",
}


def _import_model(dotted: str):
    module_path, class_name = dotted.rsplit(".", 1)
    import importlib
    return getattr(importlib.import_module(module_path), class_name)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _set_cell_bg(cell, hex_color: str) -> None:
    """Set a table cell background colour via XML."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement("w:shd")
    shd.set(qn("w:val"),   "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"),  hex_color.lstrip("#"))
    tcPr.append(shd)


def _bold(run) -> None:
    run.bold = True


def generate_docx(doc_type: str, doc: "DocumentInstance") -> bytes:
    """
    Generate a DOCX file for the given document instance.
    Returns raw bytes and saves to doc.docx_file.
    """
    try:
        from docx import Document
        from docx.shared import Pt, Cm, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
    except ImportError as exc:
        raise ImportError("python-docx is required: pip install python-docx") from exc

    company  = doc.company
    branding = getattr(company, "branding", None)
    vat      = getattr(company, "vat_config", None)

    primary_hex   = (branding.primary_color   if branding else "#1A56DB").lstrip("#")
    secondary_hex = (branding.secondary_color if branding else "#6B7280").lstrip("#")
    primary_rgb   = _hex_to_rgb("#" + primary_hex)

    document = Document()

    # Page margins
    section = document.sections[0]
    section.top_margin    = Cm(1.5)
    section.bottom_margin = Cm(1.5)
    section.left_margin   = Cm(2)
    section.right_margin  = Cm(2)

    # Header — Company name + document type
    header_table = document.add_table(rows=1, cols=2)
    header_table.style = "Table Grid"
    lc = header_table.cell(0, 0)
    rc = header_table.cell(0, 1)
    _set_cell_bg(lc, "#" + primary_hex)
    _set_cell_bg(rc, "#" + primary_hex)

    # Company name (left)
    p = lc.paragraphs[0]
    run = p.add_run(company.name)
    run.bold      = True
    run.font.size = Pt(16)
    run.font.color.rgb = RGBColor(255, 255, 255)

    # Document type + number (right)
    p2 = rc.paragraphs[0]
    p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r2 = p2.add_run(f"{doc_type.upper()}\n#{doc.number}")
    r2.bold      = True
    r2.font.size = Pt(14)
    r2.font.color.rgb = RGBColor(255, 255, 255)

    document.add_paragraph()  # spacer

    # Parties block
    parties = document.add_table(rows=1, cols=2)
    parties.style = "Table Grid"

    from_cell = parties.cell(0, 0)
    to_cell   = parties.cell(0, 1)

    from_p = from_cell.paragraphs[0]
    from_p.add_run("FROM\n").bold = True
    from_cell.add_paragraph(company.name)
    if company.email:
        from_cell.add_paragraph(company.email)
    if company.phone:
        from_cell.add_paragraph(company.phone)
    if company.full_address:
        from_cell.add_paragraph(company.full_address)
    vat_number = getattr(vat, "vat_number", "") if vat else ""
    if vat_number:
        from_cell.add_paragraph(f"VAT: {vat_number}")

    to_p = to_cell.paragraphs[0]
    to_p.add_run("BILL TO\n").bold = True

    # Use formal name logic which handles client_salutation
    to_cell.add_paragraph(doc.client_formal_name)
    if doc.client_email:
        to_cell.add_paragraph(doc.client_email)
    if doc.client_phone:
        to_cell.add_paragraph(doc.client_phone)
    if doc.client_address:
        to_cell.add_paragraph(doc.client_address)

    document.add_paragraph()

    # Dates / meta
    meta = document.add_table(rows=1, cols=4)
    meta.style = "Table Grid"
    labels = ["Issue Date", "Due Date", "Currency", "Status"]
    values = [
        str(doc.issue_date),
        str(doc.due_date or "—"),
        doc.currency,
        getattr(doc, "status", "—").upper(),
    ]
    for i, (label, val) in enumerate(zip(labels, values)):
        cell = meta.cell(0, i)
        cell.paragraphs[0].add_run(f"{label}\n").bold = True
        cell.add_paragraph(val)

    document.add_paragraph()

    # Line items table (not for Contract)
    line_items = list(getattr(doc, "line_items", type("_", (), {"all": lambda self: []})()).all()) if hasattr(doc, "line_items") else []

    if line_items:
        cols   = ["#", "Description", "Qty", "Unit Price", "Discount", "Total"]
        widths = [0.5, 7, 1.5, 2, 1.5, 2]  # cm

        li_table = document.add_table(rows=1, cols=len(cols))
        li_table.style = "Table Grid"

        # Header row
        hdr_row = li_table.rows[0]
        for i, (col, w) in enumerate(zip(cols, widths)):
            cell = hdr_row.cells[i]
            _set_cell_bg(cell, "#" + primary_hex)
            p = cell.paragraphs[0]
            run = p.add_run(col)
            run.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            run.font.size = Pt(9)
            cell.width = Cm(w)

        # Data rows
        for idx, item in enumerate(line_items):
            row = li_table.add_row()
            bg  = "F9FAFB" if idx % 2 == 0 else "FFFFFF"

            # Format quantity text to factor in unit_of_measure descriptions if present
            if item.unit_label and item.unit_of_measure != Decimal("1"):
                qty_str = f"{item.quantity} ({item.unit_of_measure} {item.unit_label})"
            else:
                qty_str = f"{item.quantity} {item.unit_label}".strip()
                if not qty_str:
                    qty_str = str(item.quantity)

            data = [
                str(idx + 1),
                item.description,
                qty_str,
                f"{doc.currency} {item.unit_price:,.2f}",
                f"{item.discount_percent}%",
                f"{doc.currency} {item.line_total:,.2f}",
            ]
            for i, val in enumerate(data):
                row.cells[i].text = val
                _set_cell_bg(row.cells[i], bg)

        document.add_paragraph()

    # Totals summary
    totals_table = document.add_table(rows=0, cols=2)
    totals_table.style = "Table Grid"
    totals_table.alignment = WD_TABLE_ALIGNMENT.RIGHT

    vat_label = (vat.vat_label if vat else "VAT") or "VAT"
    vat_rate  = float(vat.vat_rate if vat else 0)

    rows_data = [
        ("Subtotal",   f"{doc.currency} {doc.subtotal:,.2f}",        False),
        ("Discount",   f"- {doc.currency} {doc.discount_amount:,.2f}", False),
        (f"{vat_label} ({vat_rate:.1f}%)", f"{doc.currency} {doc.tax_amount:,.2f}", False),
        ("TOTAL",      f"{doc.currency} {doc.total:,.2f}",            True),
    ]
    if doc_type == "invoice":
        rows_data += [
            ("Amount Paid", f"{doc.currency} {doc.amount_paid:,.2f}", False),
            ("Balance Due", f"{doc.currency} {doc.balance_due:,.2f}", True),
        ]

    for label, val, is_total in rows_data:
        row = totals_table.add_row()
        lc2 = row.cells[0]
        rc2 = row.cells[1]
        if is_total:
            _set_cell_bg(lc2, "#" + primary_hex)
            _set_cell_bg(rc2, "#" + primary_hex)
            lr = lc2.paragraphs[0].add_run(label)
            lr.bold = True
            lr.font.color.rgb = RGBColor(255, 255, 255)
            rr = rc2.paragraphs[0].add_run(val)
            rr.bold = True
            rr.font.color.rgb = RGBColor(255, 255, 255)
        else:
            lc2.text = label
            rc2.text = val

    # Contract body (if contract)
    if doc_type == "contract" and getattr(doc, "body", ""):
        document.add_paragraph()
        document.add_heading("Contract Terms", level=2)
        for line in doc.body.splitlines():
            document.add_paragraph(line)

    # Notes + footer
    if doc.notes:
        document.add_paragraph()
        document.add_heading("Notes", level=3)
        document.add_paragraph(doc.notes)

    footer_text = ""
    if branding:
        footer_text = branding.invoice_footer_text if doc_type == "invoice" else \
                      branding.quotation_footer_text if doc_type == "quotation" else \
                      branding.contract_footer_text
    if footer_text:
        document.add_paragraph()
        fp = document.add_paragraph(footer_text)
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Serialise + save
    buffer = io.BytesIO()
    document.save(buffer)
    docx_bytes = buffer.getvalue()

    filename = f"{doc.number or str(doc.pk)}.docx"
    doc.docx_file.save(filename, ContentFile(docx_bytes, name=filename), save=True)

    logger.info("DOCX generated for %s %s (%d bytes)", doc_type, doc.pk, len(docx_bytes))
    return docx_bytes


def generate_docx_by_id(doc_type: str, doc_id: str) -> bytes:
    """Convenience wrapper used by Celery tasks."""
    if doc_type not in _DOC_MODELS:
        raise ValueError(f"Unknown doc_type: {doc_type!r}")
    Model = _import_model(_DOC_MODELS[doc_type])
    doc = Model.objects.select_related(
        "company", "company__branding", "company__vat_config"
    ).get(pk=doc_id)
    return generate_docx(doc_type, doc)