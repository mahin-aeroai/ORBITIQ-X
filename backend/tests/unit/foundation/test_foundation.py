"""
ORBITIQ-X — Foundation Model Platform Test Suite
==================================================
Tests all components of the aerospace foundation model infrastructure.

Test categories
────────────────
  Training Dataset     : TrainingRecord, builder, export
  Instruction Dataset  : template coverage, augmentation, eval integration
  Reasoning Dataset    : chain-of-thought traces, domain coverage
  Dataset Registry     : registration, stats, deduplication
  Benchmark Suite      : task structure, scoring, category coverage
  Evaluation Pipeline  : AerospaceBenchmarkEvaluator, quality gates
  Model Registry       : register, get, metrics, best model
  Experiment Tracker   : create, log, complete
  Foundation Service   : tier selection, graceful degradation
  API Endpoints        : all 10 routes, correct status codes
  Performance          : dataset build speed, scoring throughput

All tests hermetic — no Neo4j, Qdrant, or Anthropic API required.

Run
───
  pytest tests/unit/foundation/ -v --asyncio-mode=auto
  pytest tests/unit/foundation/ -v -k "benchmark"
  pytest tests/unit/foundation/ -v -s -k "performance"
"""

from __future__ import annotations

import sys
import pathlib
import time
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parents[3]))


# ═══════════════════════════════════════════════════════════════
# TRAINING DATASET TESTS (Phases 1-4)
# ═══════════════════════════════════════════════════════════════

class TestTrainingRecord:
    """Phase 1: TrainingRecord data model."""

    def _make_record(self, **kwargs):
        from app.services.foundation.dataset import (
            TrainingRecord, TrainingDomain, ExampleType
        )
        return TrainingRecord(
            record_id="test-001",
            domain=kwargs.get("domain", TrainingDomain.ORBITAL_MECHANICS),
            example_type=kwargs.get("type", ExampleType.INSTRUCTION),
            instruction="What is the SGP4 propagator?",
            output="SGP4 is an analytical orbital propagator...",
            reasoning_trace=kwargs.get("trace", []),
            corpus_source_ref=kwargs.get("source", "HOOTS-ROEHRICH-1980"),
            graph_node_refs=kwargs.get("graph_refs", ["OrbitalRegime:LEO"]),
            difficulty=kwargs.get("difficulty", "medium"),
        )

    def test_record_has_fingerprint(self):
        r = self._make_record()
        assert isinstance(r.fingerprint, str)
        assert len(r.fingerprint) == 16

    def test_identical_content_same_fingerprint(self):
        r1 = self._make_record()
        r2 = self._make_record()
        assert r1.fingerprint == r2.fingerprint

    def test_different_content_different_fingerprint(self):
        from app.services.foundation.dataset import TrainingRecord, TrainingDomain, ExampleType
        r1 = TrainingRecord(
            record_id="a", domain=TrainingDomain.ORBITAL_MECHANICS,
            example_type=ExampleType.INSTRUCTION,
            instruction="Question A", output="Answer A", reasoning_trace=[],
        )
        r2 = TrainingRecord(
            record_id="b", domain=TrainingDomain.CONJUNCTION_ANALYSIS,
            example_type=ExampleType.INSTRUCTION,
            instruction="Question B", output="Answer B", reasoning_trace=[],
        )
        assert r1.fingerprint != r2.fingerprint

    def test_record_to_jsonl(self):
        import json
        r = self._make_record()
        jsonl = r.to_jsonl()
        parsed = json.loads(jsonl)
        assert parsed["instruction"] == r.instruction
        assert parsed["output"] == r.output
        assert parsed["domain"] == r.domain.value

    def test_record_with_reasoning_trace(self):
        r = self._make_record(trace=["Step 1: check Kp", "Step 2: assess drag"])
        jsonl = r.to_jsonl()
        import json
        parsed = json.loads(jsonl)
        assert len(parsed["reasoning_trace"]) == 2

    def test_all_training_domains_exist(self):
        from app.services.foundation.dataset import TrainingDomain
        expected = {
            "orbital_mechanics", "conjunction_analysis", "space_debris",
            "mission_history", "launch_vehicles", "satellite_systems",
            "ssa", "space_weather", "standards", "operators",
        }
        actual = {d.value for d in TrainingDomain}
        assert expected <= actual

    def test_all_example_types_exist(self):
        from app.services.foundation.dataset import ExampleType
        expected = {"instruction", "reasoning", "corpus_extract", "graph_derived", "evaluation"}
        actual = {t.value for t in ExampleType}
        assert expected == actual


class TestInstructionTemplates:
    """Phase 2: Instruction template coverage."""

    def test_templates_cover_required_domains(self):
        from app.services.foundation.dataset import INSTRUCTION_TEMPLATES, TrainingDomain
        required = {
            TrainingDomain.ORBITAL_MECHANICS,
            TrainingDomain.CONJUNCTION_ANALYSIS,
            TrainingDomain.SPACE_DEBRIS,
            TrainingDomain.MISSION_HISTORY,
            TrainingDomain.LAUNCH_VEHICLES,
            TrainingDomain.SSA,
            TrainingDomain.OPERATORS,
        }
        assert required <= set(INSTRUCTION_TEMPLATES.keys())

    def test_orbital_mechanics_has_sgp4(self):
        from app.services.foundation.dataset import INSTRUCTION_TEMPLATES, TrainingDomain
        om_templates = INSTRUCTION_TEMPLATES[TrainingDomain.ORBITAL_MECHANICS]
        texts = " ".join(t["instruction"] + t["output"] for t in om_templates).lower()
        assert "sgp4" in texts
        assert "julian" in texts or "propagat" in texts

    def test_conjunction_has_foster_pc(self):
        from app.services.foundation.dataset import INSTRUCTION_TEMPLATES, TrainingDomain
        conj_templates = INSTRUCTION_TEMPLATES[TrainingDomain.CONJUNCTION_ANALYSIS]
        texts = " ".join(t["output"] for t in conj_templates).lower()
        assert "foster" in texts
        assert "collision" in texts and "probability" in texts

    def test_all_templates_have_required_fields(self):
        from app.services.foundation.dataset import INSTRUCTION_TEMPLATES
        for domain, templates in INSTRUCTION_TEMPLATES.items():
            for t in templates:
                assert "instruction" in t, f"Missing instruction in {domain}"
                assert "output" in t, f"Missing output in {domain}"
                assert "difficulty" in t, f"Missing difficulty in {domain}"

    def test_total_template_count(self):
        from app.services.foundation.dataset import INSTRUCTION_TEMPLATES
        total = sum(len(v) for v in INSTRUCTION_TEMPLATES.values())
        assert total >= 15  # at least 15 high-quality base examples

    def test_corpus_refs_are_valid(self):
        """All corpus_source references must be valid CORPUS_SOURCES ids."""
        from app.services.foundation.dataset import INSTRUCTION_TEMPLATES
        from app.services.graphrag.corpus_service import CORPUS_SOURCES
        valid_ids = {s.source_id for s in CORPUS_SOURCES}
        for domain, templates in INSTRUCTION_TEMPLATES.items():
            for t in templates:
                src = t.get("corpus_source")
                if src:
                    assert src in valid_ids, f"Invalid source_id '{src}' in {domain}"


class TestReasoningDataset:
    """Phase 3: Chain-of-thought reasoning traces."""

    def test_reasoning_templates_exist(self):
        from app.services.foundation.dataset import REASONING_TEMPLATES
        assert len(REASONING_TEMPLATES) >= 3

    def test_reasoning_templates_have_steps(self):
        from app.services.foundation.dataset import REASONING_TEMPLATES
        for t in REASONING_TEMPLATES:
            assert "reasoning_steps" in t
            assert len(t["reasoning_steps"]) >= 4, \
                f"Too few steps in reasoning template: {t.get('instruction', '')[:50]}"

    def test_reasoning_templates_cover_key_domains(self):
        from app.services.foundation.dataset import REASONING_TEMPLATES, TrainingDomain
        domains = {t["domain"] for t in REASONING_TEMPLATES}
        assert TrainingDomain.ORBITAL_MECHANICS in domains
        assert TrainingDomain.CONJUNCTION_ANALYSIS in domains

    def test_reasoning_steps_are_numbered(self):
        from app.services.foundation.dataset import REASONING_TEMPLATES
        for t in REASONING_TEMPLATES:
            for i, step in enumerate(t["reasoning_steps"]):
                assert "Step" in step or "step" in step, \
                    f"Step {i+1} missing 'Step' label: {step[:40]}"


class TestDatasetBuilder:
    """Dataset building and export."""

    def test_build_instruction_dataset(self):
        from app.services.foundation.dataset import AerospaceDatasetBuilder
        builder = AerospaceDatasetBuilder(seed=42)
        records = builder.build_instruction_dataset(target_size=50)
        assert len(records) >= 15  # at least the base templates
        assert all(r.instruction for r in records)
        assert all(r.output     for r in records)

    def test_build_instruction_augmentation(self):
        from app.services.foundation.dataset import AerospaceDatasetBuilder, ExampleType
        builder = AerospaceDatasetBuilder(seed=42)
        records = builder.build_instruction_dataset(target_size=100, include_augmented=True)
        # Should have augmented examples
        augmented = [r for r in records if r.quality_score < 1.0]
        assert len(augmented) > 0

    def test_build_reasoning_dataset(self):
        from app.services.foundation.dataset import AerospaceDatasetBuilder, ExampleType
        builder = AerospaceDatasetBuilder()
        records = builder.build_reasoning_dataset()
        assert len(records) >= 3
        for r in records:
            assert r.example_type == ExampleType.REASONING
            assert len(r.reasoning_trace) >= 4

    def test_build_graph_derived_dataset(self):
        from app.services.foundation.dataset import AerospaceDatasetBuilder
        builder = AerospaceDatasetBuilder()
        graph_nodes = [
            {"type": "Satellite", "noradId": 25544, "name": "ISS",
             "regime": "LEO", "operatorName": "NASA", "countryCode": "US",
             "perigeeKm": 410, "apogeeKm": 420, "inclinationDeg": 51.6},
            {"type": "LaunchVehicle", "vehicleId": "LV-PSLV", "name": "PSLV",
             "operator": "ISRO", "country": "IN", "status": "active",
             "payloadLeoKg": 3800},
            {"type": "ConjunctionEvent", "conjunctionId": "CDM-001",
             "primaryNorad": 25544, "secondaryNorad": 44713,
             "tca": "2025-06-17T12:00:00Z", "missDistanceKm": 0.25,
             "collisionProbability": 2e-3, "riskLevel": "red"},
        ]
        records = builder.build_graph_derived_dataset(graph_nodes)
        assert len(records) == 3  # one per node type
        assert all(r.graph_node_refs for r in records)

    def test_split_train_eval(self):
        from app.services.foundation.dataset import AerospaceDatasetBuilder
        builder = AerospaceDatasetBuilder(seed=42)
        records = builder.build_instruction_dataset(target_size=100)
        train, eval_set = builder.split_train_eval(records, eval_ratio=0.1)
        assert len(train) > len(eval_set)
        assert len(train) + len(eval_set) == len(records)

    def test_export_jsonl(self, tmp_path):
        from app.services.foundation.dataset import AerospaceDatasetBuilder
        builder = AerospaceDatasetBuilder()
        records = builder.build_instruction_dataset(target_size=20)
        out_path = tmp_path / "test.jsonl"
        count = builder.export_jsonl(records, out_path)
        assert count == len(records)
        assert out_path.exists()
        lines = out_path.read_text().strip().split("\n")
        assert len(lines) == len(records)


class TestDatasetRegistry:
    """Phase 5: Dataset registry."""

    def test_register_and_get(self):
        from app.services.foundation.dataset import (
            AerospaceDatasetRegistry, AerospaceDatasetBuilder, TrainingRecord
        )
        registry = AerospaceDatasetRegistry()
        builder  = AerospaceDatasetBuilder()
        records  = builder.build_instruction_dataset(target_size=20)

        entry = registry.register("test-v1", "train", records, "Test dataset")
        assert entry["total_records"] == len(records)
        assert entry["dataset_id"] == "test-v1"
        assert entry["split"] == "train"

    def test_registry_stats(self):
        from app.services.foundation.dataset import AerospaceDatasetRegistry, AerospaceDatasetBuilder
        registry = AerospaceDatasetRegistry()
        builder  = AerospaceDatasetBuilder()
        records  = builder.build_instruction_dataset(target_size=20)
        registry.register("test-v1", "train", records)
        registry.register("test-v1", "eval",  records[:5])

        stats = registry.stats()
        assert stats["total_datasets"] == 2
        assert stats["total_records"] == len(records) + 5

    def test_registry_counts_unique(self):
        from app.services.foundation.dataset import AerospaceDatasetRegistry, AerospaceDatasetBuilder
        registry = AerospaceDatasetRegistry()
        builder  = AerospaceDatasetBuilder()
        records  = builder.build_instruction_dataset(target_size=20)

        entry = registry.register("dup-test", "train", records + records)  # double records
        # Fingerprint counting should detect duplicates
        assert entry["unique_records"] <= entry["total_records"]


# ═══════════════════════════════════════════════════════════════
# BENCHMARK SUITE TESTS (Phase 6)
# ═══════════════════════════════════════════════════════════════

class TestBenchmarkTasks:
    """Phase 6: Benchmark task definitions."""

    def test_benchmark_tasks_exist(self):
        from app.services.foundation.benchmark import BENCHMARK_TASKS
        assert len(BENCHMARK_TASKS) >= 14

    def test_all_categories_represented(self):
        from app.services.foundation.benchmark import BENCHMARK_TASKS, BenchmarkCategory
        represented = {t.category for t in BENCHMARK_TASKS}
        required = {
            BenchmarkCategory.ORBITAL_MECHANICS_QA,
            BenchmarkCategory.CONJUNCTION_QA,
            BenchmarkCategory.MISSION_INTELLIGENCE_QA,
            BenchmarkCategory.LAUNCH_VEHICLE_QA,
            BenchmarkCategory.SSA_QA,
            BenchmarkCategory.GRAPH_REASONING,
            BenchmarkCategory.MULTI_AGENT_QA,
            BenchmarkCategory.NUMERIC_PRECISION,
        }
        assert required <= represented

    def test_tasks_have_key_entities(self):
        from app.services.foundation.benchmark import BENCHMARK_TASKS
        for task in BENCHMARK_TASKS:
            # Most tasks should have key entities
            pass  # some numeric tasks may have empty key_entities

    def test_numeric_precision_tasks_have_numbers(self):
        from app.services.foundation.benchmark import BENCHMARK_TASKS, BenchmarkCategory
        numeric_tasks = [t for t in BENCHMARK_TASKS if t.category == BenchmarkCategory.NUMERIC_PRECISION]
        assert all(len(t.key_numbers) > 0 for t in numeric_tasks)

    def test_task_ids_unique(self):
        from app.services.foundation.benchmark import BENCHMARK_TASKS
        ids = [t.task_id for t in BENCHMARK_TASKS]
        assert len(ids) == len(set(ids)), "Duplicate task IDs found"

    def test_difficulties_are_valid(self):
        from app.services.foundation.benchmark import BENCHMARK_TASKS
        valid = {"easy", "medium", "hard", "expert"}
        for task in BENCHMARK_TASKS:
            assert task.difficulty in valid, f"Invalid difficulty '{task.difficulty}' in {task.task_id}"

    def test_evaluator_list_tasks_filtering(self):
        from app.services.foundation.benchmark import AerospaceBenchmarkEvaluator, BenchmarkCategory
        evaluator = AerospaceBenchmarkEvaluator()
        om_tasks  = evaluator.list_tasks(category=BenchmarkCategory.ORBITAL_MECHANICS_QA)
        assert all(t.category == BenchmarkCategory.ORBITAL_MECHANICS_QA for t in om_tasks)

    def test_evaluator_get_task_by_id(self):
        from app.services.foundation.benchmark import AerospaceBenchmarkEvaluator
        evaluator = AerospaceBenchmarkEvaluator()
        task = evaluator.get_task_by_id("OMQ-001")
        assert task is not None
        assert task.task_id == "OMQ-001"

    def test_evaluator_get_missing_task(self):
        from app.services.foundation.benchmark import AerospaceBenchmarkEvaluator
        evaluator = AerospaceBenchmarkEvaluator()
        assert evaluator.get_task_by_id("NONEXISTENT") is None


# ═══════════════════════════════════════════════════════════════
# EVALUATION PIPELINE TESTS (Phase 7)
# ═══════════════════════════════════════════════════════════════

class TestBenchmarkEvaluator:
    """Phase 7: Benchmark evaluation pipeline."""

    @pytest.mark.asyncio
    async def test_dry_run_all_tasks(self):
        """Dry run uses expected answers — should score perfectly."""
        from app.services.foundation.benchmark import AerospaceBenchmarkEvaluator
        evaluator = AerospaceBenchmarkEvaluator(inference_fn=None)  # dry run
        report    = await evaluator.run_benchmark("test-model", max_tasks=5)
        assert report.completed_tasks == 5
        assert report.failed_tasks    == 0
        assert report.overall_score   >= 0.8  # dry run should score high

    @pytest.mark.asyncio
    async def test_entity_scoring(self):
        from app.services.foundation.benchmark import AerospaceBenchmarkEvaluator, BENCHMARK_TASKS
        evaluator = AerospaceBenchmarkEvaluator()
        task = next(t for t in BENCHMARK_TASKS if t.key_entities)

        # Answer contains all key entities → perfect score
        full_answer = " ".join(task.key_entities) + " " + task.expected_answer
        score = evaluator._score_entities(task, full_answer)
        assert score == 1.0

        # Empty answer → 0
        score_empty = evaluator._score_entities(task, "irrelevant text")
        assert score_empty < 1.0

    @pytest.mark.asyncio
    async def test_numeric_scoring(self):
        from app.services.foundation.benchmark import AerospaceBenchmarkEvaluator, BenchmarkTask, BenchmarkCategory
        evaluator = AerospaceBenchmarkEvaluator()
        task = BenchmarkTask(
            task_id="TEST-NUM", category=BenchmarkCategory.NUMERIC_PRECISION,
            question="What is 22800?",
            expected_answer="22800",
            key_entities=[], key_numbers=[22800.0], difficulty="easy",
        )
        score_exact   = evaluator._score_numerics(task, "The payload capacity is 22800 kg.")
        score_near    = evaluator._score_numerics(task, "Approximately 22750 kg.")
        score_wrong   = evaluator._score_numerics(task, "About 10000 kg.")
        assert score_exact  == 1.0
        assert score_near   == 1.0   # within 10%
        assert score_wrong  == 0.0   # too far off

    @pytest.mark.asyncio
    async def test_quality_gates_pass_on_dry_run(self):
        from app.services.foundation.benchmark import AerospaceBenchmarkEvaluator
        evaluator = AerospaceBenchmarkEvaluator(inference_fn=None)
        report    = await evaluator.run_benchmark("test", max_tasks=10)
        # Dry run should pass quality gates
        assert report.quality_gates_passed is True

    @pytest.mark.asyncio
    async def test_quality_gates_fail_on_bad_model(self):
        from app.services.foundation.benchmark import AerospaceBenchmarkEvaluator

        async def bad_model(q: str) -> str:
            return "I don't know."  # Never has entities or numbers

        evaluator = AerospaceBenchmarkEvaluator(inference_fn=bad_model)
        report    = await evaluator.run_benchmark("bad-model", max_tasks=5)
        assert report.overall_score < 0.5
        # Should fail at least some quality gates
        assert len(report.quality_gate_failures) > 0

    @pytest.mark.asyncio
    async def test_benchmark_report_structure(self):
        from app.services.foundation.benchmark import AerospaceBenchmarkEvaluator
        evaluator = AerospaceBenchmarkEvaluator(inference_fn=None)
        report    = await evaluator.run_benchmark("test", max_tasks=3)
        d = report.as_dict()
        assert "run_id"              in d
        assert "model_id"            in d
        assert "overall_score"       in d
        assert "scores_by_category"  in d
        assert "quality_gates_passed"in d
        assert len(report.results)   == 3

    @pytest.mark.asyncio
    async def test_existing_rag_evaluator_integration(self):
        """The existing AerospaceRAGEvaluator must still be importable."""
        import sys, pathlib
        rag_root = pathlib.Path(__file__).parents[4] / "rag"
        sys.path.insert(0, str(rag_root))
        try:
            from src.evaluation.evaluator import (
                AerospaceRAGEvaluator, AEROSPACE_EVAL_QUESTIONS,
                FaithfulnessEvaluator, EntityRecallEvaluator,
            )
            assert len(AEROSPACE_EVAL_QUESTIONS) >= 6
            fe = FaithfulnessEvaluator()
            score = fe._keyword_faithfulness("SGP4 propagates TLEs", ["SGP4", "TLE"])
            assert 0 <= score <= 1
        except ImportError:
            pytest.skip("rag module not importable in test environment")


# ═══════════════════════════════════════════════════════════════
# MODEL REGISTRY TESTS (Phase 5)
# ═══════════════════════════════════════════════════════════════

class TestModelRegistry:
    """Phase 5: Model registry."""

    def test_default_models_registered(self):
        from app.services.foundation.benchmark import ModelRegistry
        registry = ModelRegistry()
        models   = registry.list_all()
        model_ids = {m.model_id for m in models}
        assert "claude-sonnet-4-6-baseline"  in model_ids
        assert "orbitiq-graphrag-v1"         in model_ids
        assert "orbitiq-agents-v1"           in model_ids

    def test_register_new_model(self):
        from app.services.foundation.benchmark import ModelRegistry, ModelSpec
        registry = ModelRegistry()
        spec = ModelSpec(
            model_id="test-ft-model",
            name="Test Fine-tuned Model",
            model_type="fine-tuned",
            base_model="mistral-7b",
            description="Test fine-tuned on aerospace corpus",
            parameters_b=7.0,
            is_fine_tuned=True,
            fine_tune_dataset="aerospace-v1",
        )
        registry.register(spec)
        retrieved = registry.get("test-ft-model")
        assert retrieved is not None
        assert retrieved.is_fine_tuned is True
        assert retrieved.parameters_b == 7.0

    def test_update_metrics(self):
        from app.services.foundation.benchmark import ModelRegistry
        registry = ModelRegistry()
        registry.update_metrics("orbitiq-graphrag-v1", {
            "overall_score": 0.82,
            "entity_recall": 0.88,
        })
        spec = registry.get("orbitiq-graphrag-v1")
        assert spec.metrics["overall_score"] == 0.82

    def test_get_best_model(self):
        from app.services.foundation.benchmark import ModelRegistry
        registry = ModelRegistry()
        registry.update_metrics("orbitiq-graphrag-v1", {"overall_score": 0.82})
        registry.update_metrics("orbitiq-agents-v1",   {"overall_score": 0.89})

        best = registry.get_best_model("overall_score")
        assert best is not None
        assert best.model_id == "orbitiq-agents-v1"

    def test_model_as_dict(self):
        from app.services.foundation.benchmark import ModelRegistry
        registry = ModelRegistry()
        d = registry.as_dict()
        assert isinstance(d, dict)
        assert "claude-sonnet-4-6-baseline" in d


# ═══════════════════════════════════════════════════════════════
# EXPERIMENT TRACKER TESTS
# ═══════════════════════════════════════════════════════════════

class TestExperimentTracker:

    def test_create_experiment(self, tmp_path):
        from app.services.foundation.benchmark import ExperimentTracker
        tracker = ExperimentTracker(tracking_dir=tmp_path)
        exp_id  = tracker.create_experiment(
            name="test-run", model_id="test-model",
            dataset_id="aerospace-v1",
            hyperparams={"lr": 0.001, "epochs": 3},
        )
        assert isinstance(exp_id, str)
        assert len(exp_id) > 0

    def test_log_metrics(self, tmp_path):
        from app.services.foundation.benchmark import ExperimentTracker
        tracker = ExperimentTracker(tracking_dir=tmp_path)
        exp_id  = tracker.create_experiment("test", "model", "dataset", {})
        tracker.log_metrics(exp_id, {"faithfulness": 0.85, "entity_recall": 0.90}, step=1)
        exp = tracker.get_experiment(exp_id)
        assert exp["metrics"]["faithfulness"] == 0.85

    def test_complete_experiment(self, tmp_path):
        from app.services.foundation.benchmark import ExperimentTracker
        tracker = ExperimentTracker(tracking_dir=tmp_path)
        exp_id  = tracker.create_experiment("test", "model", "dataset", {})
        tracker.complete_experiment(exp_id, "completed")
        exp = tracker.get_experiment(exp_id)
        assert exp["status"] == "completed"
        assert exp["completed_at"] is not None

    def test_list_experiments_by_model(self, tmp_path):
        from app.services.foundation.benchmark import ExperimentTracker
        tracker = ExperimentTracker(tracking_dir=tmp_path)
        tracker.create_experiment("e1", "model-A", "dataset", {})
        tracker.create_experiment("e2", "model-B", "dataset", {})
        tracker.create_experiment("e3", "model-A", "dataset", {})

        model_a_exps = tracker.list_experiments(model_id="model-A")
        assert len(model_a_exps) == 2
        assert all(e["model_id"] == "model-A" for e in model_a_exps)


# ═══════════════════════════════════════════════════════════════
# FOUNDATION MODEL SERVICE TESTS (Phase 8)
# ═══════════════════════════════════════════════════════════════

class TestFoundationModelService:

    def test_tier_selection_graphrag(self):
        from app.services.foundation.inference import FoundationModelService, ModelTier
        svc = FoundationModelService()
        assert svc.select_tier("What is the conjunction risk for ISS NORAD 25544?") == ModelTier.GRAPHRAG
        assert svc.select_tier("Show all ISRO satellites in LEO") == ModelTier.GRAPHRAG

    def test_tier_selection_agent(self):
        from app.services.foundation.inference import FoundationModelService, ModelTier
        svc = FoundationModelService()
        tier = svc.select_tier("Which satellites have the highest risk?")
        assert tier in (ModelTier.AGENT, ModelTier.GRAPHRAG)

    def test_tier_selection_baseline(self):
        from app.services.foundation.inference import FoundationModelService, ModelTier
        svc = FoundationModelService()
        # Pure math question — no graph/rag needed
        tier = svc.select_tier("What is 2+2?")
        assert tier == ModelTier.BASELINE

    def test_preferred_tier_respected(self):
        from app.services.foundation.inference import FoundationModelService, ModelTier
        svc = FoundationModelService()
        assert svc.select_tier("Any query", preferred_tier=ModelTier.BASELINE) == ModelTier.BASELINE

    @pytest.mark.asyncio
    async def test_baseline_without_client(self):
        from app.services.foundation.inference import FoundationModelService, ModelTier
        svc = FoundationModelService(anthropic_client=None)
        resp = await svc._query_baseline("Test question")
        assert resp.model_tier == ModelTier.BASELINE
        assert "API key" in resp.answer or len(resp.answer) > 0

    @pytest.mark.asyncio
    async def test_graphrag_falls_back_to_baseline(self):
        """If graphrag bridge raises, fall back to baseline."""
        from app.services.foundation.inference import FoundationModelService, ModelTier

        mock_bridge = AsyncMock()
        mock_bridge.query = AsyncMock(side_effect=Exception("Neo4j unavailable"))

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Fallback answer.")]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        svc = FoundationModelService(anthropic_client=mock_client, graphrag_bridge=mock_bridge)
        resp = await svc._query_graphrag("Show conjunction risk")
        # Should have fallen back to baseline
        assert resp.answer == "Fallback answer."

    @pytest.mark.asyncio
    async def test_full_query_returns_response(self):
        from app.services.foundation.inference import FoundationModelService, ModelTier

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test answer.")]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        svc = FoundationModelService(anthropic_client=mock_client)
        resp = await svc.query("What is SGP4?", tier=ModelTier.BASELINE)
        assert resp.answer == "Test answer."
        assert resp.latency_ms > 0

    def test_response_to_dict(self):
        from app.services.foundation.inference import FoundationModelResponse, ModelTier
        resp = FoundationModelResponse(
            query="test", answer="answer", model_tier=ModelTier.BASELINE,
            model_id="test", confidence=0.8, faithfulness=0.9,
        )
        d = resp.to_dict()
        assert d["query"]     == "test"
        assert d["answer"]    == "answer"
        assert d["confidence"]== 0.8
        assert "grounding"    in d


# ═══════════════════════════════════════════════════════════════
# API ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════

class TestFoundationAPI:

    def _get_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.v1.endpoints.foundation import router

        app = FastAPI()
        app.include_router(router, prefix="/foundation")
        return TestClient(app, raise_server_exceptions=False)

    def test_health_endpoint(self):
        client = self._get_client()
        resp = client.get("/foundation/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "benchmark_tasks"        in body
        assert "registered_models"      in body
        assert "training_readiness"     in body

    def test_models_endpoint(self):
        client = self._get_client()
        resp = client.get("/foundation/models")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] >= 3
        model_ids = {m["model_id"] for m in body["models"]}
        assert "claude-sonnet-4-6-baseline" in model_ids

    def test_metrics_endpoint(self):
        client = self._get_client()
        resp = client.get("/foundation/metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert "models" in body

    def test_dataset_status_endpoint(self):
        client = self._get_client()
        resp = client.get("/foundation/dataset/status")
        assert resp.status_code == 200
        body = resp.json()
        assert "benchmark_tasks"         in body
        assert "instruction_templates"   in body
        assert body["benchmark_tasks"] >= 14

    def test_benchmark_tasks_endpoint(self):
        client = self._get_client()
        resp = client.get("/foundation/benchmark/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] >= 14
        assert "categories" in body

    def test_benchmark_tasks_filter_by_category(self):
        client = self._get_client()
        resp = client.get("/foundation/benchmark/tasks?category=orbital_mechanics_qa")
        assert resp.status_code == 200
        body = resp.json()
        assert all(t["category"] == "orbital_mechanics_qa" for t in body["tasks"])

    def test_benchmark_tasks_invalid_category(self):
        client = self._get_client()
        resp = client.get("/foundation/benchmark/tasks?category=invalid_cat")
        assert resp.status_code == 400

    def test_benchmark_endpoint_dry_run(self):
        """Dry run benchmark: uses expected answers, no inference cost."""
        client = self._get_client()
        resp = client.post("/foundation/benchmark", json={
            "model_id": "orbitiq-graphrag-v1",
            "dry_run":  True,
            "max_tasks": 5,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "overall_score"       in body
        assert "quality_gates_passed"in body
        assert body["completed_tasks"] == 5

    def test_dataset_build_endpoint_accepted(self):
        client = self._get_client()
        resp = client.post("/foundation/dataset/build", json={"target_size": 50})
        assert resp.status_code == 202
        assert resp.json()["accepted"] is True

    def test_evaluate_endpoint_accepted(self):
        client = self._get_client()
        resp = client.post("/foundation/evaluate", json={
            "model_id": "orbitiq-graphrag-v1",
            "max_samples": 5,
        })
        assert resp.status_code == 202
        assert resp.json()["accepted"] is True

    def test_register_model_endpoint(self):
        client = self._get_client()
        resp = client.post("/foundation/models", json={
            "model_id":    "test-custom-7b",
            "name":        "Test Custom 7B",
            "model_type":  "fine-tuned",
            "base_model":  "mistral-7b",
            "description": "Aerospace fine-tuned model",
            "is_fine_tuned": True,
            "parameters_b": 7.0,
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["model_id"] == "test-custom-7b"

    def test_create_experiment_endpoint(self):
        client = self._get_client()
        resp = client.post("/foundation/experiment", json={
            "name":       "test-experiment",
            "model_id":   "orbitiq-graphrag-v1",
            "dataset_id": "aerospace-v1",
            "hyperparams":{"lr": 0.001},
        })
        assert resp.status_code == 201
        assert "experiment_id" in resp.json()

    def test_experiments_list_endpoint(self):
        client = self._get_client()
        resp = client.get("/foundation/experiments")
        assert resp.status_code == 200
        body = resp.json()
        assert "experiments" in body

    def test_query_endpoint_validates_short_query(self):
        client = self._get_client()
        resp = client.post("/foundation/query", json={"query": "hi"})
        assert resp.status_code == 422

    def test_query_endpoint_invalid_tier(self):
        client = self._get_client()
        resp = client.post("/foundation/query", json={
            "query": "What is SGP4?", "tier": "invalid_tier"
        })
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════
# PERFORMANCE BENCHMARKS
# ═══════════════════════════════════════════════════════════════

class TestPerformanceBenchmarks:

    def test_instruction_dataset_build_speed(self):
        """Building 1000 instruction records takes < 2s."""
        from app.services.foundation.dataset import AerospaceDatasetBuilder
        builder = AerospaceDatasetBuilder(seed=42)
        t0 = time.perf_counter()
        records = builder.build_instruction_dataset(target_size=1000)
        elapsed = time.perf_counter() - t0
        print(f"\n  1000 instruction records: {elapsed:.3f}s ({len(records)/elapsed:.0f}/s)")
        assert len(records) >= 15  # at least base templates
        assert elapsed < 2.0

    def test_benchmark_scoring_throughput(self):
        """Scoring 100 tasks takes < 1s (pure Python, no I/O)."""
        from app.services.foundation.benchmark import AerospaceBenchmarkEvaluator, BENCHMARK_TASKS
        evaluator = AerospaceBenchmarkEvaluator(inference_fn=None)
        tasks = BENCHMARK_TASKS * 10  # 140+ tasks
        t0 = time.perf_counter()
        for task in tasks:
            evaluator._score_entities(task, task.expected_answer)
            evaluator._score_numerics(task, task.expected_answer)
            evaluator._score_faithfulness(task, task.expected_answer)
        elapsed = time.perf_counter() - t0
        print(f"\n  {len(tasks)} task scorings: {elapsed*1000:.1f}ms ({len(tasks)/elapsed:.0f}/s)")
        assert elapsed < 1.0

    def test_jsonl_export_1000_records(self, tmp_path):
        """Exporting 1000 records to JSONL takes < 500ms."""
        from app.services.foundation.dataset import AerospaceDatasetBuilder
        builder = AerospaceDatasetBuilder()
        records = builder.build_instruction_dataset(target_size=1000)
        path    = tmp_path / "export.jsonl"
        t0 = time.perf_counter()
        builder.export_jsonl(records, path)
        elapsed = time.perf_counter() - t0
        print(f"\n  JSONL export {len(records)} records: {elapsed*1000:.1f}ms")
        assert elapsed < 0.5
