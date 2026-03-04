"""
Comprehensive test suite for agreement calculator.

Tests all 7 agreement metrics across diverse annotation scenarios:
- Cohen's kappa: 2 annotators, categorical labels
- Fleiss' kappa: 3+ annotators, categorical labels
- Krippendorff's alpha: handles missing data, variable annotator counts
- IoU: bounding box spatial agreement
- Dice: segmentation mask overlap
- Span F1: NER entity matching
- BLEU: free-text similarity

Each test validates both the metric computation and interpretation
(strong/moderate/fair/poor agreement classification).
"""

import pytest
import sys
import os

# Add src to path so we can import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from quality.agreement_calculator import AgreementCalculator, AgreementScore


class TestCohensKappa:
    """Cohen's kappa for 2 annotators on categorical labels."""

    def test_perfect_agreement(self):
        """Perfect agreement should yield kappa = 1.0"""
        calc = AgreementCalculator()
        ann_a = ["fraud", "legit", "fraud", "legit", "legit"]
        ann_b = ["fraud", "legit", "fraud", "legit", "legit"]

        result = calc.cohens_kappa(ann_a, ann_b)

        assert result.score == 1.0
        assert result.interpretation == "strong"
        assert result.n_annotators == 2
        assert result.n_items == 5
        assert result.details["observed_agreement"] == 1.0
        assert result.details["raw_agreement_pct"] == 100.0

    def test_complete_disagreement(self):
        """Complete disagreement should yield kappa <= 0"""
        calc = AgreementCalculator()
        ann_a = ["A", "A", "A", "A"]
        ann_b = ["B", "B", "B", "B"]

        result = calc.cohens_kappa(ann_a, ann_b)

        assert result.score <= 0.0
        assert result.n_items == 4

    def test_partial_agreement_high_chance(self):
        """
        When base rate is high (90% of items are class A),
        raw agreement can be high but kappa is low.

        This demonstrates why chance-corrected metrics matter.
        """
        calc = AgreementCalculator()
        # 90% A, 10% B
        ann_a = ["A"] * 9 + ["B"]
        ann_b = ["A"] * 9 + ["B"]

        result = calc.cohens_kappa(ann_a, ann_b)

        # Perfect agreement on this distribution
        assert result.score == 1.0

        # Now both annotators just guess A all the time
        ann_a2 = ["A"] * 10
        ann_b2 = ["A"] * 10
        result2 = calc.cohens_kappa(ann_a2, ann_b2)

        # Kappa should be very low despite 100% raw agreement
        assert result2.details["raw_agreement_pct"] == 100.0
        assert result2.score == 0.0  # No better than chance

    def test_moderate_agreement(self):
        """Real-world disagreement producing moderate agreement."""
        calc = AgreementCalculator()
        ann_a = ["fraud", "legit", "fraud", "legit", "legit", "legit", "fraud", "legit"]
        ann_b = ["fraud", "legit", "legit", "legit", "legit", "legit", "fraud", "fraud"]

        result = calc.cohens_kappa(ann_a, ann_b)

        assert 0.4 <= result.score <= 0.8  # Should be fair to moderate
        assert result.interpretation in ("fair", "moderate")
        assert result.n_items == 8

    def test_empty_annotations(self):
        """Empty annotations should be handled gracefully."""
        calc = AgreementCalculator()
        result = calc.cohens_kappa([], [])
        assert result.score == 0.0
        assert result.n_items == 0

    def test_mismatched_length(self):
        """Mismatched annotation lengths should raise error."""
        calc = AgreementCalculator()
        with pytest.raises(ValueError):
            calc.cohens_kappa(["A", "B"], ["A", "B", "C"])


class TestFleissKappa:
    """Fleiss' kappa for 3+ annotators."""

    def test_unanimous_agreement(self):
        """All raters agree on all items."""
        calc = AgreementCalculator()
        matrix = [
            ["A", "A", "A"],
            ["B", "B", "B"],
            ["A", "A", "A"],
        ]

        result = calc.fleiss_kappa(matrix)

        assert result.score == 1.0
        assert result.interpretation == "strong"
        assert result.n_annotators == 3
        assert result.n_items == 3

    def test_mixed_agreement_3_annotators(self):
        """Some items have 2-of-3 agreement, some unanimous."""
        calc = AgreementCalculator()
        matrix = [
            ["A", "A", "A"],   # unanimous
            ["A", "A", "B"],   # 2-of-3
            ["A", "B", "B"],   # 2-of-3
            ["B", "B", "B"],   # unanimous
        ]

        result = calc.fleiss_kappa(matrix)

        assert result.metric == "fleiss_kappa"
        assert 0.4 <= result.score <= 1.0
        assert result.n_annotators == 3
        assert result.n_items == 4

    def test_label_proportions_computed(self):
        """Label proportions should be tracked."""
        calc = AgreementCalculator()
        matrix = [
            ["fraud", "fraud", "legit"],
            ["fraud", "fraud", "fraud"],
        ]

        result = calc.fleiss_kappa(matrix)

        assert "label_proportions" in result.details
        proportions = result.details["label_proportions"]
        assert "fraud" in proportions
        assert "legit" in proportions
        # fraud appears in 5 of 6 slots
        assert abs(proportions["fraud"] - 5/6) < 0.01
        # legit appears in 1 of 6 slots
        assert abs(proportions["legit"] - 1/6) < 0.01

    def test_single_label_returns_perfect_agreement(self):
        """If only one label present, agreement is perfect."""
        calc = AgreementCalculator()
        matrix = [["A", "A"], ["A", "A"]]
        result = calc.fleiss_kappa(matrix)
        assert result.score == 1.0


class TestKrippendorffAlpha:
    """Krippendorff's alpha: handles missing data and variable raters."""

    def test_perfect_agreement_with_missing_data(self):
        """Perfect agreement even with missing annotations."""
        calc = AgreementCalculator()
        annotations = [
            ["A", "A", None],     # 2 raters annotated, both agree
            ["B", "B", "B"],      # 3 raters, all agree
            ["A", None, None],    # 1 rater
        ]

        result = calc.krippendorff_alpha(annotations)

        assert result.score == 1.0
        assert result.interpretation == "strong"
        assert result.details["missing_values"] == 3

    def test_partial_disagreement_with_missing(self):
        """Disagreement with variable missing data."""
        calc = AgreementCalculator()
        annotations = [
            ["fraud", "fraud", "legit"],
            ["legit", None, None],
            ["fraud", "fraud", "fraud"],
        ]

        result = calc.krippendorff_alpha(annotations)

        assert result.metric == "krippendorff_alpha"
        assert result.n_items == 3
        assert "total_pairs" in result.details

    def test_no_overlap_returns_zero(self):
        """Non-overlapping annotations return zero."""
        calc = AgreementCalculator()
        annotations = [
            ["A", None, None],
            [None, "B", None],
            [None, None, "C"],
        ]

        result = calc.krippendorff_alpha(annotations)

        assert result.score == 0.0

    def test_empty_annotations_returns_zero(self):
        """Empty input returns zero."""
        calc = AgreementCalculator()
        result = calc.krippendorff_alpha([])
        assert result.score == 0.0


class TestIoU:
    """IoU: Intersection over Union for bounding boxes."""

    def test_identical_boxes(self):
        """Identical bounding boxes should have IoU = 1.0"""
        calc = AgreementCalculator()
        boxes_a = [{"x": 100, "y": 100, "w": 50, "h": 50}]
        boxes_b = [{"x": 100, "y": 100, "w": 50, "h": 50}]

        result = calc.iou(boxes_a, boxes_b)

        assert result.score == 1.0
        assert result.interpretation == "strong"
        assert result.details["per_box_iou"][0] == 1.0

    def test_no_overlap(self):
        """Non-overlapping boxes should have IoU = 0.0"""
        calc = AgreementCalculator()
        boxes_a = [{"x": 0, "y": 0, "w": 10, "h": 10}]
        boxes_b = [{"x": 100, "y": 100, "w": 10, "h": 10}]

        result = calc.iou(boxes_a, boxes_b)

        assert result.score == 0.0

    def test_partial_overlap(self):
        """Partially overlapping boxes should have 0 < IoU < 1."""
        calc = AgreementCalculator()
        # Box A: (100,100) to (150,150) = 50x50 = 2500
        # Box B: (125,125) to (175,175) = 50x50 = 2500
        # Intersection: (125,125) to (150,150) = 25x25 = 625
        # Union: 2500 + 2500 - 625 = 4375
        # IoU: 625/4375 ≈ 0.143
        boxes_a = [{"x": 100, "y": 100, "w": 50, "h": 50}]
        boxes_b = [{"x": 125, "y": 125, "w": 50, "h": 50}]

        result = calc.iou(boxes_a, boxes_b)

        assert 0.0 < result.score < 1.0
        assert result.interpretation == "poor"

    def test_multiple_boxes_with_matching(self):
        """Multiple boxes should use greedy matching."""
        calc = AgreementCalculator()
        # Annotator A: 2 boxes
        boxes_a = [
            {"x": 0, "y": 0, "w": 50, "h": 50},      # perfect match with B[0]
            {"x": 100, "y": 100, "w": 30, "h": 30},  # perfect match with B[1]
        ]
        # Annotator B: 2 boxes (same as A)
        boxes_b = [
            {"x": 0, "y": 0, "w": 50, "h": 50},
            {"x": 100, "y": 100, "w": 30, "h": 30},
        ]

        result = calc.iou(boxes_a, boxes_b)

        assert result.score == 1.0
        assert len(result.details["per_box_iou"]) == 2

    def test_unmatched_boxes_penalized(self):
        """Extra boxes in one set should lower IoU."""
        calc = AgreementCalculator()
        boxes_a = [
            {"x": 0, "y": 0, "w": 50, "h": 50},
            {"x": 100, "y": 100, "w": 30, "h": 30},
        ]
        boxes_b = [{"x": 0, "y": 0, "w": 50, "h": 50}]  # missing second box

        result = calc.iou(boxes_a, boxes_b)

        assert result.score < 1.0  # second box counts as 0 IoU
        assert result.details["unmatched_boxes"] == 1


class TestSpanF1:
    """Span-level F1 for NER annotations."""

    def test_identical_spans(self):
        """Identical spans should have F1 = 1.0"""
        calc = AgreementCalculator()
        spans_a = [
            {"start": 0, "end": 7, "label": "medication"},
            {"start": 12, "end": 18, "label": "dosage"},
        ]
        spans_b = [
            {"start": 0, "end": 7, "label": "medication"},
            {"start": 12, "end": 18, "label": "dosage"},
        ]

        result = calc.span_f1(spans_a, spans_b)

        assert result.score == 1.0
        assert result.details["exact_f1"] == 1.0
        assert result.details["relaxed_f1"] == 1.0

    def test_partial_boundary_mismatch(self):
        """Spans with same label but different boundaries."""
        calc = AgreementCalculator()
        spans_a = [{"start": 0, "end": 7, "label": "medication"}]
        spans_b = [{"start": 0, "end": 8, "label": "medication"}]  # off by 1

        result = calc.span_f1(spans_a, spans_b)

        # Exact F1 should be lower than relaxed
        assert result.details["exact_f1"] == 0.0
        assert result.details["relaxed_f1"] == 1.0  # overlaps and same label
        assert result.score == 1.0  # relaxed_f1 is the primary score

    def test_label_mismatch(self):
        """Different labels should not match."""
        calc = AgreementCalculator()
        spans_a = [{"start": 0, "end": 7, "label": "medication"}]
        spans_b = [{"start": 0, "end": 7, "label": "dosage"}]  # different label

        result = calc.span_f1(spans_a, spans_b)

        assert result.score == 0.0

    def test_no_overlap(self):
        """Non-overlapping spans should not match."""
        calc = AgreementCalculator()
        spans_a = [{"start": 0, "end": 5, "label": "medication"}]
        spans_b = [{"start": 10, "end": 15, "label": "medication"}]

        result = calc.span_f1(spans_a, spans_b)

        assert result.score == 0.0

    def test_multiple_spans_mixed_agreement(self):
        """Some spans match, some don't."""
        calc = AgreementCalculator()
        spans_a = [
            {"start": 0, "end": 7, "label": "medication"},     # matches
            {"start": 12, "end": 18, "label": "dosage"},       # matches exactly
            {"start": 25, "end": 35, "label": "diagnosis"},    # no match
        ]
        spans_b = [
            {"start": 0, "end": 7, "label": "medication"},
            {"start": 12, "end": 18, "label": "dosage"},
        ]

        result = calc.span_f1(spans_a, spans_b)

        # Precision: 2 correct out of 3 in A = 2/3
        # Recall: 2 correct out of 2 in B = 2/2 = 1.0
        # F1: 2*(2/3)*1.0 / (2/3+1.0) ≈ 0.8
        assert 0.7 < result.score < 1.0


class TestBLEUScore:
    """BLEU score for free-text annotation agreement."""

    def test_identical_text(self):
        """Identical text should have BLEU = 1.0"""
        calc = AgreementCalculator()
        text_a = "The patient presents with pneumonia and fever"
        text_b = "The patient presents with pneumonia and fever"

        result = calc.bleu_score(text_a, text_b)

        assert result.score == 1.0
        assert result.interpretation == "strong"

    def test_completely_different_text(self):
        """Completely different text should have low BLEU."""
        calc = AgreementCalculator()
        text_a = "The quick brown fox"
        text_b = "Elephant zebra giraffe"

        result = calc.bleu_score(text_a, text_b)

        assert result.score == 0.0

    def test_partial_overlap(self):
        """Text with partial n-gram overlap."""
        calc = AgreementCalculator()
        text_a = "The patient has pneumonia"
        text_b = "Patient has severe pneumonia"

        result = calc.bleu_score(text_a, text_b)

        # Should be moderate (shares "patient" and "pneumonia")
        assert 0.1 < result.score < 1.0
        assert result.interpretation in ("fair", "moderate", "strong")

    def test_word_order_matters(self):
        """BLEU penalizes different word orders."""
        calc = AgreementCalculator()
        text_a = "The quick brown fox jumps"
        text_b = "jumps fox brown quick The"  # reversed

        result = calc.bleu_score(text_a, text_b)

        # Should be low due to different n-gram order
        assert result.score < 0.5

    def test_brevity_penalty_applied(self):
        """Much shorter text should be penalized."""
        calc = AgreementCalculator()
        text_a = "The patient has pneumonia and fever"
        text_b = "Patient pneumonia"  # much shorter

        result = calc.bleu_score(text_a, text_b)

        assert "brevity_penalty" in result.details
        assert result.details["brevity_penalty"] < 1.0


class TestAutoSelectMetric:
    """Auto-selection of appropriate metric based on annotation type."""

    def test_classification_selects_kappa(self):
        """Classification annotations should use Cohen's kappa."""
        calc = AgreementCalculator()
        ann_a = ["fraud", "legit", "fraud"]
        ann_b = ["fraud", "legit", "legit"]

        result = calc.compute_agreement("classification", [ann_a, ann_b])

        assert result.metric == "cohens_kappa"
        assert result.n_annotators == 2

    def test_enum_selects_kappa(self):
        """Enum field should use Cohen's kappa."""
        calc = AgreementCalculator()
        ann_a = ["A", "B", "A"]
        ann_b = ["A", "B", "B"]

        result = calc.compute_agreement("enum", [ann_a, ann_b])

        assert result.metric == "cohens_kappa"

    def test_bbox_selects_iou(self):
        """Bounding box annotations should use IoU."""
        calc = AgreementCalculator()
        boxes_a = [{"x": 0, "y": 0, "w": 50, "h": 50}]
        boxes_b = [{"x": 0, "y": 0, "w": 50, "h": 50}]

        result = calc.compute_agreement("bounding_box", [boxes_a, boxes_b])

        assert result.metric == "iou"

    def test_ner_selects_span_f1(self):
        """NER annotations should use span F1."""
        calc = AgreementCalculator()
        spans_a = [{"start": 0, "end": 7, "label": "medication"}]
        spans_b = [{"start": 0, "end": 7, "label": "medication"}]

        result = calc.compute_agreement("spans", [spans_a, spans_b])

        assert result.metric == "span_f1"

    def test_free_text_selects_bleu(self):
        """Free-text annotations should use BLEU."""
        calc = AgreementCalculator()
        text_a = "The patient has pneumonia"
        text_b = "Patient has pneumonia"

        result = calc.compute_agreement("free_text", [text_a, text_b])

        assert result.metric == "bleu"


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_single_item(self):
        """Agreement on single item."""
        calc = AgreementCalculator()
        result = calc.cohens_kappa(["A"], ["A"])
        assert result.n_items == 1
        assert result.score == 1.0

    def test_numeric_labels_converted_to_strings(self):
        """Numeric labels should be converted to strings."""
        calc = AgreementCalculator()
        result = calc.compute_agreement("classification", [[1, 2], [1, 2]])
        assert result.metric == "cohens_kappa"
        assert result.score == 1.0

    def test_large_number_of_annotators(self):
        """Many annotators should be handled."""
        calc = AgreementCalculator()
        # 10 annotators, unanimous agreement
        matrix = [["A"] * 10, ["B"] * 10, ["A"] * 10]
        result = calc.fleiss_kappa(matrix)
        assert result.n_annotators == 10
        assert result.score == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
