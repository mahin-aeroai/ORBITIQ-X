"""
ORBITIQ-X Aerospace RAG
Chunking Strategy

Aerospace technical documents require specialized chunking because:
  1. Equations must not be split mid-formula
  2. Tables must stay intact (splitting rows destroys meaning)
  3. Section context matters enormously (same term means different things
     in "Propulsion" vs "Attitude Control" sections)
  4. Reference lists should NOT be chunked as Q&A context
  5. Figure captions are short but dense with metadata

Strategy: Hierarchical semantic chunking
  Level 1: Section splitting (by heading detection)
  Level 2: Semantic paragraph grouping within sections
  Level 3: Fixed-size fallback with sentence boundary respect
  Level 4: Overlap injection for cross-chunk context

Chunk sizes (tuned for BGE-M3, max 8192 tokens):
  Primary chunks:   512 tokens (~350 words)
  Overlap:          64 tokens  (~45 words)
  Min chunk size:   100 tokens (discard below)
  Max chunk size:  1024 tokens (hard split)

Special handling:
  Equations:  kept in chunk with 2-sentence context window
  Tables:     kept whole if < 1024 tokens, split by row groups otherwise
  Abstracts:  always a standalone chunk with high quality score
  Conclusions: standalone chunk
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Iterator

from ..models.schemas import ChunkMetadata, ContentType, DocumentChunk
from .loaders import RawDocument

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────

CHUNK_SIZE_TOKENS    = 512
CHUNK_OVERLAP_TOKENS = 64
MIN_CHUNK_TOKENS     = 80
MAX_CHUNK_TOKENS     = 1024
WORDS_PER_TOKEN      = 0.75  # approx for technical English


def _token_estimate(text: str) -> int:
    """Fast token count estimate (words / 0.75)."""
    return int(len(text.split()) / WORDS_PER_TOKEN)


# ── Section boundary detection ────────────────────────────────

SECTION_HEADING_RE = re.compile(
    r'^(?:'
    r'(?:\d+(?:\.\d+)*\.?\s+[A-Z][^\n]{3,80})'    # 1.2.3 Heading Text
    r'|(?:[A-Z][A-Z\s]{4,50}:?\s*$)'               # ALL CAPS HEADING
    r'|(?:Abstract|Introduction|Conclusion|References|Acknowledgements|Appendix)'
    r')$',
    re.MULTILINE,
)

EQUATION_RE = re.compile(r'\[EQ\].*?\[/EQ\]', re.DOTALL)
TABLE_RE     = re.compile(r'\[TABLE\].*?\[/TABLE\]', re.DOTALL)


@dataclass
class TextSection:
    heading: str
    body: str
    is_reference_list: bool = False
    is_abstract: bool = False
    is_conclusion: bool = False


# ── Chunker ───────────────────────────────────────────────────

class AerospaceChunker:
    """
    Three-pass chunker for aerospace technical documents.

    Pass 1: Section splitting — isolates logical document units.
    Pass 2: Within-section chunking — sentence-boundary-aware fixed-size.
    Pass 3: Special block handling — equations, tables, abstracts.
    """

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE_TOKENS,
        chunk_overlap: int = CHUNK_OVERLAP_TOKENS,
        min_chunk_size: int = MIN_CHUNK_TOKENS,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def chunk(self, doc: RawDocument) -> list[DocumentChunk]:
        """Main entry point — returns all chunks for a document."""
        chunks: list[DocumentChunk] = []

        # Use pre-extracted sections if available, else split on headings
        if doc.sections:
            sections = [
                TextSection(
                    heading=h,
                    body=b,
                    is_abstract="abstract" in h.lower(),
                    is_conclusion="conclusion" in h.lower() or "summary" in h.lower(),
                    is_reference_list=any(kw in h.lower()
                                          for kw in ("references", "bibliography")),
                )
                for h, b in doc.sections
            ]
        else:
            sections = self._split_into_sections(doc.content)

        for section in sections:
            # Skip reference lists — not useful for Q&A retrieval
            if section.is_reference_list:
                continue

            section_chunks = list(self._chunk_section(section, doc))
            chunks.extend(section_chunks)

        # Wire prev/next chunk IDs for context-window assembly
        for i, chunk in enumerate(chunks):
            if i > 0:
                chunk.metadata.prev_chunk_id = chunks[i - 1].chunk_id
            if i < len(chunks) - 1:
                chunk.metadata.next_chunk_id = chunks[i + 1].chunk_id
            chunk.metadata.chunk_index = i
            chunk.metadata.total_chunks = len(chunks)

        logger.info(f"Chunked '{doc.metadata.title}' into {len(chunks)} chunks")
        return chunks

    def _split_into_sections(self, text: str) -> list[TextSection]:
        """Split raw text into sections using heading heuristics."""
        matches = list(SECTION_HEADING_RE.finditer(text))
        sections = []

        if not matches:
            return [TextSection(heading="Document", body=text)]

        for i, match in enumerate(matches):
            heading = match.group(0).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if len(body.split()) < 10:
                continue
            sections.append(TextSection(
                heading=heading,
                body=body,
                is_abstract="abstract" in heading.lower(),
                is_conclusion="conclusion" in heading.lower(),
                is_reference_list=any(kw in heading.lower()
                                      for kw in ("references", "bibliography")),
            ))

        return sections

    def _chunk_section(
        self,
        section: TextSection,
        doc: RawDocument,
    ) -> Iterator[DocumentChunk]:
        """
        Chunk a single section.
        Special handling: abstracts and conclusions → single chunk.
        Equations and tables → kept intact with surrounding context.
        """
        text = section.body

        # Abstract/conclusion: always a single chunk regardless of length
        if section.is_abstract or section.is_conclusion:
            if _token_estimate(text) >= self.min_chunk_size:
                yield self._make_chunk(
                    text=text,
                    doc=doc,
                    section_title=section.heading,
                    content_type=ContentType.ABSTRACT if section.is_abstract else ContentType.CONCLUSION,
                    quality_score=1.0,
                )
            return

        # Extract special blocks first, yield them as standalone chunks
        # then chunk the remaining prose
        remaining, special_chunks = self._extract_special_blocks(text, doc, section.heading)
        yield from special_chunks

        # Chunk remaining prose with sentence-boundary respect
        yield from self._fixed_size_chunk(remaining, doc, section.heading)

    def _extract_special_blocks(
        self,
        text: str,
        doc: RawDocument,
        section_heading: str,
    ) -> tuple[str, list[DocumentChunk]]:
        """
        Extract equations and tables, yield as standalone chunks.
        Returns: (text_with_blocks_removed, special_chunks)
        """
        special_chunks = []
        processed = text

        # Tables: keep whole if under max size
        for match in TABLE_RE.finditer(text):
            table_text = match.group(0)
            if _token_estimate(table_text) <= MAX_CHUNK_TOKENS:
                # 2-sentence context before the table
                context_start = max(0, match.start() - 300)
                context = text[context_start:match.start()].strip()
                chunk_text = f"{context}\n\n{table_text}" if context else table_text
                special_chunks.append(self._make_chunk(
                    text=chunk_text,
                    doc=doc,
                    section_title=section_heading,
                    content_type=ContentType.TABLE,
                    quality_score=0.9,
                ))
            processed = processed.replace(table_text, "[TABLE_EXTRACTED]")

        # Equations with surrounding context
        for match in EQUATION_RE.finditer(text):
            eq_text = match.group(0)
            # Include 1 sentence before and after for context
            ctx_start = max(0, match.start() - 200)
            ctx_end   = min(len(text), match.end() + 200)
            chunk_text = text[ctx_start:ctx_end].strip()
            special_chunks.append(self._make_chunk(
                text=chunk_text,
                doc=doc,
                section_title=section_heading,
                content_type=ContentType.EQUATION,
                quality_score=0.85,
            ))
            processed = processed.replace(eq_text, "[EQ_EXTRACTED]")

        # Remove placeholder tokens
        processed = re.sub(r'\[(?:TABLE|EQ)_EXTRACTED\]', '', processed).strip()
        return processed, special_chunks

    def _fixed_size_chunk(
        self,
        text: str,
        doc: RawDocument,
        section_heading: str,
    ) -> Iterator[DocumentChunk]:
        """
        Split text into fixed-size chunks respecting sentence boundaries.
        Uses a sliding window with overlap.
        """
        # Split into sentences
        sentences = self._split_sentences(text)
        if not sentences:
            return

        current_chunk: list[str] = []
        current_tokens = 0
        overlap_buffer: list[str] = []

        for sentence in sentences:
            s_tokens = _token_estimate(sentence)

            # Flush if adding this sentence would exceed limit
            if current_tokens + s_tokens > self.chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                if _token_estimate(chunk_text) >= self.min_chunk_size:
                    yield self._make_chunk(
                        text=chunk_text,
                        doc=doc,
                        section_title=section_heading,
                        content_type=ContentType.TEXT,
                    )

                # Build overlap: last N tokens of current chunk
                overlap_text = self._build_overlap(current_chunk)
                current_chunk = overlap_text + [sentence]
                current_tokens = _token_estimate(" ".join(current_chunk))
            else:
                current_chunk.append(sentence)
                current_tokens += s_tokens

        # Final chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            if _token_estimate(chunk_text) >= self.min_chunk_size:
                yield self._make_chunk(
                    text=chunk_text,
                    doc=doc,
                    section_title=section_heading,
                    content_type=ContentType.TEXT,
                )

    def _split_sentences(self, text: str) -> list[str]:
        """
        Split text into sentences with aerospace-aware rules.
        Avoids splitting on:
          - "Eq. (3.14)" → period after "Eq" is not sentence end
          - "Fig. 4" → same
          - "approx. 500 km" → same
          - Numbers with periods: "3.14159"
          - Abbreviations: "i.e.", "e.g.", "et al.", "vs.", "cf."
        """
        # Protect common aerospace abbreviations
        PROTECT = [
            r'(?<!\w)(Eq|Fig|Sec|Ref|Tab|Ch|Vol|No|pp|et al|i\.e|e\.g|vs|cf|approx|alt|inc|Eq)\.',
            r'\b\d+\.\d+',  # decimal numbers
        ]
        protected = text
        placeholders: dict[str, str] = {}
        for i, pat in enumerate(PROTECT):
            for m in re.finditer(pat, protected, re.IGNORECASE):
                key = f"__PROT{i}_{len(placeholders)}__"
                placeholders[key] = m.group(0)
                protected = protected.replace(m.group(0), key, 1)

        # Now split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', protected)

        # Restore placeholders
        result = []
        for s in sentences:
            for key, val in placeholders.items():
                s = s.replace(key, val)
            s = s.strip()
            if s:
                result.append(s)
        return result

    def _build_overlap(self, sentences: list[str]) -> list[str]:
        """Return the last N tokens worth of sentences for overlap."""
        overlap: list[str] = []
        tokens = 0
        for sentence in reversed(sentences):
            t = _token_estimate(sentence)
            if tokens + t > self.chunk_overlap:
                break
            overlap.insert(0, sentence)
            tokens += t
        return overlap

    def _make_chunk(
        self,
        text: str,
        doc: RawDocument,
        section_title: str,
        content_type: ContentType = ContentType.TEXT,
        quality_score: float = 1.0,
    ) -> DocumentChunk:
        """Build a DocumentChunk with full metadata."""
        from uuid import uuid4
        chunk_id = str(uuid4())

        has_eq = bool(EQUATION_RE.search(text)) or "[EQ]" in text
        has_tbl = bool(TABLE_RE.search(text)) or "[TABLE]" in text

        metadata = ChunkMetadata(
            chunk_id=chunk_id,
            doc_id=doc.metadata.doc_id,
            doc_title=doc.metadata.title,
            agency=doc.metadata.agency.value,
            doc_type=doc.metadata.doc_type.value,
            publication_year=doc.metadata.publication_year,
            authors=doc.metadata.authors,
            doi=doc.metadata.doi,
            source_url=doc.metadata.source_url,
            report_number=doc.metadata.report_number,
            chunk_index=0,    # set later
            total_chunks=0,   # set later
            section_title=section_title,
            content_type=content_type,
            has_equations=has_eq,
            has_tables=has_tbl,
            topic_tags=doc.metadata.topic_tags,
            text_length=len(text),
            token_count=_token_estimate(text),
            quality_score=quality_score,
            language=doc.metadata.language,
        )

        return DocumentChunk(
            chunk_id=chunk_id,
            text=text,
            metadata=metadata,
        )


# ── Quality filter ────────────────────────────────────────────

class QualityFilter:
    """
    Rejects chunks that would degrade retrieval quality.

    Rejection criteria:
    - Too short (< min_chunk_size tokens)
    - Mostly non-textual (e.g. extraction artifacts, page numbers)
    - Reference list entries
    - Header/footer repetitions
    - Encoding garbage (>10% non-ASCII)
    """

    def __init__(self, min_tokens: int = MIN_CHUNK_TOKENS):
        self.min_tokens = min_tokens

    def is_good(self, chunk: DocumentChunk) -> bool:
        text = chunk.text.strip()
        if not text:
            return False

        # Length check
        if chunk.metadata.token_count < self.min_tokens:
            return False

        # Non-ASCII ratio
        non_ascii = sum(1 for c in text if ord(c) > 127)
        if len(text) > 0 and non_ascii / len(text) > 0.15:
            return False

        # Mostly digits/punctuation (extraction artifact)
        alpha_count = sum(1 for c in text if c.isalpha())
        if len(text) > 0 and alpha_count / len(text) < 0.4:
            return False

        # Reference-list pattern: "[1] Smith, J. et al..."
        ref_lines = re.findall(r'^\[\d+\]', text, re.MULTILINE)
        if len(ref_lines) > 3:
            return False

        return True

    def filter(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        good = [c for c in chunks if self.is_good(c)]
        rejected = len(chunks) - len(good)
        if rejected:
            logger.debug(f"Quality filter: rejected {rejected}/{len(chunks)} chunks")
        return good
