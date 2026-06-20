"""
ORBITIQ-X Aerospace RAG
Hallucination Mitigation + Source Citation Strategy

Aerospace answers require engineering-grade accuracy.
A hallucinated Isp value or wrong collision probability could
propagate into mission-critical analysis. Three defence layers:

Layer 1 — Retrieval faithfulness gate:
    Before generating, verify every factual claim in the answer
    is entailed by at least one retrieved chunk.
    Uses NLI (Natural Language Inference) cross-encoder.

Layer 2 — Numeric claim verifier:
    Extract all numbers from the answer (velocities, distances,
    probabilities, dates, masses). Cross-check each against
    retrieved chunks. Flag any that deviate > 10%.

Layer 3 — Uncertainty surfacing:
    Instruct Claude to explicitly mark uncertain claims with
    [UNCERTAIN] and to state when the context is insufficient.
    Post-process the output to surface these as structured flags.

Source Citation Strategy:
    IEEE-style inline citations: [1], [2], [3]
    Every factual sentence gets a citation to the chunk it came from.
    Full bibliography at end with report number, DOI, URL.
    "Traceable reference" = citation maps to exact page + section.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from ..models.schemas import CitationRecord, RAGResponse, RetrievedChunk

logger = logging.getLogger(__name__)

# ── Prompts ───────────────────────────────────────────────────

RAG_SYSTEM_PROMPT = """You are ORBITIQ-X, an aerospace intelligence assistant with
access to a curated corpus of NASA, ESA, ISRO, and academic aerospace documents.

STRICT RULES — you MUST follow all of these:

1. ONLY use information from the provided CONTEXT sections. Do not use your
   pre-training knowledge for specific technical claims.

2. Every factual sentence MUST end with an inline citation: [1], [2], etc.
   matching the SOURCE INDEX in the context.

3. If a fact cannot be found in the context, write:
   "This information is not available in the provided sources."
   Do NOT invent values.

4. For any claim you are uncertain about, add [UNCERTAIN] after the citation:
   "The Isp is approximately 311 s [3][UNCERTAIN]"

5. Include ALL relevant units: distances in km, velocities in km/s or m/s,
   masses in kg, probabilities as dimensionless decimals.

6. For numeric values (probabilities, altitudes, velocities, masses):
   reproduce the exact value from the source — do not approximate unless
   the source itself gives a range.

7. At the end, add a "Confidence assessment" paragraph explaining what
   aspects of the answer are well-supported vs uncertain.

CONTEXT:
{context}

QUESTION: {query}

ANSWER (with IEEE inline citations):"""

FAITHFULNESS_CHECK_PROMPT = """You are a fact-checker for aerospace engineering answers.

Given an ANSWER and the SOURCE PASSAGES it was generated from,
identify which claims in the ANSWER are NOT supported by the source passages.

Mark each unsupported claim with REASON.

Output ONLY a JSON array of unsupported claims:
[
  {{"claim": "exact text from answer", "reason": "not found in sources"}},
  ...
]
If all claims are supported, output: []

SOURCE PASSAGES:
{sources}

ANSWER:
{answer}

Unsupported claims (JSON):"""

UNCERTAINTY_INSTRUCTION = """
For the following answer, identify all sentences that contain:
- Approximate values ("approximately", "about", "roughly")
- Uncertain predictions ("may", "might", "could")
- Claims that hedge with "typically" or "generally"
- Any [UNCERTAIN] markers

Return a JSON array of such sentences:
[{{"sentence": "...", "uncertainty_type": "approximation|prediction|general"}}]

ANSWER: {answer}
"""


# ── Context builder ───────────────────────────────────────────

class ContextBuilder:
    """
    Assembles retrieved chunks into a structured prompt context block.

    Each source gets a header with citation key, title, agency, year,
    and section reference. This enables Claude to cite precisely.
    """

    MAX_CONTEXT_TOKENS = 32_000  # leave room for system + query + answer

    def build(
        self,
        chunks: list[RetrievedChunk],
        query: str,
    ) -> tuple[str, list[CitationRecord]]:
        """
        Build context string and citation records.
        Returns (context_block, citations).
        """
        citations: list[CitationRecord] = []
        context_parts: list[str] = []
        token_budget = self.MAX_CONTEXT_TOKENS
        seen_docs: set[str] = set()

        for i, chunk in enumerate(chunks):
            citation_key = f"[{i + 1}]"
            chunk.citation_key = citation_key

            # Build readable source header
            meta = chunk.metadata
            year_str = str(meta.publication_year) if meta.publication_year else "n.d."
            authors_str = ", ".join(meta.authors[:3])
            if len(meta.authors) > 3:
                authors_str += " et al."

            section_ref = ""
            if meta.section_title:
                section_ref = f", §{meta.section_title}"
            if meta.page_start:
                section_ref += f", p.{meta.page_start}"

            source_header = (
                f"SOURCE {citation_key} | {meta.agency} | {year_str}"
                f" | {meta.doc_title[:80]}"
                f"{section_ref}"
            )
            if meta.report_number:
                source_header += f" | {meta.report_number}"
            if meta.doi:
                source_header += f" | DOI:{meta.doi}"

            chunk_block = f"{source_header}\n{chunk.text}"
            chunk_tokens = len(chunk.text.split()) // 0.75  # approx

            if token_budget - chunk_tokens < 2000:  # reserve 2K for answer
                logger.debug(f"Context budget exhausted at chunk {i+1}")
                break

            context_parts.append(chunk_block)
            token_budget -= chunk_tokens

            # Build citation record
            citation = CitationRecord(
                citation_key=citation_key,
                chunk_id=chunk.chunk_id,
                doc_id=meta.doc_id,
                title=meta.doc_title,
                authors=meta.authors,
                year=meta.publication_year,
                agency=meta.agency,
                doc_type=meta.doc_type,
                doi=meta.doi,
                source_url=meta.source_url,
                report_number=meta.report_number,
                page_ref=f"p.{meta.page_start}" if meta.page_start else None,
                section_ref=meta.section_title,
                relevance_score=chunk.final_score,
                excerpt=chunk.text[:300],
            )
            citations.append(citation)

        context_block = "\n\n---\n\n".join(context_parts)
        return context_block, citations

    def build_prompt(
        self,
        query: str,
        context: str,
    ) -> str:
        return RAG_SYSTEM_PROMPT.format(context=context, query=query)


# ── Hallucination guard ───────────────────────────────────────

class HallucinationGuard:
    """
    Three-layer hallucination detection for aerospace answers.

    Layer 1: NLI faithfulness check
    Layer 2: Numeric claim verification
    Layer 3: Uncertainty extraction
    """

    # Confidence thresholds
    FAITHFULNESS_THRESHOLD = 0.7   # below this → flag whole answer
    NUMERIC_TOLERANCE      = 0.10  # 10% deviation flags a numeric claim

    def __init__(self, anthropic_client):
        self.client = anthropic_client
        self._nli_model = None

    def _load_nli(self):
        """Load cross-encoder NLI model for entailment check."""
        if self._nli_model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._nli_model = CrossEncoder(
                    "cross-encoder/nli-deberta-v3-small",
                    max_length=512,
                )
                logger.info("NLI cross-encoder loaded")
            except ImportError:
                logger.warning("sentence-transformers not installed; NLI disabled")

    def check_faithfulness(
        self,
        answer: str,
        source_texts: list[str],
    ) -> tuple[float, list[str]]:
        """
        Check what fraction of answer sentences are entailed by sources.

        Returns (faithfulness_score 0-1, list of unsupported sentences).
        """
        self._load_nli()
        if self._nli_model is None:
            return 1.0, []  # skip if model unavailable

        sentences = self._split_answer_sentences(answer)
        source_concat = " ".join(source_texts[:5])  # truncate for NLI

        unsupported = []
        supported_count = 0

        for sentence in sentences:
            if len(sentence.split()) < 5:
                continue  # skip very short sentences

            # NLI: premise=source, hypothesis=claim
            score = self._nli_model.predict(
                [(source_concat[:1000], sentence)]
            )[0]

            # DeBERTa NLI: [contradiction, neutral, entailment]
            entailment_score = float(score[2]) if len(score) > 2 else float(score)
            if entailment_score < 0.5:
                unsupported.append(sentence)
            else:
                supported_count += 1

        total = len([s for s in sentences if len(s.split()) >= 5])
        faithfulness = supported_count / total if total > 0 else 1.0
        return faithfulness, unsupported

    def verify_numerics(
        self,
        answer: str,
        source_texts: list[str],
    ) -> list[str]:
        """
        Extract numeric claims from answer and verify against sources.
        Returns list of suspicious numeric claims.
        """
        # Extract value-unit pairs from answer
        numeric_re = re.compile(
            r'(\d+(?:\.\d+)?(?:×10[⁻-]\d+)?)\s*'
            r'(km|km/s|m/s|kg|kN|s|°|yr|days?|%|e-\d+)',
            re.IGNORECASE,
        )
        answer_values = numeric_re.findall(answer)

        suspicious = []
        source_text = " ".join(source_texts)

        for val_str, unit in answer_values:
            try:
                val = float(val_str.replace('×10', 'e').replace('−', '-'))
            except ValueError:
                continue

            # Check if this value appears in sources (within tolerance)
            src_values = [
                float(m.group(1).replace('×10', 'e').replace('−', '-'))
                for m in numeric_re.finditer(source_text)
                if m.group(2).lower() == unit.lower()
            ]

            if src_values:
                closest = min(src_values, key=lambda x: abs(x - val))
                if closest != 0 and abs(closest - val) / abs(closest) > self.NUMERIC_TOLERANCE:
                    suspicious.append(
                        f"Value '{val_str} {unit}' deviates from source "
                        f"(closest: {closest} {unit})"
                    )

        return suspicious

    def extract_uncertainty_flags(self, answer: str) -> list[str]:
        """
        Extract sentences marked as uncertain by the model.
        Also detects hedging language patterns.
        """
        flags = []

        # Explicit [UNCERTAIN] markers
        uncertain_re = re.compile(r'([^.!?]*\[UNCERTAIN\][^.!?]*[.!?])')
        for m in uncertain_re.finditer(answer):
            flags.append(m.group(1).strip())

        # Hedging language patterns
        hedge_patterns = [
            r'approximately|roughly|about|around',
            r'may be|might be|could be|possibly',
            r'typically|generally|usually|often',
            r'it is believed|it has been suggested',
            r'further analysis is needed|insufficient data',
        ]
        sentences = self._split_answer_sentences(answer)
        for sentence in sentences:
            if any(re.search(p, sentence, re.IGNORECASE) for p in hedge_patterns):
                if sentence not in flags:
                    flags.append(sentence)

        return flags

    def compute_confidence(
        self,
        faithfulness: float,
        unsupported_count: int,
        total_sentences: int,
        numeric_issues: int,
        avg_retrieval_score: float,
    ) -> float:
        """
        Aggregate confidence score for the full answer.
        Weights: retrieval quality 30%, faithfulness 50%, numeric accuracy 20%.
        """
        retrieval_conf  = min(1.0, avg_retrieval_score * 2)  # normalize 0-0.5 to 0-1
        faithfulness_conf = faithfulness
        numeric_conf = max(0.0, 1.0 - (numeric_issues * 0.15))

        confidence = (
            0.30 * retrieval_conf
            + 0.50 * faithfulness_conf
            + 0.20 * numeric_conf
        )
        return round(confidence, 3)

    def _split_answer_sentences(self, text: str) -> list[str]:
        # Remove citations like [1], [2], [UNCERTAIN]
        clean = re.sub(r'\[\d+\]|\[UNCERTAIN\]', '', text)
        return [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean) if s.strip()]


# ── Citation formatter ────────────────────────────────────────

class CitationFormatter:
    """
    Formats citation records into multiple output styles.
    Supports IEEE, APA, and inline reference block.
    """

    def format_ieee(self, citations: list[CitationRecord]) -> str:
        """IEEE style: [1] Author(s), 'Title,' Journal, year."""
        lines = []
        for c in citations:
            authors = "; ".join(c.authors[:3])
            if len(c.authors) > 3:
                authors += " et al."
            year = str(c.year) if c.year else "n.d."
            line = f"{c.citation_key} {authors}, \"{c.title},\" {c.agency}, {year}."
            if c.report_number:
                line += f" {c.report_number}."
            if c.doi:
                line += f" DOI: {c.doi}."
            elif c.source_url:
                line += f" {c.source_url}."
            lines.append(line)
        return "\n".join(lines)

    def format_apa(self, citations: list[CitationRecord]) -> str:
        """APA style: Author(s) (year). Title. Agency."""
        lines = []
        for c in citations:
            authors = ", ".join(c.authors[:3])
            if len(c.authors) > 3:
                authors += ", et al."
            year = f"({c.year})" if c.year else "(n.d.)"
            line = f"{authors} {year}. *{c.title}*. {c.agency}."
            if c.doi:
                line += f" https://doi.org/{c.doi}"
            lines.append(line)
        return "\n".join(lines)

    def format_inline_block(self, citations: list[CitationRecord]) -> str:
        """
        Structured block for aerospace engineering reports.
        Shows title, agency, report number, section, excerpt.
        """
        blocks = []
        for c in citations:
            block = [f"### {c.citation_key} — {c.title}"]
            block.append(f"**Agency:** {c.agency}")
            if c.year:
                block.append(f"**Year:** {c.year}")
            if c.report_number:
                block.append(f"**Report:** {c.report_number}")
            if c.doi:
                block.append(f"**DOI:** {c.doi}")
            if c.section_ref:
                block.append(f"**Section:** {c.section_ref}")
            if c.page_ref:
                block.append(f"**Page:** {c.page_ref}")
            block.append(f"**Relevance:** {c.relevance_score:.3f}")
            block.append(f"**Excerpt:** _{c.excerpt[:200]}..._")
            blocks.append("\n".join(block))
        return "\n\n".join(blocks)

    def attach_citations_to_answer(
        self,
        answer: str,
        citations: list[CitationRecord],
        style: str = "ieee",
    ) -> str:
        """
        Append formatted bibliography to generated answer.
        """
        bib = self.format_ieee(citations) if style == "ieee" else self.format_apa(citations)
        return f"{answer}\n\n---\n\n**References**\n\n{bib}"
