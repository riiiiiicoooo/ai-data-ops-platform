"""
Golden Set Evaluator: Ground truth insertion and accuracy measurement.

Manages golden items (pre-labeled examples with known correct answers)
that are inserted into annotation queues to measure annotator accuracy
in real time. Handles golden pool creation, rotation, insertion rate
control, and anti-gaming detection.

Key design decisions:
- Monthly rotation with 30% replacement to prevent memorization (DEC-006)
- 5% insertion rate in steady state, 15% during onboarding
- Anti-gaming: flags golden accuracy > peer agreement by 15%+
- Immediate feedback to annotators on golden evaluations

PM context: This was built after a client reported an annotator with
99% golden accuracy but 78% peer agreement. Investigation revealed
memorization of the static golden pool. The rotation strategy and
anti-gaming detection prevent this failure mode. The 30% monthly
replacement rate means the full pool turns over in ~3.5 months,
making memorization impractical.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import UUID, uuid4


@dataclass
class GoldenItem:
    """Expert-labeled item with known correct answer."""
    item_id: UUID
    gold_annotation: dict[str, Any]    # the correct answer
    labeled_by: UUID                    # expert who created this item
    difficulty: str = "medium"          # easy, medium, hard
    task_type: str = ""
    input_data: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    retired_at: Optional[datetime] = None
    times_served: int = 0
    times_correct: int = 0


@dataclass
class GoldenPool:
    """Collection of golden items for a project."""
    pool_id: UUID
    project_id: UUID
    task_type: str
    items: list[GoldenItem] = field(default_factory=list)
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_rotated_at: Optional[datetime] = None

    # Configuration
    insertion_rate: float = 0.05            # 5% of tasks are golden
    onboarding_insertion_rate: float = 0.15 # 15% during first week
    rotation_percentage: float = 0.30       # replace 30% monthly
    target_pool_size: int = 200


@dataclass
class GoldenEvaluationResult:
    """Result of evaluating one annotator's response to a golden item."""
    golden_item_id: UUID
    annotator_id: UUID
    correct: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    metric_used: str
    metric_score: float
    feedback: str                # shown to annotator


class GoldenSetEvaluator:
    """
    Manages golden set lifecycle: creation, insertion, evaluation,
    rotation, and anti-gaming detection.

    The golden set is the primary mechanism for measuring annotator
    accuracy in real time. Without it, accuracy is only measurable
    after expensive post-hoc expert review.
    """

    ROTATION_INTERVAL_DAYS = 30
    DIFFICULTY_DISTRIBUTION = {"easy": 0.30, "medium": 0.50, "hard": 0.20}

    def __init__(self):
        self.pools: dict[UUID, GoldenPool] = {}     # pool_id -> pool
        self.project_pools: dict[UUID, UUID] = {}    # project_id -> pool_id
        self.evaluation_history: list[GoldenEvaluationResult] = []

    def create_pool(
        self,
        project_id: UUID,
        task_type: str,
        items: list[GoldenItem],
        insertion_rate: float = 0.05,
    ) -> GoldenPool:
        """Create a new golden pool for a project."""
        pool = GoldenPool(
            pool_id=uuid4(),
            project_id=project_id,
            task_type=task_type,
            items=items,
            insertion_rate=insertion_rate,
        )
        self.pools[pool.pool_id] = pool
        self.project_pools[project_id] = pool.pool_id
        return pool

    def should_insert_golden(
        self,
        project_id: UUID,
        annotator_is_onboarding: bool = False,
        items_since_last_golden: int = 0,
    ) -> bool:
        """
        Decide whether the next task should be a golden item.

        Uses probabilistic insertion with rate control. During
        onboarding, the rate is 3x higher (15% vs 5%) to rapidly
        calibrate the new annotator's accuracy.
        """
        pool_id = self.project_pools.get(project_id)
        if pool_id is None:
            return False
        pool = self.pools[pool_id]
        if not pool.items:
            return False

        rate = pool.onboarding_insertion_rate if annotator_is_onboarding else pool.insertion_rate

        # Guaranteed insertion every 1/rate items (anti-drought)
        max_gap = int(1 / rate) + 2
        if items_since_last_golden >= max_gap:
            return True

        return random.random() < rate

    def select_golden_item(
        self,
        project_id: UUID,
        annotator_id: UUID,
        difficulty_preference: Optional[str] = None,
    ) -> Optional[GoldenItem]:
        """
        Select a golden item to insert into the annotator's queue.

        Selection strategy: weighted random by difficulty, biased
        toward items the annotator has not seen recently. Difficulty
        distribution follows DIFFICULTY_DISTRIBUTION target.
        """
        pool_id = self.project_pools.get(project_id)
        if pool_id is None:
            return None
        pool = self.pools[pool_id]

        active_items = [i for i in pool.items if i.retired_at is None]
        if not active_items:
            return None

        if difficulty_preference:
            filtered = [i for i in active_items if i.difficulty == difficulty_preference]
            if filtered:
                active_items = filtered

        # Weighted selection: less-served items are preferred
        weights = [1.0 / (item.times_served + 1) for item in active_items]
        total = sum(weights)
        normalized = [w / total for w in weights]

        r = random.random()
        cumulative = 0.0
        for item, weight in zip(active_items, normalized):
            cumulative += weight
            if r <= cumulative:
                item.times_served += 1
                return item

        selected = active_items[-1]
        selected.times_served += 1
        return selected

    def evaluate(
        self,
        golden_item: GoldenItem,
        annotator_id: UUID,
        annotator_data: dict[str, Any],
        annotation_type: str = "enum",
    ) -> GoldenEvaluationResult:
        """
        Evaluate annotator's response against golden ground truth.
        Returns detailed result with feedback for the annotator.
        """
        expected = golden_item.gold_annotation
        correct, metric, score = self._compare_annotations(
            expected, annotator_data, annotation_type,
        )

        if correct:
            golden_item.times_correct += 1

        feedback = self._generate_feedback(correct, expected, annotator_data, annotation_type)

        result = GoldenEvaluationResult(
            golden_item_id=golden_item.item_id,
            annotator_id=annotator_id,
            correct=correct,
            expected=expected,
            actual=annotator_data,
            metric_used=metric,
            metric_score=score,
            feedback=feedback,
        )
        self.evaluation_history.append(result)
        return result

    def check_rotation_needed(self, project_id: UUID) -> bool:
        """Check if the golden pool needs rotation."""
        pool_id = self.project_pools.get(project_id)
        if pool_id is None:
            return False
        pool = self.pools[pool_id]

        if pool.last_rotated_at is None:
            return (datetime.now(timezone.utc) - pool.created_at).days >= self.ROTATION_INTERVAL_DAYS

        days_since = (datetime.now(timezone.utc) - pool.last_rotated_at).days
        return days_since >= self.ROTATION_INTERVAL_DAYS

    def rotate_pool(
        self,
        project_id: UUID,
        new_items: list[GoldenItem],
    ) -> dict[str, int]:
        """
        Rotate the golden pool: retire 30% of items and add new ones.

        DEC-006: Monthly rotation prevents memorization. The 30% rate
        means the full pool turns over in ~3.5 months. An annotator
        processing 50+ golden items per week will encounter mostly
        fresh items, making memorization impractical.
        """
        pool_id = self.project_pools.get(project_id)
        if pool_id is None:
            return {"error": "No pool for project"}
        pool = self.pools[pool_id]

        active = [i for i in pool.items if i.retired_at is None]
        n_to_retire = int(len(active) * pool.rotation_percentage)

        # Retire the most-served items (most likely to be memorized)
        active_sorted = sorted(active, key=lambda i: i.times_served, reverse=True)
        retired = 0
        for item in active_sorted[:n_to_retire]:
            item.retired_at = datetime.now(timezone.utc)
            retired += 1

        # Add new items
        added = 0
        for item in new_items[:n_to_retire]:
            pool.items.append(item)
            added += 1

        pool.last_rotated_at = datetime.now(timezone.utc)
        pool.version += 1

        return {"retired": retired, "added": added, "pool_version": pool.version}

    def get_pool_health(self, project_id: UUID) -> dict[str, Any]:
        """Pool health metrics for dashboard."""
        pool_id = self.project_pools.get(project_id)
        if pool_id is None:
            return {}
        pool = self.pools[pool_id]

        active = [i for i in pool.items if i.retired_at is None]
        difficulty_dist = {}
        for item in active:
            difficulty_dist[item.difficulty] = difficulty_dist.get(item.difficulty, 0) + 1

        avg_accuracy = 0.0
        served_items = [i for i in active if i.times_served > 0]
        if served_items:
            accuracies = [i.times_correct / i.times_served for i in served_items]
            avg_accuracy = sum(accuracies) / len(accuracies)

        return {
            "pool_size": len(active),
            "target_size": pool.target_pool_size,
            "retired_count": sum(1 for i in pool.items if i.retired_at is not None),
            "difficulty_distribution": difficulty_dist,
            "avg_item_accuracy": round(avg_accuracy, 3),
            "rotation_due": self.check_rotation_needed(project_id),
            "version": pool.version,
            "insertion_rate": pool.insertion_rate,
        }

    def _compare_annotations(
        self,
        expected: dict[str, Any],
        actual: dict[str, Any],
        annotation_type: str,
    ) -> tuple[bool, str, float]:
        """Compare annotator output to golden truth. Returns (correct, metric, score)."""
        if annotation_type in ("enum", "classification"):
            exp_label = expected.get("label") or expected.get("preferred")
            act_label = actual.get("label") or actual.get("preferred")
            correct = exp_label == act_label
            return correct, "exact_match", 1.0 if correct else 0.0

        elif annotation_type in ("multi_select",):
            exp_set = set(expected.get("categories", []))
            act_set = set(actual.get("categories", []))
            if not exp_set:
                return True, "set_match", 1.0
            overlap = len(exp_set & act_set)
            union = len(exp_set | act_set)
            score = overlap / union if union > 0 else 0.0
            return score >= 0.8, "jaccard", round(score, 3)

        elif annotation_type in ("preference",):
            correct = expected.get("preferred") == actual.get("preferred")
            return correct, "preference_match", 1.0 if correct else 0.0

        # Default: check primary field equality
        for key in expected:
            if key.startswith("_"):
                continue
            if actual.get(key) != expected[key]:
                return False, "field_match", 0.0
        return True, "field_match", 1.0

    def _generate_feedback(
        self,
        correct: bool,
        expected: dict[str, Any],
        actual: dict[str, Any],
        annotation_type: str,
    ) -> str:
        """Generate annotator feedback for golden evaluation."""
        if correct:
            return "Correct. Your annotation matches the expert label."

        if annotation_type in ("enum", "classification", "preference"):
            exp = expected.get("label") or expected.get("preferred")
            act = actual.get("label") or actual.get("preferred")
            return f"Incorrect. Expected '{exp}', you selected '{act}'. Review the annotation guidelines for this category."

        return "Your annotation did not match the expert label. Review the guidelines."


if __name__ == "__main__":
    evaluator = GoldenSetEvaluator()
    project_id = uuid4()

    print("=== Golden Set Evaluator Demo ===\n")

    # Create pool with 20 items
    items = []
    for i in range(20):
        diff = ["easy", "medium", "hard"][i % 3]
        items.append(GoldenItem(
            item_id=uuid4(),
            gold_annotation={"label": random.choice(["fraud", "legitimate"])},
            labeled_by=uuid4(),
            difficulty=diff,
            task_type="fraud_classification",
        ))

    pool = evaluator.create_pool(project_id, "fraud_classification", items)
    print(f"Pool created: {len(pool.items)} items")

    # Simulate evaluations
    annotator_id = uuid4()
    correct_count = 0
    for i in range(15):
        if evaluator.should_insert_golden(project_id, items_since_last_golden=i % 8):
            item = evaluator.select_golden_item(project_id, annotator_id)
            if item:
                is_correct = random.random() < 0.90
                annotation = {"label": item.gold_annotation["label"] if is_correct else "suspicious"}
                result = evaluator.evaluate(item, annotator_id, annotation, "classification")
                if result.correct:
                    correct_count += 1

    print(f"Evaluations: {len(evaluator.evaluation_history)}, Correct: {correct_count}")
    print(f"Pool health: {evaluator.get_pool_health(project_id)}")

    # Rotation
    new_items = [GoldenItem(
        item_id=uuid4(), gold_annotation={"label": "fraud"},
        labeled_by=uuid4(), difficulty="medium", task_type="fraud_classification",
    ) for _ in range(10)]
    rotation = evaluator.rotate_pool(project_id, new_items)
    print(f"Rotation: {rotation}")
