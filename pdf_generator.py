"""
pdf_generator.py
================
Generiranje profesionalnih PDF računa iz InvoiceData objekata.

Renderer prioritet:
  1. WeasyPrint  — najpreciznije, preporučeno
  2. pdfkit      — fallback (zahtijeva wkhtmltopdf na sistemu)
  3. xhtml2pdf   — čisti Python, bez sistemskih zavisnosti

Instalacija:
  pip install weasyprint jinja2
  # ili
  pip install pdfkit jinja2      (+ apt install wkhtmltopdf)
  # ili
  pip install xhtml2pdf jinja2   (samo Python)

Funkcije:
  render_invoice_html()  — HTML string iz predloška
  invoice_to_pdf()       — PDF bajti za jednu fakturu
  invoices_to_pdfs()     — lista PDF bajtova za više faktura
  get_renderer_name()    — koji renderer je aktivan
"""

from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

# ─────────────────────────────────────────────────────────────────────────────
# Putanja do Jinja2 predložaka
# ─────────────────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent / "templates"


# ─────────────────────────────────────────────────────────────────────────────
# Detekcija dostupnog PDF renderera
# ─────────────────────────────────────────────────────────────────────────────

def _detect_renderer() -> str:
    """Vrati naziv prvog dostupnog PDF renderera."""
    # 1. WeasyPrint
    try:
        import weasyprint  # noqa: F401
        return "weasyprint"
    except ImportError:
        pass

    # 2. pdfkit (zahtijeva wkhtmltopdf)
    try:
        import pdfkit
        # Provjeri je li wkhtmltopdf instaliran
        pdfkit.configuration()
        return "pdfkit"
    except Exception:
        pass

    # 3. xhtml2pdf (čisti Python fallback)
    try:
        import xhtml2pdf  # noqa: F401
        return "xhtml2pdf"
    except ImportError:
        pass

    return "none"


_RENDERER = _detect_renderer()


def get_renderer_name() -> str:
    """Vrati naziv aktivnog PDF renderera."""
    return _RENDERER


# ─────────────────────────────────────────────────────────────────────────────
# Jinja2 okruženje
# ─────────────────────────────────────────────────────────────────────────────

def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Priprema konteksta predloška
# ─────────────────────────────────────────────────────────────────────────────

_DETAIL_LABELS: list[tuple[str, str]] = [
    ("Naziv dobavljača",      "NAZIVPP"),
    ("Sjedište",              "SJEDISTEPP"),
    ("JIB / ID broj",         "IDPDVPP"),
    ("PDV broj",              "JIBPUPP"),
    ("Broj fakture",          "BROJFAKT"),
    ("Datum fakture",         "DATUMF"),
    ("Datum prijema",         "DATUMPF"),
]


def _build_context(invoice) -> dict:
    """Kreira kontekst dict za Jinja2 predložak."""
    data    = invoice.to_dict() if hasattr(invoice, "to_dict") else dict(invoice)
    errors  = getattr(invoice, "_errors",   [])
    warnings= getattr(invoice, "_warnings", [])

    details = [
        (label, data.get(field, ""))
        for label, field in _DETAIL_LABELS
    ]

    return {
        "invoice":      invoice,
        "details":      details,
        "errors":       errors,
        "warnings":     warnings,
        "generated_at": datetime.now().strftime("%d.%m.%Y u %H:%M"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# HTML rendering
# ─────────────────────────────────────────────────────────────────────────────

def render_invoice_html(invoice, template_name: str = "invoice.html") -> str:
    """
    Renderuje HTML string iz Jinja2 predloška za jednu fakturu.

    Parametri
    ---------
    invoice       : InvoiceData objekat
    template_name : naziv predloška u templates/ direktoriju

    Vraća
    -----
    HTML string spreman za PDF konverziju ili prikaz u browseru.
    """
    env      = _get_jinja_env()
    template = env.get_template(template_name)
    context  = _build_context(invoice)
    return template.render(**context)


# ─────────────────────────────────────────────────────────────────────────────
# PDF konverzija — WeasyPrint
# ─────────────────────────────────────────────────────────────────────────────

def _html_to_pdf_weasyprint(html: str) -> bytes:
    from weasyprint import HTML, CSS
    pdf_bytes = HTML(string=html, base_url=str(_TEMPLATES_DIR)).write_pdf()
    return pdf_bytes


# ─────────────────────────────────────────────────────────────────────────────
# PDF konverzija — pdfkit
# ─────────────────────────────────────────────────────────────────────────────

def _html_to_pdf_pdfkit(html: str) -> bytes:
    import pdfkit
    options = {
        "page-size": "A4",
        "encoding": "UTF-8",
        "quiet": "",
        "enable-local-file-access": None,
        "margin-top": "18mm",
        "margin-bottom": "18mm",
        "margin-left": "15mm",
        "margin-right": "15mm",
    }
    return pdfkit.from_string(html, False, options=options)


# ─────────────────────────────────────────────────────────────────────────────
# PDF konverzija — xhtml2pdf
# ─────────────────────────────────────────────────────────────────────────────

def _html_to_pdf_xhtml2pdf(html: str) -> bytes:
    from xhtml2pdf import pisa
    buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(
        src=html.encode("utf-8"),
        dest=buffer,
        encoding="utf-8",
    )
    if pisa_status.err:
        raise RuntimeError(
            f"xhtml2pdf greška pri generisanju PDF-a: {pisa_status.err}"
        )
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

_RENDERERS = {
    "weasyprint": _html_to_pdf_weasyprint,
    "pdfkit":     _html_to_pdf_pdfkit,
    "xhtml2pdf":  _html_to_pdf_xhtml2pdf,
}


def _html_to_pdf(html: str) -> bytes:
    """Pozovi aktivni renderer."""
    if _RENDERER == "none":
        raise RuntimeError(
            "Nije pronađen PDF renderer. "
            "Instaliraj jedan od: weasyprint, pdfkit, xhtml2pdf.\n"
            "  pip install weasyprint"
        )
    fn = _RENDERERS.get(_RENDERER)
    if fn is None:
        raise RuntimeError(f"Nepoznati renderer: {_RENDERER}")
    return fn(html)


# ─────────────────────────────────────────────────────────────────────────────
# Javne funkcije
# ─────────────────────────────────────────────────────────────────────────────

def invoice_to_pdf(
    invoice,
    template_name: str = "invoice.html",
) -> bytes:
    """
    Generiše PDF za jednu fakturu.

    Parametri
    ---------
    invoice       : InvoiceData objekat
    template_name : naziv Jinja2 predloška

    Vraća
    -----
    bytes — sadržaj PDF fajla

    Raises
    ------
    RuntimeError ako PDF renderer nije instaliran.
    """
    html = render_invoice_html(invoice, template_name)
    return _html_to_pdf(html)


def invoices_to_pdfs(
    invoices: list,
    template_name: str = "invoice.html",
    skip_errors: bool = True,
) -> list[tuple[str, bytes]]:
    """
    Generiše PDF za svaku fakturu u listi.

    Parametri
    ---------
    invoices      : lista InvoiceData objekata
    template_name : naziv Jinja2 predloška
    skip_errors   : ako True, preskoči fakturu s greškom i nastavi

    Vraća
    -----
    Lista tuple-ova (naziv_fajla, pdf_bytes).
    Naziv fajla je oblika 'faktura_{BROJFAKT}.pdf' ili 'faktura_{N}.pdf'.
    """
    results: list[tuple[str, bytes]] = []

    for i, inv in enumerate(invoices, start=1):
        broj = getattr(inv, "BROJFAKT", "") or f"{i:04d}"
        # Sanitiziraj naziv fajla
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(broj))
        filename = f"faktura_{safe}.pdf"

        try:
            pdf_bytes = invoice_to_pdf(inv, template_name)
            results.append((filename, pdf_bytes))
        except Exception as e:
            if skip_errors:
                print(f"[pdf_generator] Greška za '{filename}': {e}")
            else:
                raise

    return results


def save_invoice_pdf(
    invoice,
    output_path: Optional[str] = None,
    template_name: str = "invoice.html",
) -> Path:
    """
    Spremi PDF fakture na disk.

    Parametri
    ---------
    invoice     : InvoiceData objekat
    output_path : putanja do izlaznog PDF fajla.
                  Ako nije zadana, kreira se u output/ folderu pored ovog fajla.
    template_name : naziv Jinja2 predloška

    Vraća
    -----
    Path do generisanog fajla.
    """
    if output_path is None:
        broj = getattr(invoice, "BROJFAKT", "") or "nepoznato"
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(broj))
        output_path = str(
            Path(__file__).parent / "output" / f"faktura_{safe}.pdf"
        )

    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    pdf_bytes = invoice_to_pdf(invoice, template_name)
    p.write_bytes(pdf_bytes)
    return p
