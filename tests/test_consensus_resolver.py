"""
Comprehensive test suite for consensus resolver.

Tests resolution paths:
- Majority vote: 2-of-3 agree, simple and transparent
- Weighted vote: accuracy-weighted decisions (DEC-004 approach)
- Expert tiebreak: when automated methods fail
- Single annotator: edge case handling
- Batch resolution: operations on multiple tasks

Key test scenarios:
1. Clear majorities (high confidence)
2. Expert outweighing multiple lower-accuracy annotators
3. No consensus (routes to expert queue)
4. Tie-breaking with margin analysis
5. Batch distribution analysis
"""

import pytest
import sys
import os
from uuid import uuid4

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from annotation.consensus_resolver import (
    ConsensusResolver,
    ConsensusMethod,
    AnnotatorVote,
    ConsensusResult,
)


class TestMajorityVote:
    """Majority vote consensus resolution."""

    def test_unanimous_agreement(self):
        """All annotators agree."""
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.90),
            AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.85),
            AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.88),
        ]

        result = resolver.resolve(votes, ConsensusMethod.MAJORITY_VOTE)

        assert result.passed_quality
        assert result.resolved_annotation["label"] == "fraud"
        assert result.agreement_score == 1.0
        assert result.method == ConsensusMethod.MAJORITY_VOTE
        assert result.details["vote_count"] == 3
        assert result.details["total_votes"] == 3

    def test_clear_majority_2_of_3(self):
        """Two annotators agree, one disagrees."""
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.90),
            AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.88),
            AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.85),
        ]

        result = resolver.resolve(votes, ConsensusMethod.MAJORITY_VOTE)

        assert result.passed_quality
        assert result.resolved_annotation["label"] == "fraud"
        assert result.agreement_score == 2/3
        assert result.details["label_distribution"]["fraud"] == 2

    def test_no_majority_3_way_split(self):
        """Three-way split with no majority."""
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"label": "fraud_cnp"}, accuracy_score=0.90),
            AnnotatorVote(uuid4(), {"label": "fraud_ato"}, accuracy_score=0.88),
            AnnotatorVote(uuid4(), {"label": "suspicious"}, accuracy_score=0.85),
        ]

        result = resolver.resolve(votes, ConsensusMethod.MAJORITY_VOTE)

        assert not result.passed_quality
        assert result.quality_failure_reason == "no_majority"
        assert result.agreement_score == 1/3

    def test_no_consensus_routes_to_expert(self):
        """Failed consensus should set quality_failure_reason."""
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"label": "A"}, accuracy_score=0.90),
            AnnotatorVote(uuid4(), {"label": "B"}, accuracy_score=0.88),
        ]

        result = resolver.resolve(votes, ConsensusMethod.MAJORITY_VOTE)

        # 50-50 split with 2 annotators, no majority
        assert not result.passed_quality
        assert result.quality_failure_reason == "no_majority"

    def test_minimum_agreement_threshold(self):
        """Enforce minimum agreement quality gate."""
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"label": "A"}, accuracy_score=0.90),
            AnnotatorVote(uuid4(), {"label": "A"}, accuracy_score=0.88),
            AnnotatorVote(uuid4(), {"label": "B"}, accuracy_score=0.85),
            AnnotatorVote(uuid4(), {"label": "B"}, accuracy_score=0.82),
        ]

        # 50-50 split doesn't meet 75% threshold
        result = resolver.resolve(
            votes,
            ConsensusMethod.MAJORITY_VOTE,
            min_agreement=0.75
        )

        assert not result.passed_quality


class TestWeightedVote:
    """Accuracy-weighted vote (DEC-004)."""

    def test_high_accuracy_annotator_outweighs_two_lower(self):
        """
        DEC-004: weighted vote should make expert's vote count more.

        Expert 97% accuracy outweighs two junior 78% annotators
        voting differently, even though majority vote would lose.
        """
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.97),     # expert
            AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.78),    # junior
            AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.75),    # junior
        ]

        result = resolver.resolve(votes, ConsensusMethod.WEIGHTED_VOTE)

        assert result.passed_quality
        assert result.resolved_annotation["label"] == "fraud"  # expert wins
        assert result.method == ConsensusMethod.WEIGHTED_VOTE
        assert result.details["margin"] > 0  # weighted margin is positive

    def test_weighted_score_computation(self):
        """Weighted scores should sum to 1.0 (normalized)."""
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.90),
            AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.80),
        ]

        result = resolver.resolve(votes, ConsensusMethod.WEIGHTED_VOTE)

        assert result.passed_quality
        weighted_scores = result.details["weighted_scores"]
        # Check normalization
        total = sum(weighted_scores.values())
        assert abs(total - 1.0) < 0.01

    def test_insufficient_margin_triggers_expert_tiebreak(self):
        """Close weighted vote should trigger expert escalation."""
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.85),
            AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.84),  # very close
        ]

        result = resolver.resolve(votes, ConsensusMethod.EXPERT_TIEBREAK)

        # Margin (0.85 - 0.84) = 0.01 is less than MIN_WEIGHTED_MARGIN (0.05)
        assert result.quality_failure_reason == "needs_expert_tiebreak"

    def test_selects_best_annotation_from_winning_voters(self):
        """
        Among annotators voting for winner, select from highest-accuracy one.

        Rationale: bounding boxes from higher-accuracy annotator are
        likely more precise.
        """
        resolver = ConsensusResolver()
        a_id = uuid4()
        b_id = uuid4()

        votes = [
            AnnotatorVote(a_id, {"label": "fraud", "reasoning": "Poor"}, accuracy_score=0.95),
            AnnotatorVote(b_id, {"label": "fraud", "reasoning": "Excellent"}, accuracy_score=0.85),
        ]

        result = resolver.resolve(votes, ConsensusMethod.WEIGHTED_VOTE)

        # Should select from higher-accuracy annotator (A)
        assert result.resolved_annotation["reasoning"] == "Poor"


class TestExpertTiebreak:
    """Expert adjudication for failed consensus."""

    def test_expert_resolves_tied_vote(self):
        """Expert decision resolves no-consensus items."""
        resolver = ConsensusResolver()
        expert_id = uuid4()
        votes = [
            AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.90),
            AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.88),
        ]

        result = resolver.resolve_with_expert(
            votes,
            {"label": "fraud", "expert_notes": "Transaction pattern matches known fraud"},
            expert_id=expert_id,
            notes="Clear fraud indicator based on merchant and amount"
        )

        assert result.passed_quality
        assert result.method == ConsensusMethod.EXPERT_TIEBREAK
        assert result.resolved_annotation["label"] == "fraud"
        assert result.confidence == 0.95  # expert decisions are high confidence
        assert expert_id in result.contributing_votes
        assert result.details["expert_notes"]

    def test_expert_decision_high_confidence(self):
        """Expert decisions should have high confidence."""
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"label": "A"}, accuracy_score=0.80),
            AnnotatorVote(uuid4(), {"label": "B"}, accuracy_score=0.75),
            AnnotatorVote(uuid4(), {"label": "C"}, accuracy_score=0.70),
        ]

        result = resolver.resolve_with_expert(
            votes,
            {"label": "A"},
            expert_id=uuid4(),
            notes="Clear winner despite close disagreement"
        )

        assert result.confidence == 0.95


class TestSingleAnnotator:
    """Edge case: only one annotator (overlap = 1)."""

    def test_single_annotator_resolution(self):
        """Single annotator should resolve with their accuracy as confidence."""
        resolver = ConsensusResolver()
        annotator_id = uuid4()
        votes = [
            AnnotatorVote(annotator_id, {"label": "fraud"}, accuracy_score=0.92),
        ]

        result = resolver.resolve(votes)

        assert result.passed_quality
        assert result.method == ConsensusMethod.SINGLE_ANNOTATOR
        assert result.resolved_annotation["label"] == "fraud"
        assert result.agreement_score == 1.0
        assert result.confidence == 0.92  # uses annotator accuracy
        assert len(result.contributing_votes) == 1


class TestBatchResolution:
    """Batch operations on multiple tasks."""

    def test_resolve_batch_multiple_tasks(self):
        """Resolve consensus for multiple tasks at once."""
        resolver = ConsensusResolver()

        task_votes = {
            uuid4(): [
                AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.90),
                AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.88),
            ],
            uuid4(): [
                AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.85),
                AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.82),
            ],
            uuid4(): [
                AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.90),
                AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.88),
            ],
        }

        results = resolver.resolve_batch(task_votes)

        assert len(results) == 3
        for task_id, result in results.items():
            assert isinstance(result, ConsensusResult)

    def test_resolution_distribution_analysis(self):
        """Analyze distribution of resolution outcomes."""
        resolver = ConsensusResolver()

        # Simulate 20 tasks with mixed outcomes
        task_votes = {}
        for i in range(20):
            task_id = uuid4()
            if i < 15:  # 75% unanimous
                votes = [
                    AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.90),
                    AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.88),
                    AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.85),
                ]
            else:  # 25% split
                votes = [
                    AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.90),
                    AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.88),
                ]
            task_votes[task_id] = votes

        results = resolver.resolve_batch(task_votes)
        distribution = resolver.get_resolution_distribution(results)

        assert distribution["total_tasks"] == 20
        assert distribution["resolved"] > 0
        assert distribution["unresolved"] >= 0
        assert distribution["resolution_rate"] > 0.5  # Most should resolve
        assert "by_method" in distribution
        assert distribution["avg_agreement"] > 0

    def test_get_resolution_distribution_empty(self):
        """Empty results should return empty distribution."""
        resolver = ConsensusResolver()
        distribution = resolver.get_resolution_distribution({})
        assert distribution == {}


class TestLabelFieldExtraction:
    """Test label field extraction from annotation data."""

    def test_custom_label_field(self):
        """Resolve on non-default label field."""
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"preferred": "A", "label": "fraud"}),
            AnnotatorVote(uuid4(), {"preferred": "A", "label": "legit"}),
            AnnotatorVote(uuid4(), {"preferred": "B", "label": "fraud"}),
        ]

        result = resolver.resolve(votes, label_field="preferred")

        assert result.resolved_annotation["preferred"] == "A"

    def test_missing_label_field(self):
        """Handle missing label field gracefully."""
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"reasoning": "looks suspicious"}),  # no label
            AnnotatorVote(uuid4(), {"label": "fraud"}),
        ]

        result = resolver.resolve(votes)

        assert not result.passed_quality
        assert result.quality_failure_reason == "no_extractable_labels"


class TestQualityGates:
    """Quality control thresholds."""

    def test_enforces_min_agreement_quality(self):
        """Reject resolutions below minimum agreement threshold."""
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.90),
            AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.88),
            AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.85),
        ]

        # 2/3 agreement = 0.667
        result = resolver.resolve(
            votes,
            ConsensusMethod.WEIGHTED_VOTE,
            min_agreement=0.90  # require 90% agreement
        )

        assert not result.passed_quality
        assert result.quality_failure_reason == "below_min_agreement"

    def test_empty_votes_returns_failed_result(self):
        """Empty vote list should fail gracefully."""
        resolver = ConsensusResolver()
        result = resolver.resolve([])

        assert not result.passed_quality
        assert result.quality_failure_reason == "no_votes"
        assert result.agreement_score == 0.0


class TestDEC004Backtest:
    """
    DEC-004 backtest scenario: weighted vote vs majority vote.

    DEC-004: weighted vote agrees with expert ground truth 91% vs 86%
    for majority vote. The 5% improvement justifies accuracy-weighted voting.
    """

    def test_expert_vs_two_juniors_scenario(self):
        """
        Real scenario: expert 97% vs two juniors 78%, 75%.
        Expert says "fraud", juniors say "legit" (majority).
        Weighted vote should pick "fraud", majority picks "legit".

        If expert ground truth is "fraud", weighted vote is correct.
        """
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.97),
            AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.78),
            AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.75),
        ]

        # Majority vote picks "legit" (2-of-3)
        majority_result = resolver.resolve(votes, ConsensusMethod.MAJORITY_VOTE)
        assert majority_result.resolved_annotation["label"] == "legit"

        # Weighted vote picks "fraud" (expert outweighs)
        weighted_result = resolver.resolve(votes, ConsensusMethod.WEIGHTED_VOTE)
        assert weighted_result.resolved_annotation["label"] == "fraud"

        # If ground truth is "fraud", weighted vote is correct
        ground_truth = "fraud"
        assert weighted_result.resolved_annotation["label"] == ground_truth
        assert majority_result.resolved_annotation["label"] != ground_truth


class TestErrorHandling:
    """Error handling and edge cases."""

    def test_handles_missing_annotation_data(self):
        """Missing annotation data fields should be skipped."""
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {}),  # empty annotation
            AnnotatorVote(uuid4(), {"label": "fraud"}),
        ]

        result = resolver.resolve(votes)

        # Should handle gracefully
        assert isinstance(result, ConsensusResult)

    def test_numeric_labels_as_strings(self):
        """Numeric labels should be converted to strings."""
        resolver = ConsensusResolver()
        votes = [
            AnnotatorVote(uuid4(), {"label": 1}, accuracy_score=0.90),
            AnnotatorVote(uuid4(), {"label": 1}, accuracy_score=0.88),
        ]

        result = resolver.resolve(votes)

        assert result.passed_quality
        assert str(result.resolved_annotation["label"]) == "1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
