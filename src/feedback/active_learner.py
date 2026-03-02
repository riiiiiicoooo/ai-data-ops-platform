"""
Active Learner: Intelligent sample selection for maximum model improvement.

Selects the most informative unlabeled examples for annotation using
uncertainty sampling, margin sampling, and committee disagreement.
Uses a 70/30 active learning / random split to balance information
gain with distribution coverage (DEC-005).

Key design decisions:
- 70/30 AL/random split prevents sampling bias collapse (DEC-005)
- Budget allocation: highest-uncertainty items labeled by top annotators
- Efficiency tracking: labels-to-improvement ratio per batch
- Random component prevents blindness to distribution shifts

PM context: Ran a controlled experiment comparing pure active learning
vs. 70/30 split. Pure AL outperformed at Week 2 but degraded at Week 8
after a production data shift, because the model had no labels in the
shifted region. The 30% random component costs ~$1,800/year in
"suboptimal" labels but prevented a model accuracy regression that
would have cost 10x that in debugging and retraining.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4


@dataclass
class CandidateItem:
    """Unlabeled item with model prediction metadata."""
    item_id: UUID
    data_reference: str
    input_data: dict[str, Any] = field(default_factory=dict)
    prediction: Optional[str] = None
    prediction_probabilities: dict[str, float] = field(default_factory=dict)
    prediction_entropy: float = 0.0
    margin: float = 1.0
    embedding: Optional[list[float]] = None


@dataclass
class SelectionBatch:
    """Result of active learning selection."""
    batch_id: UUID
    project_id: UUID
    strategy: str
    budget: int
    active_learning_items: list[CandidateItem]
    random_items: list[CandidateItem]
    uncertainty_stats: dict[str, float]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EfficiencyMetrics:
    """Post-training evaluation of active learning batch."""
    batch_id: UUID
    baseline_metric: float
    retrained_metric: float
    improvement: float
    random_baseline_improvement: float
    efficiency_ratio: float
    labels_used: int
    cost_per_improvement_point: float


class ActiveLearner:
    """
    Selects high-value items for annotation from unlabeled pools.

    Three sampling strategies:

    1. Uncertainty sampling: select items where model prediction
       entropy is highest. These are items the model is confused about.

    2. Margin sampling: select items where the top-2 predicted class
       probabilities are closest. These are decision-boundary items.

    3. Committee disagreement: run multiple models, select items where
       they disagree most. Requires multiple model endpoints.

    All strategies use the 70/30 split (DEC-005):
    - 70% selected by active learning strategy
    - 30% selected randomly for distribution coverage
    """

    DEFAULT_AL_RATIO = 0.70
    DEFAULT_RANDOM_RATIO = 0.30

    def __init__(self, al_ratio: float = 0.70, random_ratio: float = 0.30):
        self.al_ratio = al_ratio
        self.random_ratio = random_ratio
        self.selection_history: list[SelectionBatch] = []
        self.efficiency_history: list[EfficiencyMetrics] = []

    def select_batch(
        self,
        candidates: list[CandidateItem],
        budget: int,
        strategy: str = "uncertainty",
        project_id: Optional[UUID] = None,
    ) -> SelectionBatch:
        """
        Select a batch of items for annotation.

        Splits budget into AL portion (scored by strategy) and random
        portion (uniform sample from remaining pool).
        """
        if not candidates:
            return SelectionBatch(
                batch_id=uuid4(), project_id=project_id or uuid4(),
                strategy=strategy, budget=0,
                active_learning_items=[], random_items=[],
                uncertainty_stats={},
            )

        al_count = int(budget * self.al_ratio)
        random_count = budget - al_count

        # Score candidates by strategy
        if strategy == "margin":
            scored = self._score_by_margin(candidates)
        else:
            scored = self._score_by_uncertainty(candidates)

        scored.sort(key=lambda x: x[1], reverse=True)
        al_items = [item for item, _ in scored[:al_count]]

        remaining = [item for item, _ in scored[al_count:]]
        random_count = min(random_count, len(remaining))
        random_items = random.sample(remaining, random_count) if remaining else []

        # Compute stats
        all_ent = sorted([c.prediction_entropy for c in candidates if c.prediction_entropy > 0])
        al_ent = [i.prediction_entropy for i in al_items if i.prediction_entropy > 0]

        stats = {"pool_size": len(candidates)}
        if all_ent:
            stats["pool_entropy_mean"] = round(sum(all_ent) / len(all_ent), 4)
            stats["pool_entropy_p50"] = round(all_ent[len(all_ent) // 2], 4)
            stats["pool_entropy_p95"] = round(all_ent[int(len(all_ent) * 0.95)], 4)
        if al_ent:
            stats["selected_entropy_mean"] = round(sum(al_ent) / len(al_ent), 4)

        batch = SelectionBatch(
            batch_id=uuid4(),
            project_id=project_id or uuid4(),
            strategy=strategy, budget=budget,
            active_learning_items=al_items,
            random_items=random_items,
            uncertainty_stats=stats,
        )
        self.selection_history.append(batch)
        return batch

    def _score_by_uncertainty(self, candidates: list[CandidateItem]) -> list[tuple[CandidateItem, float]]:
        """Score by prediction entropy (higher = more informative)."""
        scored = []
        for c in candidates:
            entropy = c.prediction_entropy
            if entropy == 0 and c.prediction_probabilities:
                entropy = self._compute_entropy(c.prediction_probabilities)
                c.prediction_entropy = entropy
            scored.append((c, entropy))
        return scored

    def _score_by_margin(self, candidates: list[CandidateItem]) -> list[tuple[CandidateItem, float]]:
        """Score by margin (inverted: small margin = high score)."""
        scored = []
        for c in candidates:
            margin = c.margin
            if margin == 1.0 and c.prediction_probabilities:
                probs = sorted(c.prediction_probabilities.values(), reverse=True)
                margin = (probs[0] - probs[1]) if len(probs) >= 2 else 1.0
                c.margin = margin
            scored.append((c, 1.0 - margin))
        return scored

    def _compute_entropy(self, probabilities: dict[str, float]) -> float:
        """Shannon entropy from class probabilities."""
        return -sum(p * math.log2(p) for p in probabilities.values() if p > 0)

    def record_efficiency(
        self,
        batch_id: UUID,
        baseline_metric: float,
        retrained_metric: float,
        random_baseline_improvement: float,
        labels_used: int,
        cost_per_label: float = 0.12,
    ) -> EfficiencyMetrics:
        """
        Record post-training evaluation of an active learning batch.

        The efficiency_ratio should be > 1.0 (ideally 2-3x).
        If it drops below 1.5, the sampling strategy may need tuning.
        """
        improvement = retrained_metric - baseline_metric
        efficiency_ratio = (
            improvement / random_baseline_improvement
            if random_baseline_improvement > 0 else float("inf")
        )
        total_cost = labels_used * cost_per_label
        cost_per_point = total_cost / improvement if improvement > 0 else float("inf")

        metrics = EfficiencyMetrics(
            batch_id=batch_id,
            baseline_metric=round(baseline_metric, 4),
            retrained_metric=round(retrained_metric, 4),
            improvement=round(improvement, 4),
            random_baseline_improvement=round(random_baseline_improvement, 4),
            efficiency_ratio=round(efficiency_ratio, 2),
            labels_used=labels_used,
            cost_per_improvement_point=round(cost_per_point, 2),
        )
        self.efficiency_history.append(metrics)
        return metrics

    def get_efficiency_summary(self) -> dict[str, Any]:
        """Summarize active learning efficiency across all batches."""
        if not self.efficiency_history:
            return {"batches": 0}

        ratios = [m.efficiency_ratio for m in self.efficiency_history if m.efficiency_ratio < float("inf")]
        return {
            "batches": len(self.efficiency_history),
            "avg_efficiency_ratio": round(sum(ratios) / len(ratios), 2) if ratios else 0,
            "total_improvement": round(sum(m.improvement for m in self.efficiency_history), 4),
            "total_labels": sum(m.labels_used for m in self.efficiency_history),
            "al_ratio": self.al_ratio,
            "random_ratio": self.random_ratio,
        }

    def recommend_budget(
        self,
        target_improvement: float,
        current_efficiency_ratio: float = 2.4,
        cost_per_label: float = 0.12,
    ) -> dict[str, Any]:
        """Estimate annotation budget needed for target model improvement."""
        random_labels_per_point = 12500 / 0.03
        random_labels = int(random_labels_per_point * target_improvement)
        al_labels = int(random_labels / current_efficiency_ratio)

        return {
            "target_improvement": target_improvement,
            "random_labels_needed": random_labels,
            "al_labels_needed": al_labels,
            "random_cost": round(random_labels * cost_per_label, 2),
            "al_cost": round(al_labels * cost_per_label, 2),
            "savings": round((random_labels - al_labels) * cost_per_label, 2),
            "efficiency_ratio_used": current_efficiency_ratio,
        }


if __name__ == "__main__":
    learner = ActiveLearner()

    print("=== Active Learner Demo ===\n")

    candidates = []
    for i in range(1000):
        entropy = random.betavariate(2, 5)
        probs = {"class_a": 0.5 + entropy * 0.3, "class_b": 0.5 - entropy * 0.3}
        candidates.append(CandidateItem(
            item_id=uuid4(), data_reference=f"s3://data/item_{i}.json",
            prediction_probabilities=probs, prediction_entropy=entropy,
            margin=abs(probs["class_a"] - probs["class_b"]),
        ))

    batch = learner.select_batch(candidates, budget=100, strategy="uncertainty", project_id=uuid4())
    print(f"Selected {len(batch.active_learning_items)} AL + {len(batch.random_items)} random")
    print(f"Stats: {batch.uncertainty_stats}")

    metrics = learner.record_efficiency(
        batch.batch_id, baseline_metric=0.84, retrained_metric=0.87,
        random_baseline_improvement=0.012, labels_used=100,
    )
    print(f"\nEfficiency: {metrics.efficiency_ratio}x vs random")

    rec = learner.recommend_budget(target_improvement=0.03)
    print(f"Budget for +0.03 F1: {rec['al_labels_needed']} labels (${rec['al_cost']}) vs random {rec['random_labels_needed']} (${rec['random_cost']})")
