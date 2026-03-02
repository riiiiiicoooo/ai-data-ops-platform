"""
Annotator Scorer: Rolling accuracy tracking and skill classification.

Tracks each annotator's accuracy across golden set evaluations,
peer agreement, and review outcomes. Computes rolling windows
(last 100 items, last 7 days, lifetime) and classifies annotators
into skill levels (junior < 85%, senior 85-95%, expert > 95%).

Key design decisions:
- Rolling windows rather than lifetime-only (catches recent degradation)
- Auto-dequalification after 5 consecutive golden failures (DEC-008)
- Gaming detection: golden accuracy vs peer agreement gap (DEC-006)
- Trend detection for proactive intervention

PM context: Built this after discovering that an annotator's lifetime
accuracy was 91% but their last-7-day accuracy had dropped to 74%.
The lifetime metric masked a sharp recent decline. Rolling windows
catch degradation within days instead of weeks, enabling intervention
before hundreds of bad labels enter the pipeline.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import UUID, uuid4


@dataclass
class GoldenEvaluation:
    """Result of one golden set evaluation."""
    golden_item_id: UUID
    correct: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    metric_score: float
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AnnotatorScorecard:
    """Complete quality profile for one annotator on one task type."""
    annotator_id: UUID
    task_type: str

    # Rolling accuracy windows
    accuracy_last_100: float = 0.0
    accuracy_last_7d: float = 0.0
    accuracy_lifetime: float = 0.0

    # Counts
    golden_evaluated: int = 0
    golden_correct: int = 0
    consecutive_failures: int = 0

    # Peer metrics
    peer_agreement_rate: float = 0.0

    # Throughput
    avg_seconds_per_annotation: float = 0.0
    annotations_per_hour: float = 0.0

    # Classification
    skill_level: str = "junior"  # junior, senior, expert
    trend: str = "stable"        # improving, stable, degrading

    # Gaming detection
    gaming_suspicion_score: float = 0.0  # golden_acc - peer_agreement

    # Status
    qualified: bool = True
    dequalification_reason: Optional[str] = None


class AnnotatorScorer:
    """
    Tracks and evaluates annotator quality over time.

    Three accuracy windows serve different purposes:
    - Last 100 golden items: current performance level (skill classification)
    - Last 7 days: recent trend detection (catching degradation)
    - Lifetime: overall track record (qualification decisions)

    Auto-dequalification: 5 consecutive golden failures triggers
    automatic pause. This prevents an annotator having a bad day
    from contaminating hundreds of labels before anyone notices.
    """

    SKILL_THRESHOLDS = {"expert": 0.95, "senior": 0.85, "junior": 0.0}
    CONSECUTIVE_FAILURE_LIMIT = 5
    GAMING_SUSPICION_THRESHOLD = 0.15  # golden_acc - peer_agreement > 15%
    TREND_WINDOW_DAYS = 14
    TREND_DEGRADATION_THRESHOLD = -0.05  # 5% drop over 2 weeks

    def __init__(self):
        # annotator_id -> task_type -> evaluation history
        self.evaluations: dict[UUID, dict[str, deque]] = {}
        self.scorecards: dict[tuple[UUID, str], AnnotatorScorecard] = {}
        self.timing_data: dict[UUID, list[float]] = {}  # seconds per annotation

    def record_golden_evaluation(
        self,
        annotator_id: UUID,
        task_type: str,
        evaluation: GoldenEvaluation,
    ) -> AnnotatorScorecard:
        """
        Record a golden set evaluation and update the annotator's scorecard.
        Returns updated scorecard with current metrics.
        """
        # Initialize tracking structures
        if annotator_id not in self.evaluations:
            self.evaluations[annotator_id] = {}
        if task_type not in self.evaluations[annotator_id]:
            self.evaluations[annotator_id][task_type] = deque(maxlen=500)

        self.evaluations[annotator_id][task_type].append(evaluation)

        key = (annotator_id, task_type)
        if key not in self.scorecards:
            self.scorecards[key] = AnnotatorScorecard(
                annotator_id=annotator_id, task_type=task_type,
            )

        scorecard = self.scorecards[key]
        evals = list(self.evaluations[annotator_id][task_type])

        # Update counts
        scorecard.golden_evaluated = len(evals)
        scorecard.golden_correct = sum(1 for e in evals if e.correct)

        # Consecutive failures
        if evaluation.correct:
            scorecard.consecutive_failures = 0
        else:
            scorecard.consecutive_failures += 1

        # Rolling accuracy: last 100
        recent_100 = evals[-100:]
        correct_100 = sum(1 for e in recent_100 if e.correct)
        scorecard.accuracy_last_100 = correct_100 / len(recent_100) if recent_100 else 0.0

        # Rolling accuracy: last 7 days
        cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
        recent_7d = [e for e in evals if e.evaluated_at > cutoff_7d]
        correct_7d = sum(1 for e in recent_7d if e.correct)
        scorecard.accuracy_last_7d = correct_7d / len(recent_7d) if recent_7d else scorecard.accuracy_last_100

        # Lifetime accuracy
        scorecard.accuracy_lifetime = (
            scorecard.golden_correct / scorecard.golden_evaluated
            if scorecard.golden_evaluated > 0 else 0.0
        )

        # Skill level classification
        primary_accuracy = scorecard.accuracy_last_100
        if primary_accuracy >= self.SKILL_THRESHOLDS["expert"]:
            scorecard.skill_level = "expert"
        elif primary_accuracy >= self.SKILL_THRESHOLDS["senior"]:
            scorecard.skill_level = "senior"
        else:
            scorecard.skill_level = "junior"

        # Trend detection
        scorecard.trend = self._compute_trend(evals)

        # Gaming detection (golden accuracy vs peer agreement)
        if scorecard.peer_agreement_rate > 0:
            gap = scorecard.accuracy_last_100 - scorecard.peer_agreement_rate
            scorecard.gaming_suspicion_score = round(gap, 3)

        # Auto-dequalification check
        if scorecard.consecutive_failures >= self.CONSECUTIVE_FAILURE_LIMIT:
            scorecard.qualified = False
            scorecard.dequalification_reason = (
                f"{scorecard.consecutive_failures} consecutive golden failures"
            )

        # Round for display
        scorecard.accuracy_last_100 = round(scorecard.accuracy_last_100, 4)
        scorecard.accuracy_last_7d = round(scorecard.accuracy_last_7d, 4)
        scorecard.accuracy_lifetime = round(scorecard.accuracy_lifetime, 4)

        return scorecard

    def record_annotation_timing(
        self, annotator_id: UUID, duration_seconds: float,
    ) -> None:
        """Record annotation duration for throughput calculation."""
        if annotator_id not in self.timing_data:
            self.timing_data[annotator_id] = []
        self.timing_data[annotator_id].append(duration_seconds)
        # Keep last 200
        if len(self.timing_data[annotator_id]) > 200:
            self.timing_data[annotator_id] = self.timing_data[annotator_id][-200:]

    def update_peer_agreement(
        self, annotator_id: UUID, task_type: str, peer_rate: float,
    ) -> None:
        """Update peer agreement rate (computed externally from consensus)."""
        key = (annotator_id, task_type)
        if key in self.scorecards:
            self.scorecards[key].peer_agreement_rate = round(peer_rate, 4)

    def get_scorecard(self, annotator_id: UUID, task_type: str) -> Optional[AnnotatorScorecard]:
        """Retrieve current scorecard."""
        return self.scorecards.get((annotator_id, task_type))

    def get_all_scorecards(self, task_type: Optional[str] = None) -> list[AnnotatorScorecard]:
        """Get all scorecards, optionally filtered by task type."""
        cards = list(self.scorecards.values())
        if task_type:
            cards = [c for c in cards if c.task_type == task_type]
        return sorted(cards, key=lambda c: c.accuracy_last_100, reverse=True)

    def get_gaming_suspects(self, task_type: Optional[str] = None) -> list[AnnotatorScorecard]:
        """Find annotators where golden accuracy exceeds peer agreement by >15%."""
        cards = self.get_all_scorecards(task_type)
        return [
            c for c in cards
            if c.gaming_suspicion_score > self.GAMING_SUSPICION_THRESHOLD
            and c.golden_evaluated >= 20  # enough data to be meaningful
        ]

    def get_dequalified(self) -> list[AnnotatorScorecard]:
        """Get all dequalified annotators."""
        return [c for c in self.scorecards.values() if not c.qualified]

    def _compute_trend(self, evals: list[GoldenEvaluation]) -> str:
        """Detect accuracy trend over last 2 weeks."""
        if len(evals) < 20:
            return "stable"

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=self.TREND_WINDOW_DAYS)
        midpoint = now - timedelta(days=self.TREND_WINDOW_DAYS / 2)

        first_half = [e for e in evals if cutoff < e.evaluated_at <= midpoint]
        second_half = [e for e in evals if e.evaluated_at > midpoint]

        if not first_half or not second_half:
            return "stable"

        acc_first = sum(1 for e in first_half if e.correct) / len(first_half)
        acc_second = sum(1 for e in second_half if e.correct) / len(second_half)
        delta = acc_second - acc_first

        if delta <= self.TREND_DEGRADATION_THRESHOLD:
            return "degrading"
        elif delta >= abs(self.TREND_DEGRADATION_THRESHOLD):
            return "improving"
        return "stable"

    def generate_quality_report(self, task_type: str) -> dict[str, Any]:
        """Generate aggregate quality report for a task type."""
        cards = self.get_all_scorecards(task_type)
        if not cards:
            return {"task_type": task_type, "annotator_count": 0}

        accuracies = [c.accuracy_last_100 for c in cards if c.golden_evaluated >= 10]
        return {
            "task_type": task_type,
            "annotator_count": len(cards),
            "qualified_count": sum(1 for c in cards if c.qualified),
            "dequalified_count": sum(1 for c in cards if not c.qualified),
            "avg_accuracy": round(sum(accuracies) / len(accuracies), 4) if accuracies else 0,
            "min_accuracy": round(min(accuracies), 4) if accuracies else 0,
            "max_accuracy": round(max(accuracies), 4) if accuracies else 0,
            "skill_distribution": {
                level: sum(1 for c in cards if c.skill_level == level)
                for level in ["junior", "senior", "expert"]
            },
            "trend_distribution": {
                trend: sum(1 for c in cards if c.trend == trend)
                for trend in ["improving", "stable", "degrading"]
            },
            "gaming_suspects": len(self.get_gaming_suspects(task_type)),
        }


if __name__ == "__main__":
    import random
    scorer = AnnotatorScorer()

    print("=== Annotator Scorer Demo ===\n")

    # Simulate 3 annotators with different quality profiles
    annotators = {
        "Expert": (uuid4(), 0.97),
        "Senior": (uuid4(), 0.88),
        "Struggling": (uuid4(), 0.72),
    }

    for name, (ann_id, base_accuracy) in annotators.items():
        for i in range(50):
            correct = random.random() < base_accuracy
            card = scorer.record_golden_evaluation(
                ann_id, "rlhf_preference",
                GoldenEvaluation(
                    golden_item_id=uuid4(), correct=correct,
                    expected={"preferred": "A"}, actual={"preferred": "A" if correct else "B"},
                    metric_score=1.0 if correct else 0.0,
                ),
            )

        print(f"  {name}:")
        print(f"    Accuracy (last 100): {card.accuracy_last_100:.1%}")
        print(f"    Skill level: {card.skill_level}")
        print(f"    Trend: {card.trend}")
        print(f"    Qualified: {card.qualified}")

    # Simulate consecutive failures for dequalification
    print("\n--- Dequalification demo ---")
    failing_id = uuid4()
    for i in range(6):
        card = scorer.record_golden_evaluation(
            failing_id, "radiology_bbox",
            GoldenEvaluation(
                golden_item_id=uuid4(), correct=False,
                expected={"label": "mass"}, actual={"label": "no_finding"},
                metric_score=0.0,
            ),
        )
    print(f"  After 6 consecutive failures: qualified={card.qualified}")
    print(f"  Reason: {card.dequalification_reason}")

    # Quality report
    print(f"\n--- Quality Report ---")
    report = scorer.generate_quality_report("rlhf_preference")
    print(f"  Annotators: {report['annotator_count']}")
    print(f"  Avg accuracy: {report['avg_accuracy']:.1%}")
    print(f"  Skill distribution: {report['skill_distribution']}")
