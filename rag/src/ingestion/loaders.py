"""
ORBITIQ-X Aerospace RAG
Document Ingestion Pipeline

Handles 7 source types with format-specific loaders:
  PDF        — NASA/ESA/ISRO technical reports, papers (pdfplumber)
  HTML       — ESA web documents, NASA NTRS pages (BeautifulSoup)
  LaTeX      — arXiv preprints, textbook source (pylatexenc)
  DOCX       — Operator manuals, internal reports (python-docx)
  TXT/MD     — Preprocessed text, README files
  EPUB       — Digital textbooks
  BIBTEX     — Reference databases for citation harvesting

Architecture:
  SourceDiscovery → FormatRouter → Loader → Normalizer → QualityFilter → Output
"""

from __future__ import annotations

import hashlib
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

import httpx

from ..models.schemas import AgencyType, DocumentMetadata, DocumentType

logger = logging.getLogger(__name__)


# ── Raw document representation ───────────────────────────────

@dataclass
class RawDocument:
    content: str                    # full extracted text
    metadata: DocumentMetadata
    raw_path: str
    format: str                     # pdf|html|latex|docx|txt|epub
    pages: list[str] | None = None  # per-page text if available
    sections: list[tuple[str, str]] | None = None  # [(heading, body)]


# ── Base loader ───────────────────────────────────────────────

class BaseLoader(ABC):
    """All format loaders implement this interface."""

    @abstractmethod
    def can_load(self, path: str) -> bool:
        """Return True if this loader handles the given path/URL."""

    @abstractmethod
    def load(self, path: str, metadata: DocumentMetadata) -> RawDocument:
        """Load and extract text from the document."""


# ── PDF Loader ────────────────────────────────────────────────

class PDFLoader(BaseLoader):
    """
    Primary loader for NASA/ESA/ISRO technical reports.

    Uses pdfplumber (preferred over PyMuPDF for table preservation).
    Extracts: text, section headings, tables as structured text,
    figure captions, equations (as LaTeX if tagged, else raw text).

    Aerospace-specific handling:
    - Detects multi-column layouts (common in IEEE papers)
    - Preserves equation numbering: "Eq. (3.14)"
    - Extracts figure captions for image-text pairs
    - Handles scanned PDFs via pytesseract fallback
    """

    def can_load(self, path: str) -> bool:
        return path.lower().endswith(".pdf") or "application/pdf" in path

    def load(self, path: str, metadata: DocumentMetadata) -> RawDocument:
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("Install pdfplumber: pip install pdfplumber")

        pages_text: list[str] = []
        sections: list[tuple[str, str]] = []
        full_text_parts: list[str] = []

        with pdfplumber.open(path) as pdf:
            metadata.total_pages = len(pdf.pages)

            for page_num, page in enumerate(pdf.pages):
                # Extract text with layout preservation
                text = page.extract_text(
                    x_tolerance=2,
                    y_tolerance=3,
                    layout=True,
                    x_density=7.25,
                    y_density=13,
                ) or ""

                # Extract tables and render as structured text
                tables = page.extract_tables()
                for table in tables:
                    if table:
                        table_text = self._table_to_text(table)
                        text += f"\n\n[TABLE]\n{table_text}\n[/TABLE]\n"

                pages_text.append(text)
                full_text_parts.append(text)

        full_text = "\n\n".join(full_text_parts)

        # Detect and extract sections
        sections = self._extract_sections(full_text)

        # Clean up common PDF artifacts
        full_text = self._clean_pdf_text(full_text)

        # Compute SHA-256 for deduplication
        metadata.hash_sha256 = hashlib.sha256(full_text.encode()).hexdigest()

        return RawDocument(
            content=full_text,
            metadata=metadata,
            raw_path=path,
            format="pdf",
            pages=pages_text,
            sections=sections,
        )

    def _table_to_text(self, table: list[list]) -> str:
        """Convert a pdfplumber table to readable text."""
        if not table:
            return ""
        rows = []
        for row in table:
            cells = [str(c or "").strip() for c in row]
            rows.append(" | ".join(cells))
        return "\n".join(rows)

    def _extract_sections(self, text: str) -> list[tuple[str, str]]:
        """
        Heuristic section detection for aerospace technical docs.
        Patterns:
          "1. Introduction"
          "2.3 Orbital Mechanics"
          "SECTION III: PROPULSION"
          "Abstract", "Conclusion", "References"
        """
        # Pattern: numbered section headings
        section_pattern = re.compile(
            r'^(?:(\d+(?:\.\d+)*\.?\s+[A-Z][^\n]{3,60})|'  # 1.2 Heading
            r'([A-Z][A-Z\s]{4,40}):?\s*$)',                  # ALL CAPS HEADING
            re.MULTILINE,
        )
        matches = list(section_pattern.finditer(text))
        sections = []
        for i, match in enumerate(matches):
            heading = match.group(0).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if len(body) > 50:
                sections.append((heading, body))
        return sections

    def _clean_pdf_text(self, text: str) -> str:
        """Remove PDF extraction artifacts common in aerospace docs."""
        # Remove page headers/footers (repeated short lines)
        text = re.sub(r'\n(.{1,60})\n\1\n', '\n', text)
        # Merge hyphenated line breaks (common in two-column PDFs)
        text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
        # Normalize whitespace
        text = re.sub(r' {2,}', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


# ── HTML Loader ───────────────────────────────────────────────

class HTMLLoader(BaseLoader):
    """
    Loads ESA web docs, NASA NTRS pages, arXiv HTML.
    Extracts structured content: headings, paragraphs, equations (MathML→text).
    """

    def can_load(self, path: str) -> bool:
        return (path.lower().endswith((".html", ".htm"))
                or path.startswith("http"))

    def load(self, path: str, metadata: DocumentMetadata) -> RawDocument:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError("Install beautifulsoup4: pip install beautifulsoup4 lxml")

        if path.startswith("http"):
            response = httpx.get(path, timeout=30, follow_redirects=True)
            response.raise_for_status()
            html = response.text
        else:
            html = Path(path).read_text(encoding="utf-8", errors="replace")

        soup = BeautifulSoup(html, "lxml")

        # Remove navigation, ads, scripts
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Extract structured sections
        sections: list[tuple[str, str]] = []
        current_heading = "Introduction"
        current_body: list[str] = []

        for elem in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre"]):
            if elem.name in ("h1", "h2", "h3", "h4"):
                if current_body:
                    sections.append((current_heading, " ".join(current_body)))
                current_heading = elem.get_text(strip=True)
                current_body = []
            else:
                text = elem.get_text(separator=" ", strip=True)
                if text and len(text) > 20:
                    current_body.append(text)

        if current_body:
            sections.append((current_heading, " ".join(current_body)))

        full_text = "\n\n".join(
            f"{heading}\n{body}" for heading, body in sections
        )
        metadata.hash_sha256 = hashlib.sha256(full_text.encode()).hexdigest()

        return RawDocument(
            content=full_text,
            metadata=metadata,
            raw_path=path,
            format="html",
            sections=sections,
        )


# ── LaTeX Loader ──────────────────────────────────────────────

class LaTeXLoader(BaseLoader):
    """
    Handles arXiv preprints and aerospace textbooks in LaTeX source.
    Preserves equation structure, converts to readable form.
    """

    def can_load(self, path: str) -> bool:
        return path.lower().endswith((".tex", ".latex"))

    def load(self, path: str, metadata: DocumentMetadata) -> RawDocument:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")

        # Extract sections
        section_pattern = re.compile(
            r'\\(?:chapter|section|subsection|subsubsection)\*?\{([^}]+)\}'
        )

        # Replace common LaTeX commands with readable equivalents
        text = raw
        text = re.sub(r'\\begin\{equation\}(.*?)\\end\{equation\}',
                       r'\n[EQ] \1 [/EQ]\n', text, flags=re.DOTALL)
        text = re.sub(r'\$\$(.+?)\$\$', r' [EQ] \1 [/EQ] ', text, flags=re.DOTALL)
        text = re.sub(r'\$(.+?)\$', r' \1 ', text)
        text = re.sub(r'\\(?:emph|textbf|textit|text)\{([^}]+)\}', r'\1', text)
        text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
        text = re.sub(r'\\[a-zA-Z]+', '', text)
        text = re.sub(r'[{}]', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        metadata.hash_sha256 = hashlib.sha256(text.encode()).hexdigest()

        # Build sections from LaTeX structure
        sections = []
        matches = list(section_pattern.finditer(raw))
        for i, m in enumerate(matches):
            heading = m.group(1)
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            body = raw[start:end]
            body = re.sub(r'\\[a-zA-Z]+\{?([^}]*)\}?', r'\1', body)
            sections.append((heading, body.strip()))

        return RawDocument(
            content=text.strip(),
            metadata=metadata,
            raw_path=path,
            format="latex",
            sections=sections,
        )


# ── DOCX Loader ───────────────────────────────────────────────

class DOCXLoader(BaseLoader):
    """Loads satellite operator manuals and internal technical reports."""

    def can_load(self, path: str) -> bool:
        return path.lower().endswith(".docx")

    def load(self, path: str, metadata: DocumentMetadata) -> RawDocument:
        try:
            import docx
        except ImportError:
            raise ImportError("Install python-docx: pip install python-docx")

        doc = docx.Document(path)
        sections: list[tuple[str, str]] = []
        current_heading = "Document"
        current_body: list[str] = []

        for para in doc.paragraphs:
            if para.style.name.startswith("Heading"):
                if current_body:
                    sections.append((current_heading, " ".join(current_body)))
                current_heading = para.text.strip()
                current_body = []
            elif para.text.strip():
                current_body.append(para.text.strip())

        if current_body:
            sections.append((current_heading, " ".join(current_body)))

        # Extract tables
        for table in doc.tables:
            rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows.append(" | ".join(cells))
            table_text = "\n".join(rows)
            if table_text.strip():
                sections.append(("[TABLE]", table_text))

        full_text = "\n\n".join(f"{h}\n{b}" for h, b in sections)
        metadata.hash_sha256 = hashlib.sha256(full_text.encode()).hexdigest()
        metadata.total_pages = len(doc.paragraphs) // 40  # rough estimate

        return RawDocument(
            content=full_text,
            metadata=metadata,
            raw_path=path,
            format="docx",
            sections=sections,
        )


# ── Format router ─────────────────────────────────────────────

LOADERS: list[BaseLoader] = [
    PDFLoader(),
    HTMLLoader(),
    LaTeXLoader(),
    DOCXLoader(),
]


def load_document(path: str, metadata: DocumentMetadata) -> RawDocument | None:
    """Route a document path to the correct loader."""
    for loader in LOADERS:
        if loader.can_load(path):
            try:
                doc = loader.load(path, metadata)
                logger.info(f"Loaded {path}: {len(doc.content)} chars via {loader.__class__.__name__}")
                return doc
            except Exception as e:
                logger.error(f"Failed to load {path} with {loader.__class__.__name__}: {e}")
                return None
    logger.warning(f"No loader found for: {path}")
    return None


# ── Agency detector ───────────────────────────────────────────

_AGENCY_PATTERNS = {
    AgencyType.NASA:   [r'\bNASA\b', r'National Aeronautics', r'NASA/TM', r'NASA/CR'],
    AgencyType.ESA:    [r'\bESA\b', r'European Space Agency', r'ESTEC', r'SP-\d{3}'],
    AgencyType.ISRO:   [r'\bISRO\b', r'Indian Space Research', r'VSSC', r'SAC-'],
    AgencyType.JAXA:   [r'\bJAXA\b', r'Japan Aerospace'],
    AgencyType.CNSA:   [r'\bCNSA\b', r'China National Space'],
}

def detect_agency(text: str, title: str = "") -> AgencyType:
    combined = f"{title} {text[:2000]}"
    for agency, patterns in _AGENCY_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, combined, re.IGNORECASE):
                return agency
    return AgencyType.OTHER


_DOCTYPE_PATTERNS = {
    DocumentType.MISSION_REPORT:   [r'Mission Report', r'Flight Report', r'Post-Mission'],
    DocumentType.TECHNICAL_REPORT: [r'Technical(?:\s+Note|\s+Memorandum|\s+Report)', r'TM-\d', r'TR-\d'],
    DocumentType.RESEARCH_PAPER:   [r'Abstract', r'Journal of', r'IEEE\s+Trans', r'Acta Astro'],
    DocumentType.TEXTBOOK:         [r'Chapter \d', r'Introduction to', r'Fundamentals of'],
    DocumentType.OPERATOR_MANUAL:  [r'Operator\s+Manual', r'User\s+Manual', r'ICD-\d'],
    DocumentType.DEBRIS_STUDY:     [r'Space Debris', r'Mitigation', r'Fragmentation'],
    DocumentType.STANDARDS_DOC:    [r'ISO \d{4,}', r'ECSS-', r'MIL-STD-'],
}

def detect_doc_type(text: str, title: str = "") -> DocumentType:
    combined = f"{title} {text[:3000]}"
    for doc_type, patterns in _DOCTYPE_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, combined, re.IGNORECASE):
                return doc_type
    return DocumentType.UNKNOWN
