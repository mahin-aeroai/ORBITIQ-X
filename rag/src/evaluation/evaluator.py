"""
ORBITIQ-X Aerospace RAG
Evaluation Framework

Metrics tracked:
  faithfulness         — claims supported by retrieved context (NLI)
  answer_relevancy     — answer addresses the question (embedding similarity)
  context_recall       — retrieved chunks cover ground-truth facts
  context_precision    — retrieved chunks are mostly relevant (not noisy)
  entity_recall        — key aerospace entities (NORAD IDs, mission names) recovered
  citation_accuracy    — citations correctly map to supporting content
  hallucination_rate   — fraction of unsupported claims
  numeric_accuracy     — numbers match source (critical for engineering)

Evaluation dataset: aerospace_eval_v1.json
  500 question-answer pairs from:
    100 orbital mechanics (TLE, SGP4, propagation, conjunction)
    100 mission history (NASA Apollo, ESA Mars/Venus, ISRO PSLV)
    100 debris and SSA (Fengyun, Iridium-33, ASAT events)
    100 launch vehicles (PSLV variants, Falcon 9, Ariane 6)
    100 spacecraft systems (propulsion, ADCS, thermal, power)

Evaluation schedule:
  Nightly: full 500-sample eval, report to MLflow
  On PR: 50-sample smoke eval, block merge if faithfulness < 0.8
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from ..models.schemas import EvalMetrics, EvalSample, RAGQuery

logger = logging.getLogger(__name__)


# ── Evaluation dataset builder ────────────────────────────────

AEROSPACE_EVAL_QUESTIONS = [
    # Orbital mechanics
    {
        "question": "What is the SGP4 propagator and what perturbations does it model?",
        "ground_truth": "SGP4 (Simplified General Perturbations 4) is an analytical orbital propagator that models Earth's gravitational field through J2, J3, and J4 zonal harmonics, atmospheric drag using the ballistic coefficient (Bstar), and solar radiation pressure. It uses Two-Line Element sets as input and propagates mean orbital elements forward in time.",
        "ground_truth_contexts": ["sgp4", "propagator", "J2", "TLE"],
        "category": "orbital_mechanics",
    },
    {
        "question": "What is the Foster method for computing collision probability (Pc)?",
        "ground_truth": "The Foster method projects the combined position covariance of two objects onto the collision plane (perpendicular to relative velocity at TCA), then integrates a 2D Gaussian distribution over a disk of radius equal to the combined hard-body radius. The result is the collision probability Pc.",
        "ground_truth_contexts": ["Foster", "collision probability", "Pc", "covariance", "TCA"],
        "category": "conjunction_analysis",
    },
    {
        "question": "What altitude bands define LEO, MEO, and GEO orbits?",
        "ground_truth": "LEO (Low Earth Orbit): 200–2000 km. MEO (Medium Earth Orbit): 2000–35786 km. GEO (Geostationary Earth Orbit): approximately 35786 km. VLEO (Very Low Earth Orbit) is sometimes used for altitudes below 450 km.",
        "ground_truth_contexts": ["LEO", "MEO", "GEO", "altitude", "orbit regime"],
        "category": "orbital_mechanics",
    },
    # Mission history
    {
        "question": "What was the primary mission objective of Chandrayaan-3?",
        "ground_truth": "Chandrayaan-3 was India's third lunar exploration mission, aimed at achieving a soft landing near the lunar south pole. It successfully landed on August 23, 2023, making India the fourth nation to achieve a lunar soft landing and the first to land near the south pole.",
        "ground_truth_contexts": ["Chandrayaan-3", "lunar", "south pole", "ISRO"],
        "category": "mission_history",
    },
    {
        "question": "What launch vehicle does ISRO use for heavy payloads to GTO?",
        "ground_truth": "ISRO uses the GSLV Mk III (also called LVM3) for heavy payloads to Geostationary Transfer Orbit. It has a payload capacity of approximately 4000 kg to GTO, using a cryogenic upper stage.",
        "ground_truth_contexts": ["GSLV", "LVM3", "GTO", "ISRO", "cryogenic"],
        "category": "launch_vehicle",
    },
    # Debris and SSA
    {
        "question": "How many debris objects did the Fengyun-1C ASAT test create?",
        "ground_truth": "The 2007 Chinese ASAT test against Fengyun-1C created approximately 3000 trackable debris objects (> 10 cm) and an estimated 35,000 objects larger than 1 cm. The cloud is concentrated between 800-900 km altitude in a sun-synchronous orbit.",
        "ground_truth_contexts": ["Fengyun-1C", "ASAT", "debris", "2007"],
        "category": "debris",
    },
]


# ── Metric computers ──────────────────────────────────────────

class FaithfulnessEvaluator:
    """
    Compute faithfulness: fraction of answer claims supported by context.
    Uses NLI cross-encoder (same as HallucinationGuard).
    """

    def compute(
        self,
        answer: str,
        contexts: list[str],
    ) -> float:
        """Returns faithfulness score 0-1."""
        try:
            from sentence_transformers import CrossEncoder
            nli = CrossEncoder("cross-encoder/nli-deberta-v3-small", max_length=512)
        except ImportError:
            return self._keyword_faithfulness(answer, contexts)

        # Split answer into sentences
        sentences = [s.strip() for s in answer.replace('\n', ' ').split('. ') if len(s.strip()) > 20]
        if not sentences:
            return 1.0

        source = " ".join(contexts)[:2000]
        supported = 0
        for sent in sentences:
            score = nli.predict([(source, sent)])[0]
            entailment = float(score[2]) if len(score) > 2 else float(score)
            if entailment > 0.5:
                supported += 1

        return supported / len(sentences)

    def _keyword_faithfulness(self, answer: str, contexts: str) -> float:
        """Fallback: keyword overlap between answer and contexts."""
        source = " ".join(contexts).lower()
        answer_words = set(answer.lower().split())
        source_words = set(source.split())
        if not answer_words:
            return 0.0
        return len(answer_words & source_words) / len(answer_words)


class AnswerRelevancyEvaluator:
    """
    Compute answer relevancy: does the answer address the question?
    Uses embedding cosine similarity between question and answer.
    """

    def compute(self, question: str, answer: str, embedder=None) -> float:
        if embedder:
            q_emb = np.array(embedder.embed_query(question)["dense"])
            a_emb = np.array(embedder.embed_texts([answer])[0]["dense"])
            cosine = float(np.dot(q_emb, a_emb) /
                          (np.linalg.norm(q_emb) * np.linalg.norm(a_emb) + 1e-10))
            return max(0.0, cosine)

        # Fallback: keyword overlap
        q_words = set(question.lower().split())
        a_words = set(answer.lower().split())
        return len(q_words & a_words) / max(len(q_words), 1)


class EntityRecallEvaluator:
    """
    Compute entity recall: are aerospace entities from ground truth found in answer?
    Critical for SSA queries: NORAD IDs, mission names, orbit parameters.
    """

    def compute(
        self,
        ground_truth_contexts: list[str],
        generated_answer: str,
    ) -> float:
        """Fraction of ground truth context keywords present in answer."""
        if not ground_truth_contexts:
            return 1.0
        answer_lower = generated_answer.lower()
        found = sum(1 for kw in ground_truth_contexts if kw.lower() in answer_lower)
        return found / len(ground_truth_contexts)


class CitationAccuracyEvaluator:
    """
    Verify that citations in the answer map to chunks containing
    the claimed information.
    """

    def compute(
        self,
        answer_with_citations: str,
        citation_map: dict[str, str],  # {[1]: chunk_text}
    ) -> float:
        """
        For each [N] citation in the answer, check that the
        preceding sentence is entailed by chunk N's text.
        """
        citation_re = r'\[(\d+)\]'
        sentences = answer_with_citations.split('. ')
        total, correct = 0, 0

        for sentence in sentences:
            cit_matches = re.findall(citation_re, sentence)
            if not cit_matches:
                continue
            for cit_num in cit_matches:
                cit_key = f"[{cit_num}]"
                if cit_key not in citation_map:
                    continue
                chunk_text = citation_map[cit_key]
                # Simple keyword check
                sent_words = set(sentence.lower().split())
                chunk_words = set(chunk_text.lower().split())
                overlap = len(sent_words & chunk_words) / max(len(sent_words), 1)
                total += 1
                if overlap > 0.15:  # at least 15% keyword overlap
                    correct += 1

        return correct / total if total > 0 else 1.0


class NumericAccuracyEvaluator:
    """
    Critical for aerospace: are numeric values correct?
    Extracts numbers from ground truth and answer, compares.
    """

    def compute(self, ground_truth: str, generated_answer: str) -> float:
        import re
        num_re = re.compile(r'(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)')

        gt_nums  = set(float(x) for x in num_re.findall(ground_truth))
        ans_nums = set(float(x) for x in num_re.findall(generated_answer))

        if not gt_nums:
            return 1.0

        matched = 0
        for gt_val in gt_nums:
            for ans_val in ans_nums:
                if gt_val == 0:
                    if ans_val == 0:
                        matched += 1
                        break
                elif abs(ans_val - gt_val) / abs(gt_val) <= 0.10:
                    matched += 1
                    break

        return matched / len(gt_nums)


# ── RAG Evaluator ─────────────────────────────────────────────

class AerospaceRAGEvaluator:
    """
    Full evaluation harness for the ORBITIQ-X aerospace RAG system.

    Usage:
        evaluator = AerospaceRAGEvaluator(rag_pipeline)
        metrics = await evaluator.evaluate(eval_dataset)
        evaluator.save_report(metrics, "eval_report.json")
    """

    def __init__(self, rag_pipeline, embedder=None):
        self.rag = rag_pipeline
        self.embedder = embedder
        self.faithfulness_eval  = FaithfulnessEvaluator()
        self.relevancy_eval     = AnswerRelevancyEvaluator()
        self.entity_eval        = EntityRecallEvaluator()
        self.citation_eval      = CitationAccuracyEvaluator()
        self.numeric_eval       = NumericAccuracyEvaluator()

    async def evaluate_sample(self, sample: EvalSample) -> dict[str, float]:
        """Evaluate a single question-answer pair."""
        query_obj = RAGQuery(
            query=sample.question,
            top_k=8,
            use_hyde=True,
            rerank=True,
            mmr_diversity=True,
        )

        # Run the RAG pipeline
        try:
            response = await self.rag.answer(query_obj)
        except Exception as e:
            logger.error(f"RAG failed for: {sample.question[:60]}: {e}")
            return {"faithfulness": 0, "answer_relevancy": 0, "error": str(e)}

        answer = response.answer
        contexts = [c.text for c in response.retrieved_chunks]
        citation_map = {c.citation_key: c.excerpt
                        for c in response.sources if c.citation_key}

        return {
            "faithfulness":    self.faithfulness_eval.compute(answer, contexts),
            "answer_relevancy": self.relevancy_eval.compute(
                sample.question, answer, self.embedder
            ),
            "context_recall":  self._context_recall(
                sample.ground_truth_contexts, contexts
            ),
            "entity_recall":   self.entity_eval.compute(
                sample.ground_truth_contexts, answer
            ),
            "citation_accuracy": self.citation_eval.compute(answer, citation_map),
            "numeric_accuracy":  self.numeric_eval.compute(
                sample.ground_truth_answer, answer
            ),
            "hallucination_rate": 1.0 - response.faithfulness_score,
            "latency_ms": response.latency_ms,
        }

    def _context_recall(self, gt_contexts: list[str], retrieved: list[str]) -> float:
        """Fraction of ground-truth context keywords found in any retrieved chunk."""
        if not gt_contexts:
            return 1.0
        all_retrieved = " ".join(retrieved).lower()
        found = sum(1 for kw in gt_contexts if kw.lower() in all_retrieved)
        return found / len(gt_contexts)

    async def evaluate(
        self,
        samples: list[EvalSample] | None = None,
        max_samples: int = 500,
    ) -> EvalMetrics:
        """Run full evaluation suite."""
        if samples is None:
            samples = self._load_default_dataset()

        samples = samples[:max_samples]
        results = []

        for i, sample in enumerate(samples):
            logger.info(f"Evaluating sample {i+1}/{len(samples)}: {sample.question[:50]}")
            result = await self.evaluate_sample(sample)
            results.append(result)
            if (i + 1) % 10 == 0:
                logger.info(f"Progress: {i+1}/{len(samples)} | "
                           f"avg_faithfulness={np.mean([r.get('faithfulness',0) for r in results]):.3f}")

        def avg(key): return float(np.mean([r.get(key, 0) for r in results]))

        metrics = EvalMetrics(
            faithfulness=avg("faithfulness"),
            answer_relevancy=avg("answer_relevancy"),
            context_recall=avg("context_recall"),
            context_precision=avg("context_recall"),  # proxy
            entity_recall=avg("entity_recall"),
            citation_accuracy=avg("citation_accuracy"),
            hallucination_rate=avg("hallucination_rate"),
            numeric_accuracy=avg("numeric_accuracy"),
            sample_count=len(results),
        )

        logger.info(f"\nEvaluation complete ({len(results)} samples):")
        logger.info(f"  Faithfulness:    {metrics.faithfulness:.3f}")
        logger.info(f"  Answer Relevancy: {metrics.answer_relevancy:.3f}")
        logger.info(f"  Entity Recall:   {metrics.entity_recall:.3f}")
        logger.info(f"  Citation Acc:    {metrics.citation_accuracy:.3f}")
        logger.info(f"  Numeric Acc:     {metrics.numeric_accuracy:.3f}")
        logger.info(f"  Hallucination:   {metrics.hallucination_rate:.3f}")

        return metrics

    def _load_default_dataset(self) -> list[EvalSample]:
        """Load built-in evaluation questions."""
        return [
            EvalSample(
                question=q["question"],
                ground_truth_answer=q["ground_truth"],
                ground_truth_contexts=q["ground_truth_contexts"],
            )
            for q in AEROSPACE_EVAL_QUESTIONS
        ]

    def save_report(self, metrics: EvalMetrics, path: str) -> None:
        report = metrics.model_dump()
        report["generated_at"] = datetime.utcnow().isoformat()
        Path(path).write_text(json.dumps(report, indent=2, default=str))
        logger.info(f"Evaluation report saved to {path}")

    def assert_quality_gates(self, metrics: EvalMetrics) -> None:
        """Raise AssertionError if any metric falls below production threshold."""
        gates = {
            "faithfulness":    0.80,
            "answer_relevancy": 0.70,
            "entity_recall":   0.75,
            "citation_accuracy": 0.80,
            "numeric_accuracy":  0.85,
            "hallucination_rate": 0.15,  # max allowed
        }
        failures = []
        for metric, threshold in gates.items():
            val = getattr(metrics, metric)
            if metric == "hallucination_rate":
                if val > threshold:
                    failures.append(f"{metric}={val:.3f} > threshold={threshold}")
            else:
                if val < threshold:
                    failures.append(f"{metric}={val:.3f} < threshold={threshold}")
        if failures:
            raise AssertionError(
                f"RAG quality gates failed:\n" + "\n".join(f"  - {f}" for f in failures)
            )
        logger.info("All quality gates passed")
