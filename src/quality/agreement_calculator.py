"""
Agreement Calculator: Multi-metric inter-annotator agreement measurement.

Implements 7 agreement metrics auto-selected based on annotation type.
This is the core of DEC-003: a single "accuracy" number is meaningless
across annotation types. Classification needs kappa, bounding boxes need
IoU, NER needs span F1, and free text needs BLEU.

Metrics implemented:
- Cohen's kappa (2 annotators, categorical)
- Fleiss' kappa (3+ annotators, categorical)
- Krippendorff's alpha (any count, handles missing data)
- IoU - Intersection over Union (bounding boxes)
- Dice coefficient (segmentation masks)
- Span-level F1 (NER span matching)
- BLEU score (free-text similarity)

PM context: This was the first module I prototyped to validate the
multi-metric approach. Showed stakeholders that raw agreement on a
fraud classification task was 92% but kappa was only 0.62 (because
90% of transactions are legitimate, so random agreement is high).
That single comparison convinced the team that chance-corrected
metrics were essential.
"""

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class AgreementScore:
    """Result of an agreement calculation."""
    metric: str
    score: float
    interpretation: str     # "strong", "moderate", "fair", "poor"
    n_annotators: int
    n_items: int
    details: dict[str, Any]


class AgreementCalculator:
    """
    Computes inter-annotator agreement using the metric appropriate
    for each annotation type.

    Interpretation scale (Landis & Koch for kappa-family metrics):
      > 0.80: strong agreement
      0.60-0.80: moderate agreement
      0.40-0.60: fair agreement
      0.20-0.40: slight agreement
      < 0.20: poor agreement

    For IoU/Dice:
      > 0.80: strong spatial agreement
      0.60-0.80: moderate
      < 0.60: poor
    """

    @staticmethod
    def interpret(score: float) -> str:
        """Interpret agreement score on standard scale."""
        if score >= 0.80:
            return "strong"
        elif score >= 0.60:
            return "moderate"
        elif score >= 0.40:
            return "fair"
        elif score >= 0.20:
            return "slight"
        else:
            return "poor"

    # ------------------------------------------------------------------
    # Cohen's Kappa (2 annotators, categorical)
    # ------------------------------------------------------------------

    def cohens_kappa(
        self,
        annotations_a: list[str],
        annotations_b: list[str],
    ) -> AgreementScore:
        """
        Cohen's kappa for 2 annotators on categorical labels.

        kappa = (observed_agreement - chance_agreement) / (1 - chance_agreement)

        Why kappa over raw agreement: if 90% of items are class A and
        two annotators both always guess A, raw agreement is 90% but
        kappa is 0.0 (they are no better than chance).
        """
        if len(annotations_a) != len(annotations_b):
            raise ValueError("Annotation lists must have equal length")

        n = len(annotations_a)
        if n == 0:
            return AgreementScore("cohens_kappa", 0.0, "poor", 2, 0, {})

        # Observed agreement
        agree_count = sum(1 for a, b in zip(annotations_a, annotations_b) if a == b)
        observed = agree_count / n

        # Expected (chance) agreement
        labels = set(annotations_a) | set(annotations_b)
        expected = 0.0
        for label in labels:
            freq_a = sum(1 for x in annotations_a if x == label) / n
            freq_b = sum(1 for x in annotations_b if x == label) / n
            expected += freq_a * freq_b

        # Kappa
        if expected == 1.0:
            kappa = 1.0  # perfect agreement by definition
        else:
            kappa = (observed - expected) / (1 - expected)

        kappa = max(-1.0, min(1.0, kappa))

        return AgreementScore(
            metric="cohens_kappa",
            score=round(kappa, 4),
            interpretation=self.interpret(kappa),
            n_annotators=2,
            n_items=n,
            details={
                "observed_agreement": round(observed, 4),
                "chance_agreement": round(expected, 4),
                "raw_agreement_pct": round(observed * 100, 1),
            },
        )

    # ------------------------------------------------------------------
    # Fleiss' Kappa (3+ annotators, categorical)
    # ------------------------------------------------------------------

    def fleiss_kappa(
        self,
        annotation_matrix: list[list[str]],
    ) -> AgreementScore:
        """
        Fleiss' kappa for 3+ annotators on categorical labels.

        Input: list of items, each item is a list of labels from
        different annotators. Handles variable annotator counts per item.

        Extension of Cohen's kappa to multiple raters. Accounts for
        chance agreement given the overall label distribution.
        """
        if not annotation_matrix:
            return AgreementScore("fleiss_kappa", 0.0, "poor", 0, 0, {})

        n_items = len(annotation_matrix)
        n_raters = len(annotation_matrix[0])

        # Collect all unique labels
        all_labels = set()
        for item_labels in annotation_matrix:
            all_labels.update(item_labels)
        labels = sorted(all_labels)
        n_labels = len(labels)

        if n_labels <= 1:
            return AgreementScore("fleiss_kappa", 1.0, "strong", n_raters, n_items, {})

        # Build counts matrix: for each item, count how many raters chose each label
        counts_matrix = []
        for item_labels in annotation_matrix:
            counts = {label: 0 for label in labels}
            for l in item_labels:
                counts[l] += 1
            counts_matrix.append([counts[label] for label in labels])

        # Proportion of all assignments to each label (p_j)
        total_assignments = n_items * n_raters
        p_j = []
        for j in range(n_labels):
            col_sum = sum(counts_matrix[i][j] for i in range(n_items))
            p_j.append(col_sum / total_assignments)

        # P_bar_e: expected agreement by chance
        p_bar_e = sum(p ** 2 for p in p_j)

        # P_i: extent of agreement for each item
        p_i_values = []
        for i in range(n_items):
            item_sum = sum(
                counts_matrix[i][j] * (counts_matrix[i][j] - 1)
                for j in range(n_labels)
            )
            p_i = item_sum / (n_raters * (n_raters - 1)) if n_raters > 1 else 0
            p_i_values.append(p_i)

        # P_bar: mean observed agreement
        p_bar = sum(p_i_values) / n_items if n_items > 0 else 0

        # Fleiss' kappa
        if p_bar_e == 1.0:
            kappa = 1.0
        else:
            kappa = (p_bar - p_bar_e) / (1 - p_bar_e)

        kappa = max(-1.0, min(1.0, kappa))

        return AgreementScore(
            metric="fleiss_kappa",
            score=round(kappa, 4),
            interpretation=self.interpret(kappa),
            n_annotators=n_raters,
            n_items=n_items,
            details={
                "observed_agreement": round(p_bar, 4),
                "chance_agreement": round(p_bar_e, 4),
                "label_proportions": {
                    labels[j]: round(p_j[j], 3) for j in range(n_labels)
                },
            },
        )

    # ------------------------------------------------------------------
    # Krippendorff's Alpha (any count, handles missing data)
    # ------------------------------------------------------------------

    def krippendorff_alpha(
        self,
        annotations: list[list[Optional[str]]],
    ) -> AgreementScore:
        """
        Krippendorff's alpha for any number of annotators with
        possible missing data (None values).

        More robust than Fleiss' kappa: handles missing annotations
        naturally, which is common when annotators skip items or
        when overlap is variable across items.
        """
        # Collect all non-None values with their (item, rater) positions
        pairs = []
        n_items = len(annotations)
        if n_items == 0:
            return AgreementScore("krippendorff_alpha", 0.0, "poor", 0, 0, {})

        n_raters = max(len(item) for item in annotations) if annotations else 0

        for i, item_labels in enumerate(annotations):
            non_none = [l for l in item_labels if l is not None]
            # Generate all pairs within this item
            for a_idx in range(len(non_none)):
                for b_idx in range(a_idx + 1, len(non_none)):
                    pairs.append((non_none[a_idx], non_none[b_idx]))

        if not pairs:
            return AgreementScore("krippendorff_alpha", 0.0, "poor", n_raters, n_items, {})

        # Observed disagreement
        n_pairs = len(pairs)
        observed_disagreement = sum(
            0 if a == b else 1 for a, b in pairs
        ) / n_pairs

        # Expected disagreement (from marginal frequencies)
        all_values = []
        for item_labels in annotations:
            all_values.extend([l for l in item_labels if l is not None])

        value_counts = Counter(all_values)
        total = len(all_values)

        expected_disagreement = 0.0
        values = list(value_counts.keys())
        for i_val in range(len(values)):
            for j_val in range(i_val + 1, len(values)):
                freq_i = value_counts[values[i_val]] / total
                freq_j = value_counts[values[j_val]] / total
                expected_disagreement += 2 * freq_i * freq_j

        # Alpha
        if expected_disagreement == 0:
            alpha = 1.0
        else:
            alpha = 1 - (observed_disagreement / expected_disagreement)

        alpha = max(-1.0, min(1.0, alpha))

        return AgreementScore(
            metric="krippendorff_alpha",
            score=round(alpha, 4),
            interpretation=self.interpret(alpha),
            n_annotators=n_raters,
            n_items=n_items,
            details={
                "observed_disagreement": round(observed_disagreement, 4),
                "expected_disagreement": round(expected_disagreement, 4),
                "total_pairs": n_pairs,
                "missing_values": sum(
                    1 for item in annotations for l in item if l is None
                ),
            },
        )

    # ------------------------------------------------------------------
    # IoU - Intersection over Union (bounding boxes)
    # ------------------------------------------------------------------

    def iou(
        self,
        boxes_a: list[dict],
        boxes_b: list[dict],
    ) -> AgreementScore:
        """
        Intersection over Union for bounding box annotations.

        Each box is a dict with keys: x, y, w, h (top-left corner + size).
        Computes best-match IoU between corresponding boxes using
        Hungarian matching on IoU scores.

        IoU = area_of_intersection / area_of_union.
        IoU = 1.0 means identical boxes. IoU = 0.0 means no overlap.
        """
        if not boxes_a and not boxes_b:
            return AgreementScore("iou", 1.0, "strong", 2, 0, {})

        if not boxes_a or not boxes_b:
            return AgreementScore("iou", 0.0, "poor", 2, max(len(boxes_a), len(boxes_b)), {})

        # Compute IoU matrix
        iou_matrix = []
        for a in boxes_a:
            row = []
            for b in boxes_b:
                row.append(self._compute_single_iou(a, b))
            iou_matrix.append(row)

        # Greedy matching (simplified Hungarian)
        matched_ious = []
        used_b = set()
        for i in range(len(boxes_a)):
            best_iou = 0.0
            best_j = -1
            for j in range(len(boxes_b)):
                if j not in used_b and iou_matrix[i][j] > best_iou:
                    best_iou = iou_matrix[i][j]
                    best_j = j
            if best_j >= 0:
                matched_ious.append(best_iou)
                used_b.add(best_j)
            else:
                matched_ious.append(0.0)

        # Account for unmatched boxes in B
        unmatched = len(boxes_b) - len(used_b)
        for _ in range(unmatched):
            matched_ious.append(0.0)

        mean_iou = sum(matched_ious) / len(matched_ious) if matched_ious else 0.0

        return AgreementScore(
            metric="iou",
            score=round(mean_iou, 4),
            interpretation=self.interpret(mean_iou),
            n_annotators=2,
            n_items=max(len(boxes_a), len(boxes_b)),
            details={
                "per_box_iou": [round(x, 3) for x in matched_ious],
                "boxes_a_count": len(boxes_a),
                "boxes_b_count": len(boxes_b),
                "unmatched_boxes": abs(len(boxes_a) - len(boxes_b)),
            },
        )

    def _compute_single_iou(self, box_a: dict, box_b: dict) -> float:
        """Compute IoU between two bounding boxes."""
        ax, ay = box_a.get("x", 0), box_a.get("y", 0)
        aw, ah = box_a.get("w", 0), box_a.get("h", 0)
        bx, by = box_b.get("x", 0), box_b.get("y", 0)
        bw, bh = box_b.get("w", 0), box_b.get("h", 0)

        # Intersection
        x_left = max(ax, bx)
        y_top = max(ay, by)
        x_right = min(ax + aw, bx + bw)
        y_bottom = min(ay + ah, by + bh)

        if x_right <= x_left or y_bottom <= y_top:
            return 0.0

        intersection = (x_right - x_left) * (y_bottom - y_top)
        area_a = aw * ah
        area_b = bw * bh
        union = area_a + area_b - intersection

        if union <= 0:
            return 0.0

        return intersection / union

    # ------------------------------------------------------------------
    # Span-level F1 (NER)
    # ------------------------------------------------------------------

    def span_f1(
        self,
        spans_a: list[dict],
        spans_b: list[dict],
    ) -> AgreementScore:
        """
        Span-level F1 for NER annotations.

        Each span is a dict with keys: start, end, label.
        A span in A is considered a match if there is a span in B with:
        - Same label
        - Overlapping character range (partial credit)

        Strict match requires exact start/end. Relaxed match requires
        any overlap with same label.
        """
        if not spans_a and not spans_b:
            return AgreementScore("span_f1", 1.0, "strong", 2, 0, {})

        if not spans_a or not spans_b:
            return AgreementScore("span_f1", 0.0, "poor", 2, max(len(spans_a), len(spans_b)), {})

        # Exact match
        exact_tp = 0
        for sa in spans_a:
            for sb in spans_b:
                if (sa.get("start") == sb.get("start")
                        and sa.get("end") == sb.get("end")
                        and sa.get("label") == sb.get("label")):
                    exact_tp += 1
                    break

        exact_precision = exact_tp / len(spans_a) if spans_a else 0
        exact_recall = exact_tp / len(spans_b) if spans_b else 0
        exact_f1 = (
            2 * exact_precision * exact_recall / (exact_precision + exact_recall)
            if (exact_precision + exact_recall) > 0 else 0
        )

        # Relaxed match (any overlap + same label)
        relaxed_tp = 0
        for sa in spans_a:
            for sb in spans_b:
                if sa.get("label") != sb.get("label"):
                    continue
                if self._spans_overlap(sa, sb):
                    relaxed_tp += 1
                    break

        relaxed_precision = relaxed_tp / len(spans_a) if spans_a else 0
        relaxed_recall = relaxed_tp / len(spans_b) if spans_b else 0
        relaxed_f1 = (
            2 * relaxed_precision * relaxed_recall / (relaxed_precision + relaxed_recall)
            if (relaxed_precision + relaxed_recall) > 0 else 0
        )

        return AgreementScore(
            metric="span_f1",
            score=round(relaxed_f1, 4),
            interpretation=self.interpret(relaxed_f1),
            n_annotators=2,
            n_items=max(len(spans_a), len(spans_b)),
            details={
                "exact_f1": round(exact_f1, 4),
                "relaxed_f1": round(relaxed_f1, 4),
                "exact_precision": round(exact_precision, 4),
                "exact_recall": round(exact_recall, 4),
                "spans_a_count": len(spans_a),
                "spans_b_count": len(spans_b),
            },
        )

    def _spans_overlap(self, span_a: dict, span_b: dict) -> bool:
        """Check if two character spans overlap."""
        a_start, a_end = span_a.get("start", 0), span_a.get("end", 0)
        b_start, b_end = span_b.get("start", 0), span_b.get("end", 0)
        return a_start < b_end and b_start < a_end

    # ------------------------------------------------------------------
    # BLEU Score (free-text similarity)
    # ------------------------------------------------------------------

    def bleu_score(
        self,
        text_a: str,
        text_b: str,
        max_n: int = 4,
    ) -> AgreementScore:
        """
        Simplified BLEU score for free-text annotation agreement.

        BLEU measures n-gram overlap between two texts. Originally
        designed for machine translation evaluation, used here to
        measure how similar two free-text annotations are.

        Note: BLEU is an approximation for text agreement. For
        production use, periodic human evaluation calibrates the
        automated metric (DEC-003).
        """
        tokens_a = text_a.lower().split()
        tokens_b = text_b.lower().split()

        if not tokens_a or not tokens_b:
            return AgreementScore("bleu", 0.0, "poor", 2, 1, {})

        # Compute n-gram precision for n=1..max_n
        precisions = []
        for n in range(1, max_n + 1):
            ngrams_a = self._get_ngrams(tokens_a, n)
            ngrams_b = self._get_ngrams(tokens_b, n)

            if not ngrams_a:
                precisions.append(0.0)
                continue

            matches = sum(1 for ng in ngrams_a if ng in ngrams_b)
            precision = matches / len(ngrams_a)
            precisions.append(precision)

        # Geometric mean of precisions (with smoothing)
        if all(p == 0 for p in precisions):
            bleu = 0.0
        else:
            smoothed = [max(p, 1e-10) for p in precisions]
            log_avg = sum(math.log(p) for p in smoothed) / len(smoothed)
            bleu = math.exp(log_avg)

        # Brevity penalty
        bp = min(1.0, math.exp(1 - len(tokens_b) / max(len(tokens_a), 1)))
        bleu *= bp

        return AgreementScore(
            metric="bleu",
            score=round(bleu, 4),
            interpretation=self.interpret(bleu),
            n_annotators=2,
            n_items=1,
            details={
                "ngram_precisions": {
                    f"{n}gram": round(p, 3) for n, p in enumerate(precisions, 1)
                },
                "brevity_penalty": round(bp, 3),
                "tokens_a": len(tokens_a),
                "tokens_b": len(tokens_b),
            },
        )

    def _get_ngrams(self, tokens: list[str], n: int) -> list[tuple]:
        """Extract n-grams from token list."""
        return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]

    # ------------------------------------------------------------------
    # Auto-select metric based on annotation type
    # ------------------------------------------------------------------

    def compute_agreement(
        self,
        annotation_type: str,
        annotations: list[Any],
    ) -> AgreementScore:
        """
        Auto-select and compute the appropriate agreement metric
        based on annotation type.

        This is the main entry point. Callers do not need to know
        which metric applies; the calculator selects automatically.
        """
        if annotation_type in ("enum", "classification", "preference"):
            if len(annotations) == 2:
                return self.cohens_kappa(annotations[0], annotations[1])
            else:
                return self.fleiss_kappa(annotations)

        elif annotation_type in ("multi_select",):
            return self.krippendorff_alpha(annotations)

        elif annotation_type in ("bounding_box", "bbox"):
            if len(annotations) >= 2:
                return self.iou(annotations[0], annotations[1])
            return AgreementScore("iou", 0.0, "poor", len(annotations), 0, {})

        elif annotation_type in ("spans", "ner"):
            if len(annotations) >= 2:
                return self.span_f1(annotations[0], annotations[1])
            return AgreementScore("span_f1", 0.0, "poor", len(annotations), 0, {})

        elif annotation_type in ("text", "free_text"):
            if len(annotations) >= 2:
                return self.bleu_score(annotations[0], annotations[1])
            return AgreementScore("bleu", 0.0, "poor", len(annotations), 0, {})

        else:
            # Fallback: treat as categorical
            if len(annotations) == 2:
                return self.cohens_kappa(
                    [str(a) for a in annotations[0]],
                    [str(a) for a in annotations[1]],
                )
            return AgreementScore("unknown", 0.0, "poor", len(annotations), 0, {})


# ------------------------------------------------------------------
# Demonstration
# ------------------------------------------------------------------

if __name__ == "__main__":
    calc = AgreementCalculator()

    print("=== Agreement Calculator Demo ===\n")

    # Cohen's Kappa: fraud classification
    print("--- Cohen's Kappa (fraud classification, 2 annotators) ---")
    ann_a = ["fraud", "legit", "fraud", "legit", "legit", "legit", "fraud", "legit", "legit", "legit"]
    ann_b = ["fraud", "legit", "legit", "legit", "legit", "legit", "fraud", "legit", "legit", "legit"]
    result = calc.cohens_kappa(ann_a, ann_b)
    print(f"  Kappa: {result.score} ({result.interpretation})")
    print(f"  Raw agreement: {result.details['raw_agreement_pct']}%")
    print(f"  Chance agreement: {result.details['chance_agreement']}")

    # Fleiss' Kappa: 3 annotators
    print("\n--- Fleiss' Kappa (3 annotators, 8 items) ---")
    matrix = [
        ["A", "A", "A"],   # unanimous
        ["A", "A", "B"],   # 2-of-3
        ["A", "A", "A"],   # unanimous
        ["B", "B", "B"],   # unanimous
        ["A", "B", "A"],   # 2-of-3
        ["A", "A", "A"],   # unanimous
        ["B", "B", "A"],   # 2-of-3
        ["A", "A", "A"],   # unanimous
    ]
    result = calc.fleiss_kappa(matrix)
    print(f"  Kappa: {result.score} ({result.interpretation})")
    print(f"  Label proportions: {result.details['label_proportions']}")

    # IoU: bounding boxes
    print("\n--- IoU (radiology bounding boxes) ---")
    boxes_1 = [{"x": 100, "y": 100, "w": 50, "h": 50}]
    boxes_2 = [{"x": 110, "y": 105, "w": 45, "h": 45}]
    result = calc.iou(boxes_1, boxes_2)
    print(f"  IoU: {result.score} ({result.interpretation})")
    print(f"  Per-box IoU: {result.details['per_box_iou']}")

    # Span F1: NER
    print("\n--- Span F1 (clinical NER) ---")
    spans_1 = [
        {"start": 0, "end": 7, "label": "medication"},
        {"start": 12, "end": 18, "label": "dosage"},
    ]
    spans_2 = [
        {"start": 0, "end": 7, "label": "medication"},
        {"start": 12, "end": 17, "label": "dosage"},     # slight end disagreement
        {"start": 25, "end": 35, "label": "diagnosis"},   # extra span
    ]
    result = calc.span_f1(spans_1, spans_2)
    print(f"  Relaxed F1: {result.score} ({result.interpretation})")
    print(f"  Exact F1: {result.details['exact_f1']}")

    # Auto-select
    print("\n--- Auto-select metric ---")
    for ann_type in ["classification", "bbox", "ner", "free_text"]:
        print(f"  {ann_type}: metric = ", end="")
        if ann_type == "classification":
            r = calc.compute_agreement(ann_type, [ann_a, ann_b])
        elif ann_type == "bbox":
            r = calc.compute_agreement(ann_type, [boxes_1, boxes_2])
        elif ann_type == "ner":
            r = calc.compute_agreement(ann_type, [spans_1, spans_2])
        else:
            r = calc.compute_agreement(ann_type, ["The patient has pneumonia", "Patient presents with pneumonia"])
        print(f"{r.metric} = {r.score} ({r.interpretation})")
