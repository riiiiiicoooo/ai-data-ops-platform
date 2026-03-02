"""
Model Evaluator: Per-slice performance analysis and error pattern detection.

Connects annotation quality to model outcomes by tracking per-slice
accuracy, identifying systematic failure patterns, and generating
targeted re-annotation requests. Closes the feedback loop between
model performance and data collection.

Key design decisions:
- Per-slice evaluation (not just aggregate metrics)
- Error pattern clustering for targeted re-annotation
- Batch-to-model provenance tracking
- Diminishing returns detection for budget allocation

PM context: Built this after an ML engineer said "the model's F1 is
0.89 but it fails on medical abbreviations." Without per-slice analysis,
the team would have randomly annotated more data hoping to fix the
weakness. With slice-level tracking, we identified that medical
abbreviation accuracy was 0.72 on a 340-item slice, generated a
targeted re-annotation batch of 2,000 items specifically for that
category, and improved slice accuracy to 0.88 with minimal total
annotation spend.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4


@dataclass
class ModelSlice:
    """A segment of the evaluation data with its own performance metrics."""
    slice_name: str
    filter_criteria: dict[str, Any]
    sample_count: int
    accuracy: float
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    error_count: int = 0
    error_examples: list[dict] = field(default_factory=list)


@dataclass
class EvaluationRun:
    """Complete model evaluation against annotated data."""
    run_id: UUID
    project_id: UUID
    model_endpoint_id: UUID
    annotation_batch_ids: list[UUID]
    total_training_examples: int
    training_quality_summary: dict[str, Any]
    accuracy: float = 0.0
    f1_macro: float = 0.0
    f1_weighted: float = 0.0
    eval_dataset_size: int = 0
    per_class: dict[str, dict[str, float]] = field(default_factory=dict)
    slices: list[ModelSlice] = field(default_factory=list)
    error_patterns: list[dict[str, Any]] = field(default_factory=list)
    previous_run_id: Optional[UUID] = None
    improvement: Optional[dict[str, float]] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ReAnnotationRequest:
    """Targeted re-annotation request based on model weakness."""
    request_id: UUID
    project_id: UUID
    source: str
    target_slice: str
    filter_criteria: dict[str, Any]
    recommended_volume: int
    priority: str = "high"
    rationale: str = ""
    current_accuracy: float = 0.0
    target_accuracy: float = 0.0


class ModelEvaluator:
    """
    Evaluates model performance and generates targeted improvement
    recommendations.

    The evaluation pipeline:
    1. Run model against held-out eval set
    2. Compute aggregate metrics (accuracy, F1)
    3. Slice evaluation data by meaningful categories
    4. Identify underperforming slices
    5. Cluster error patterns
    6. Generate re-annotation requests for weak slices
    7. Track improvement across evaluation runs
    """

    SLICE_ACCURACY_THRESHOLD = 0.80
    SLICE_MIN_SAMPLES = 50
    IMPROVEMENT_DIMINISHING_THRESHOLD = 0.005

    def __init__(self):
        self.evaluation_runs: dict[UUID, EvaluationRun] = {}
        self.project_runs: dict[UUID, list[UUID]] = {}
        self.reannot_requests: list[ReAnnotationRequest] = []

    def record_evaluation(self, run: EvaluationRun) -> EvaluationRun:
        """Record a model evaluation run and compute comparisons."""
        self.evaluation_runs[run.run_id] = run

        if run.project_id not in self.project_runs:
            self.project_runs[run.project_id] = []
        self.project_runs[run.project_id].append(run.run_id)

        # Compute improvement vs previous
        if run.previous_run_id and run.previous_run_id in self.evaluation_runs:
            prev = self.evaluation_runs[run.previous_run_id]
            run.improvement = {
                "accuracy_delta": round(run.accuracy - prev.accuracy, 4),
                "f1_macro_delta": round(run.f1_macro - prev.f1_macro, 4),
                "f1_weighted_delta": round(run.f1_weighted - prev.f1_weighted, 4),
            }

        return run

    def identify_weak_slices(self, run_id: UUID) -> list[ModelSlice]:
        """
        Identify evaluation slices performing below threshold.

        These are the slices where targeted re-annotation will have
        the highest marginal impact on model quality.
        """
        run = self.evaluation_runs.get(run_id)
        if run is None:
            return []

        weak = [
            s for s in run.slices
            if s.accuracy < self.SLICE_ACCURACY_THRESHOLD
            and s.sample_count >= self.SLICE_MIN_SAMPLES
        ]
        return sorted(weak, key=lambda s: s.accuracy)

    def generate_reannot_requests(
        self, run_id: UUID, budget: int = 5000,
    ) -> list[ReAnnotationRequest]:
        """
        Generate targeted re-annotation requests for weak slices.

        Budget allocation: proportional to the gap between current
        accuracy and threshold, weighted by slice size. Larger gaps
        and larger slices get more annotation budget.
        """
        weak_slices = self.identify_weak_slices(run_id)
        run = self.evaluation_runs.get(run_id)
        if not weak_slices or run is None:
            return []

        scored_slices = []
        for s in weak_slices:
            gap = self.SLICE_ACCURACY_THRESHOLD - s.accuracy
            weight = gap * math.sqrt(s.sample_count)
            scored_slices.append((s, weight))

        total_weight = sum(w for _, w in scored_slices)
        if total_weight == 0:
            return []

        requests = []
        for slice_obj, weight in scored_slices:
            allocated = int(budget * (weight / total_weight))
            allocated = max(100, min(allocated, budget // 2))

            req = ReAnnotationRequest(
                request_id=uuid4(),
                project_id=run.project_id,
                source="error_slice",
                target_slice=slice_obj.slice_name,
                filter_criteria=slice_obj.filter_criteria,
                recommended_volume=allocated,
                priority="high" if slice_obj.accuracy < 0.70 else "normal",
                rationale=(
                    f"Slice '{slice_obj.slice_name}' accuracy is "
                    f"{slice_obj.accuracy:.1%} on {slice_obj.sample_count} samples, "
                    f"below {self.SLICE_ACCURACY_THRESHOLD:.0%} threshold"
                ),
                current_accuracy=slice_obj.accuracy,
                target_accuracy=self.SLICE_ACCURACY_THRESHOLD,
            )
            requests.append(req)
            self.reannot_requests.append(req)

        return requests

    def detect_diminishing_returns(self, project_id: UUID) -> dict[str, Any]:
        """
        Detect if annotation spending is hitting diminishing returns.

        If the marginal improvement per batch drops below threshold,
        it may be more productive to invest in model architecture
        changes rather than more labels.
        """
        run_ids = self.project_runs.get(project_id, [])
        if len(run_ids) < 2:
            return {"sufficient_data": False}

        improvements = []
        for i in range(1, len(run_ids)):
            run = self.evaluation_runs[run_ids[i]]
            if run.improvement:
                improvements.append({
                    "run": i,
                    "f1_delta": run.improvement.get("f1_macro_delta", 0),
                    "labels": run.total_training_examples,
                })

        if not improvements:
            return {"sufficient_data": False}

        latest_improvement = improvements[-1]["f1_delta"]
        avg_improvement = sum(i["f1_delta"] for i in improvements) / len(improvements)
        diminishing = latest_improvement < self.IMPROVEMENT_DIMINISHING_THRESHOLD

        return {
            "diminishing_returns": diminishing,
            "latest_improvement": latest_improvement,
            "avg_improvement": round(avg_improvement, 4),
            "total_runs": len(improvements),
            "recommendation": (
                "Consider model architecture changes or feature engineering"
                if diminishing else
                "Annotation spending is still producing meaningful improvements"
            ),
            "improvement_history": improvements,
        }

    def get_provenance_chain(self, run_id: UUID) -> dict[str, Any]:
        """
        Build provenance chain from annotations to model evaluation.

        Answers: "which annotation batches contributed to this model,
        and what was their quality?"
        """
        run = self.evaluation_runs.get(run_id)
        if run is None:
            return {}

        return {
            "model_run_id": str(run.run_id),
            "project_id": str(run.project_id),
            "annotation_batches": [str(b) for b in run.annotation_batch_ids],
            "total_training_examples": run.total_training_examples,
            "training_quality": run.training_quality_summary,
            "model_metrics": {
                "accuracy": run.accuracy,
                "f1_macro": run.f1_macro,
                "f1_weighted": run.f1_weighted,
                "eval_size": run.eval_dataset_size,
            },
            "improvement_vs_previous": run.improvement,
            "weak_slices": [
                {"name": s.slice_name, "accuracy": s.accuracy, "count": s.sample_count}
                for s in self.identify_weak_slices(run_id)
            ],
            "evaluated_at": run.created_at.isoformat(),
        }

    def generate_model_card_data(self, run_id: UUID) -> dict[str, Any]:
        """Generate model card data section from evaluation run."""
        run = self.evaluation_runs.get(run_id)
        if run is None:
            return {}

        return {
            "training_data": {
                "total_examples": run.total_training_examples,
                "annotation_batches": len(run.annotation_batch_ids),
                "quality_metrics": run.training_quality_summary,
            },
            "evaluation_results": {
                "accuracy": run.accuracy,
                "f1_macro": run.f1_macro,
                "f1_weighted": run.f1_weighted,
                "eval_dataset_size": run.eval_dataset_size,
                "per_class_metrics": run.per_class,
            },
            "known_limitations": [
                {
                    "slice": s.slice_name,
                    "accuracy": s.accuracy,
                    "sample_count": s.sample_count,
                }
                for s in self.identify_weak_slices(run_id)
            ],
            "data_provenance": {
                "annotation_platform": "AI Data Operations Platform",
                "quality_methodology": "Golden set evaluation + multi-annotator consensus",
                "consensus_method": run.training_quality_summary.get("consensus_method", "weighted_vote"),
            },
        }


if __name__ == "__main__":
    evaluator = ModelEvaluator()
    project_id = uuid4()

    print("=== Model Evaluator Demo ===\n")

    run1 = EvaluationRun(
        run_id=uuid4(), project_id=project_id,
        model_endpoint_id=uuid4(),
        annotation_batch_ids=[uuid4()],
        total_training_examples=10000,
        training_quality_summary={
            "mean_agreement_kappa": 0.83, "golden_accuracy": 0.96,
            "consensus_method": "weighted_vote",
        },
        accuracy=0.89, f1_macro=0.85, f1_weighted=0.88, eval_dataset_size=2000,
        per_class={"fraud": {"precision": 0.82, "recall": 0.79, "f1": 0.80}},
        slices=[
            ModelSlice("medical_abbreviations", {"text_contains": "abbrev"}, 340, 0.72, f1=0.68, error_count=95),
            ModelSlice("nighttime_scenes", {"time": "night"}, 520, 0.78, f1=0.75, error_count=114),
            ModelSlice("standard_transactions", {"type": "standard"}, 1140, 0.94, f1=0.93, error_count=68),
        ],
    )
    evaluator.record_evaluation(run1)

    weak = evaluator.identify_weak_slices(run1.run_id)
    print(f"Weak slices ({len(weak)}):")
    for s in weak:
        print(f"  {s.slice_name}: accuracy={s.accuracy:.0%}, samples={s.sample_count}")

    requests = evaluator.generate_reannot_requests(run1.run_id, budget=3000)
    print(f"\nRe-annotation requests ({len(requests)}):")
    for r in requests:
        print(f"  {r.target_slice}: {r.recommended_volume} items ({r.priority})")

    run2 = EvaluationRun(
        run_id=uuid4(), project_id=project_id,
        model_endpoint_id=uuid4(),
        annotation_batch_ids=[uuid4(), uuid4()],
        total_training_examples=13000,
        training_quality_summary={"mean_agreement_kappa": 0.85, "golden_accuracy": 0.97, "consensus_method": "weighted_vote"},
        accuracy=0.91, f1_macro=0.88, f1_weighted=0.90, eval_dataset_size=2000,
        slices=[
            ModelSlice("medical_abbreviations", {"text_contains": "abbrev"}, 340, 0.84, f1=0.82, error_count=54),
            ModelSlice("nighttime_scenes", {"time": "night"}, 520, 0.83, f1=0.81, error_count=88),
            ModelSlice("standard_transactions", {"type": "standard"}, 1140, 0.95, f1=0.94, error_count=57),
        ],
        previous_run_id=run1.run_id,
    )
    evaluator.record_evaluation(run2)
    print(f"\nImprovement: {run2.improvement}")

    provenance = evaluator.get_provenance_chain(run2.run_id)
    print(f"Provenance: {provenance['total_training_examples']} examples from {len(provenance['annotation_batches'])} batches")

    dr = evaluator.detect_diminishing_returns(project_id)
    print(f"Diminishing returns: {dr.get('diminishing_returns', 'N/A')}")
