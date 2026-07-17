"""
Document Tool for Robert COO Agent — Extract text from PDFs, DOCX, and spreadsheets.

Handles:
- PDF extraction via pdfplumber (primary) + PyMuPDF (fallback)
- DOCX via python-docx
- XLSX/XLS via openpyxl
- Temp file management (auto-deleted after processing — no documents stored)
- Construction document type detection
- Error handling with credential scrubbing

File size limits:
    PDF:  50MB
    DOCX: 25MB
    XLSX: 25MB
"""

import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.base import sanitize_error

logger = logging.getLogger(__name__)

# ── File size limits ──────────────────────────────────────────────────────────
FILE_SIZE_LIMITS = {
    "pdf": 50 * 1024 * 1024,   # 50MB
    "docx": 25 * 1024 * 1024,  # 25MB
    "xlsx": 25 * 1024 * 1024,  # 25MB
    "xls":  25 * 1024 * 1024,
}

# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class DocumentMetadata:
    file_name: str
    file_size_bytes: int
    mime_type: str
    document_type: str
    extracted_at: str
    page_count: Optional[int] = None
    has_tables: bool = False
    is_construction_doc: bool = False
    detected_csi_divisions: List[str] = field(default_factory=list)

@dataclass
class DocumentExtractionResult:
    success: bool
    content: str
    metadata: DocumentMetadata
    tables: Optional[List[Dict]] = None
    error: Optional[str] = None
    extraction_method: str = "unknown"
    warnings: List[str] = field(default_factory=list)


# ── Type detection ────────────────────────────────────────────────────────────

MIME_TO_TYPE = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
}

CONSTRUCTION_KEYWORDS = {
    "specification": ["section", "spec", "specification", "csi", "division", "general conditions"],
    "rfi": ["rfi", "request for information", "clarification"],
    "submittal": ["submittal", "submission", "product data", "samples"],
    "bid_tab": ["bid tab", "bid sheet", "unit price", "lump sum", "pricing"],
    "change_order": ["change order", "co #", "cost adjustment"],
    "schedule": ["schedule", "gantt", "milestone", "baseline forecast"],
    "estimate": ["estimate", "cost recap", "takeoff", "quantity"],
}


def infer_document_type(filename: str, mime_type: str = "") -> str:
    """Return 'pdf', 'docx', 'xlsx', 'xls', or 'unknown'."""
    name_lower = filename.lower()
    if mime_type in MIME_TO_TYPE:
        return MIME_TO_TYPE[mime_type]
    if name_lower.endswith(".pdf"):
        return "pdf"
    if name_lower.endswith(".docx"):
        return "docx"
    if name_lower.endswith(".doc"):
        return "docx"
    if name_lower.endswith(".xlsx"):
        return "xlsx"
    if name_lower.endswith(".xls"):
        return "xls"
    return "unknown"


def validate_file_size(file_size_bytes: int, doc_type: str) -> Optional[str]:
    """Returns error string if file too large, None if OK."""
    limit = FILE_SIZE_LIMITS.get(doc_type, 25 * 1024 * 1024)
    if file_size_bytes > limit:
        mb = file_size_bytes / (1024 * 1024)
        limit_mb = limit / (1024 * 1024)
        return f"File too large: {mb:.1f}MB (limit: {limit_mb:.0f}MB for {doc_type})"
    return None


def detect_construction_type(filename: str, text_sample: str) -> Tuple[bool, Optional[str]]:
    """Detect if document is construction-related and classify its type."""
    combined = (filename + " " + text_sample).lower()
    for doc_type, keywords in CONSTRUCTION_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return True, doc_type
    return False, None


# ── PDF extraction ────────────────────────────────────────────────────────────

def _extract_pdf_pdfplumber(filepath: str) -> Tuple[str, int, Optional[str]]:
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            pages = len(pdf.pages)
            parts = []
            for i, page in enumerate(pdf.pages):
                try:
                    t = page.extract_text()
                    if t:
                        parts.append(f"\n--- Page {i+1} ---\n{t}")
                except Exception as pe:
                    parts.append(f"\n--- Page {i+1} [failed: {sanitize_error(str(pe))}] ---")
            return "\n".join(parts), pages, None
    except ImportError:
        return "", 0, "pdfplumber not installed"
    except Exception as e:
        return "", 0, f"pdfplumber: {sanitize_error(str(e))}"


def _extract_pdf_pymupdf(filepath: str) -> Tuple[str, int, Optional[str]]:
    try:
        import fitz
        doc = fitz.open(filepath)
        pages = len(doc)
        parts = []
        for i, page in enumerate(doc):
            try:
                t = page.get_text()
                if t:
                    parts.append(f"\n--- Page {i+1} ---\n{t}")
            except Exception:
                pass
        doc.close()
        return "\n".join(parts), pages, None
    except ImportError:
        return "", 0, "PyMuPDF not installed"
    except Exception as e:
        return "", 0, f"PyMuPDF: {sanitize_error(str(e))}"


def extract_pdf(filepath: str) -> Tuple[str, int, str]:
    """Extract PDF with automatic fallback. Returns (text, pages, method)."""
    text, pages, err = _extract_pdf_pdfplumber(filepath)
    if not err:
        return text, pages, "pdfplumber"
    logger.warning(f"pdfplumber failed: {err} — trying PyMuPDF")
    text, pages, err2 = _extract_pdf_pymupdf(filepath)
    if not err2:
        return text, pages, "pymupdf"
    return "", 0, "failed"


# ── DOCX extraction ───────────────────────────────────────────────────────────

def extract_docx(filepath: str) -> Tuple[str, Optional[str]]:
    """Extract text from DOCX. Returns (text, error)."""
    try:
        from docx import Document
        doc = Document(filepath)
        parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                parts.append(para.text)
        for table in doc.tables:
            parts.append("\n--- TABLE ---")
            for row in table.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
            parts.append("--- END TABLE ---")
        return "\n".join(parts), None
    except ImportError:
        return "", "python-docx not installed; run: pip install python-docx"
    except Exception as e:
        return "", f"DOCX: {sanitize_error(str(e))}"


# ── Spreadsheet extraction ────────────────────────────────────────────────────

def _extract_xlsx(filepath: str) -> Tuple[str, List[Dict], Optional[str]]:
    try:
        from openpyxl import load_workbook
        wb = load_workbook(filepath, data_only=True)
        tables, parts = [], []
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            parts.append(f"\n=== Sheet: {sheet_name} ===")
            rows = []
            for row in sheet.iter_rows(values_only=True):
                if not any(c is not None for c in row):
                    continue
                r = [str(c) if c is not None else "" for c in row]
                rows.append(r)
                parts.append(" | ".join(r))
            if rows:
                tables.append({"sheet_name": sheet_name, "rows": rows})
        return "\n".join(parts), tables, None
    except ImportError:
        return "", [], "openpyxl not installed; run: pip install openpyxl"
    except Exception as e:
        return "", [], f"openpyxl: {sanitize_error(str(e))}"


def extract_spreadsheet(filepath: str, filename: str) -> Tuple[str, List[Dict], str]:
    """Extract spreadsheet. Returns (text, tables, method)."""
    text, tables, err = _extract_xlsx(filepath)
    if not err:
        return text, tables, "openpyxl"
    if text or tables:
        logger.warning(f"Spreadsheet had partial error: {err}")
        return text, tables, "openpyxl_partial"
    return "", [], "failed"


# ── Main entry point ──────────────────────────────────────────────────────────

def extract_document(file_bytes: bytes, filename: str,
                     document_type: str, mime_type: str = "") -> DocumentExtractionResult:
    """
    Extract text and metadata from a document.
    Temp file is created and deleted automatically.

    Args:
        file_bytes: Raw document bytes
        filename: Original filename
        document_type: "pdf", "docx", "xlsx", "xls"
        mime_type: Optional MIME type hint

    Returns:
        DocumentExtractionResult
    """
    timestamp = datetime.now().isoformat()
    metadata = DocumentMetadata(
        file_name=filename,
        file_size_bytes=len(file_bytes),
        mime_type=mime_type,
        document_type=document_type,
        extracted_at=timestamp,
    )

    # Write to temp file
    suffix = f".{document_type}"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            temp_path = tf.name
            tf.write(file_bytes)

        # Route to extractor
        content = ""
        tables = None
        extraction_method = "unknown"
        error = None

        if document_type == "pdf":
            content, page_count, extraction_method = extract_pdf(temp_path)
            metadata.page_count = page_count
            if extraction_method == "failed":
                error = "PDF extraction failed — pdfplumber and PyMuPDF both failed"

        elif document_type in ("docx", "doc"):
            content, error = extract_docx(temp_path)
            extraction_method = "python-docx"

        elif document_type in ("xlsx", "xls"):
            content, tables, extraction_method = extract_spreadsheet(temp_path, filename)
            metadata.has_tables = bool(tables)
            if extraction_method == "failed":
                error = "Spreadsheet extraction failed"

        else:
            error = f"Unsupported type: {document_type}"

        if error:
            return DocumentExtractionResult(
                success=False, content="", metadata=metadata,
                error=error, extraction_method=extraction_method,
            )

        # Detect construction document type
        sample = content[:2000]
        is_const, const_type = detect_construction_type(filename, sample)
        metadata.is_construction_doc = is_const
        if const_type:
            metadata.detected_csi_divisions = [const_type]

        # Detect CSI division numbers
        import re
        divisions = set()
        for m in re.finditer(r"(?:section|division)\s+0*(\d{1,2})\b", content, re.IGNORECASE):
            d = int(m.group(1))
            if 1 <= d <= 49:
                divisions.add(f"Div_{d:02d}")
        if divisions:
            metadata.detected_csi_divisions = sorted(list(divisions))

        return DocumentExtractionResult(
            success=True,
            content=content,
            metadata=metadata,
            tables=tables,
            extraction_method=extraction_method,
        )

    except Exception as e:
        err_str = sanitize_error(str(e))
        logger.exception(f"extract_document exception: {err_str}")
        return DocumentExtractionResult(
            success=False, content="", metadata=metadata,
            error=f"Exception: {err_str}",
        )

    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


# ── Telegram file helpers ─────────────────────────────────────────────────────

def get_telegram_file_url(file_id: str, bot_token: str) -> Tuple[Optional[str], Optional[str]]:
    """Fetch Telegram getFile URL. Returns (url, error)."""
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if not result.get("ok"):
                return None, result.get("description", "getFile failed")
            file_path = result["result"].get("file_path")
            if not file_path:
                return None, "No file_path in getFile response"
            return f"https://api.telegram.org/file/bot{bot_token}/{file_path}", None
    except Exception as e:
        return None, sanitize_error(str(e))


def download_telegram_file(url: str, timeout_sec: int = 30) -> Tuple[Optional[bytes], Optional[str]]:
    """Download file bytes from Telegram CDN. Returns (bytes, error)."""
    import urllib.request
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return resp.read(), None
    except Exception as e:
        return None, sanitize_error(str(e))
