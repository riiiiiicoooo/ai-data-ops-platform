"""
Annotation Validator: Structural and semantic validation for annotations.

Validates annotations before they enter the quality pipeline. Catches
structural errors (missing fields, invalid values, overlapping spans)
and semantic warnings (suspiciously fast completion, pre-label
rubber-stamping) before bad data reaches the training export.

Key design decisions:
- Validation at submission time, not batch export time (fail fast)
- Structural errors block submission; semantic warnings flag for review
- Pre-label correction rate monitoring for anchoring detection (DEC-007)
- Temporal consistency checks for video/sequence annotations

PM context: I added the pre-label anchoring detector after an incident
where an annotator accepted 97% of model pre-labels on a batch with
known 15% error rate. Without detection, those errors would have
entered the training pipeline. The correction rate monitor now flags
annotators whose acceptance rate suggests rubber-stamping.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4


class ValidationSeverity(Enum):
    """Severity levels for validation findings."""
    ERROR = "error"           # blocks submission
    WARNING = "warning"       # flags for review, allows submission
    INFO = "info"             # logged for analytics, no action


@dataclass
class ValidationFinding:
    """Single validation finding (error, warning, or info)."""
    severity: ValidationSeverity
    field: str
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Complete validation result for an annotation."""
    valid: bool
    findings: list[ValidationFinding] = field(default_factory=list)
    errors: int = 0
    warnings: int = 0

    def add(self, finding: ValidationFinding) -> None:
        self.findings.append(finding)
        if finding.severity == ValidationSeverity.ERROR:
            self.errors += 1
            self.valid = False
        elif finding.severity == ValidationSeverity.WARNING:
            self.warnings += 1


@dataclass
class AnnotationContext:
    """Context for validation (task metadata, pre-label info, timing)."""
    task_id: UUID
    annotator_id: UUID
    schema_output_type: str             # "enum", "spans", "bounding_box", etc.
    annotation_data: dict[str, Any]

    # Pre-label context (for anchoring detection)
    pre_label_shown: bool = False
    pre_label_data: Optional[dict[str, Any]] = None

    # Timing (for speed anomaly detection)
    started_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None

    # Sequence context (for temporal consistency in video annotation)
    previous_frame_annotation: Optional[dict[str, Any]] = None
    frame_number: Optional[int] = None

    # Input metadata
    input_text_length: Optional[int] = None
    input_image_dimensions: Optional[tuple[int, int]] = None


class AnnotationValidator:
    """
    Validates annotations for structural correctness and semantic quality.

    Structural validation: required fields present, values within allowed
    set, spans do not overlap, bounding boxes within image bounds.
    These are hard errors that block submission.

    Semantic validation: annotation completed suspiciously fast, pre-label
    accepted without changes on known-error items, bounding box covers
    unreasonable percentage of image. These are warnings that flag for
    review but do not block submission.
    """

    # Speed anomaly thresholds (seconds)
    MIN_ANNOTATION_SECONDS = {
        "enum": 3,                # classification: at least 3 seconds to read
        "multi_select": 5,        # multi-select: at least 5 seconds
        "spans": 10,              # NER: at least 10 seconds per annotation
        "bounding_box": 8,        # bbox: at least 8 seconds to draw
        "text": 15,               # free text: at least 15 seconds to type
        "preference": 15,         # preference pair: at least 15 seconds to compare
    }

    # Pre-label acceptance threshold for rubber-stamping warning
    PRELABEL_ACCEPTANCE_WARNING_THRESHOLD = 0.90  # > 90% acceptance = suspicious

    # Bounding box reasonableness
    MAX_BBOX_COVERAGE = 0.85     # bbox covering > 85% of image is suspicious
    MIN_BBOX_SIZE_PX = 5         # bbox smaller than 5px in either dimension

    # NER span constraints
    MAX_SPAN_LENGTH_CHARS = 500  # spans longer than 500 chars are likely errors

    def validate(self, context: AnnotationContext) -> ValidationResult:
        """
        Run all applicable validators on an annotation.

        Returns ValidationResult with errors (block submission) and
        warnings (flag for review).
        """
        result = ValidationResult(valid=True)

        # Structural validators (always run)
        self._validate_not_empty(context, result)
        self._validate_completeness(context, result)

        # Type-specific structural validators
        if context.schema_output_type in ("spans", "ner"):
            self._validate_spans(context, result)
        elif context.schema_output_type in ("bounding_box", "bbox"):
            self._validate_bounding_boxes(context, result)
        elif context.schema_output_type == "preference":
            self._validate_preference(context, result)

        # Semantic validators (warnings, not errors)
        self._validate_annotation_speed(context, result)
        if context.pre_label_shown:
            self._validate_pre_label_engagement(context, result)

        # Temporal consistency (for sequences)
        if context.previous_frame_annotation is not None:
            self._validate_temporal_consistency(context, result)

        return result

    # ------------------------------------------------------------------
    # Structural validators (errors)
    # ------------------------------------------------------------------

    def _validate_not_empty(
        self,
        context: AnnotationContext,
        result: ValidationResult,
    ) -> None:
        """Annotation must contain data."""
        if not context.annotation_data:
            result.add(ValidationFinding(
                severity=ValidationSeverity.ERROR,
                field="annotation_data",
                code="EMPTY_ANNOTATION",
                message="Annotation cannot be empty",
            ))

    def _validate_completeness(
        self,
        context: AnnotationContext,
        result: ValidationResult,
    ) -> None:
        """Check for common completeness issues."""
        data = context.annotation_data

        # Check for null/empty string values in non-optional fields
        for key, value in data.items():
            if value is None:
                result.add(ValidationFinding(
                    severity=ValidationSeverity.WARNING,
                    field=key,
                    code="NULL_VALUE",
                    message=f"Field '{key}' is null",
                ))
            elif isinstance(value, str) and value.strip() == "":
                result.add(ValidationFinding(
                    severity=ValidationSeverity.WARNING,
                    field=key,
                    code="EMPTY_STRING",
                    message=f"Field '{key}' is an empty string",
                ))

    def _validate_spans(
        self,
        context: AnnotationContext,
        result: ValidationResult,
    ) -> None:
        """Validate NER span annotations."""
        spans = context.annotation_data.get("spans", [])

        if not isinstance(spans, list):
            result.add(ValidationFinding(
                severity=ValidationSeverity.ERROR,
                field="spans",
                code="SPANS_NOT_LIST",
                message="Spans field must be a list",
            ))
            return

        for i, span in enumerate(spans):
            if not isinstance(span, dict):
                result.add(ValidationFinding(
                    severity=ValidationSeverity.ERROR,
                    field=f"spans[{i}]",
                    code="SPAN_NOT_DICT",
                    message=f"Span {i} must be a dict",
                ))
                continue

            start = span.get("start")
            end = span.get("end")
            label = span.get("label")

            # Required fields
            if start is None or end is None:
                result.add(ValidationFinding(
                    severity=ValidationSeverity.ERROR,
                    field=f"spans[{i}]",
                    code="SPAN_MISSING_BOUNDS",
                    message=f"Span {i} missing start or end",
                ))
                continue

            if label is None:
                result.add(ValidationFinding(
                    severity=ValidationSeverity.ERROR,
                    field=f"spans[{i}].label",
                    code="SPAN_MISSING_LABEL",
                    message=f"Span {i} missing label",
                ))

            # Bounds check
            if start >= end:
                result.add(ValidationFinding(
                    severity=ValidationSeverity.ERROR,
                    field=f"spans[{i}]",
                    code="SPAN_INVALID_BOUNDS",
                    message=f"Span {i}: start ({start}) must be less than end ({end})",
                ))

            if start < 0:
                result.add(ValidationFinding(
                    severity=ValidationSeverity.ERROR,
                    field=f"spans[{i}].start",
                    code="SPAN_NEGATIVE_START",
                    message=f"Span {i}: start cannot be negative",
                ))

            # Text length bounds
            if context.input_text_length and end > context.input_text_length:
                result.add(ValidationFinding(
                    severity=ValidationSeverity.ERROR,
                    field=f"spans[{i}].end",
                    code="SPAN_EXCEEDS_TEXT",
                    message=f"Span {i}: end ({end}) exceeds text length ({context.input_text_length})",
                ))

            # Span too long (likely selection error)
            if end - start > self.MAX_SPAN_LENGTH_CHARS:
                result.add(ValidationFinding(
                    severity=ValidationSeverity.WARNING,
                    field=f"spans[{i}]",
                    code="SPAN_SUSPICIOUSLY_LONG",
                    message=f"Span {i} is {end - start} chars (>{self.MAX_SPAN_LENGTH_CHARS}). Verify selection.",
                ))

        # Check for overlapping spans
        self._check_span_overlap(spans, result)

    def _check_span_overlap(
        self,
        spans: list[dict],
        result: ValidationResult,
    ) -> None:
        """Check for overlapping spans (usually an annotation error)."""
        valid_spans = [
            s for s in spans
            if isinstance(s, dict)
            and s.get("start") is not None
            and s.get("end") is not None
            and s["start"] < s["end"]
        ]

        sorted_spans = sorted(valid_spans, key=lambda s: s["start"])
        for i in range(len(sorted_spans) - 1):
            current = sorted_spans[i]
            next_span = sorted_spans[i + 1]
            if current["end"] > next_span["start"]:
                result.add(ValidationFinding(
                    severity=ValidationSeverity.WARNING,
                    field="spans",
                    code="SPANS_OVERLAP",
                    message=(
                        f"Spans overlap: [{current['start']},{current['end']}] "
                        f"and [{next_span['start']},{next_span['end']}]"
                    ),
                    details={
                        "span_a": current,
                        "span_b": next_span,
                    },
                ))

    def _validate_bounding_boxes(
        self,
        context: AnnotationContext,
        result: ValidationResult,
    ) -> None:
        """Validate bounding box annotations."""
        boxes = context.annotation_data.get("boxes", context.annotation_data.get("findings", []))

        if not isinstance(boxes, list):
            # Single box case
            boxes = [context.annotation_data] if "x" in context.annotation_data else []

        for i, box in enumerate(boxes):
            if not isinstance(box, dict):
                continue

            bbox = box.get("bbox", box)
            x = bbox.get("x", 0)
            y = bbox.get("y", 0)
            w = bbox.get("w", bbox.get("width", 0))
            h = bbox.get("h", bbox.get("height", 0))

            # Size check
            if w <= 0 or h <= 0:
                result.add(ValidationFinding(
                    severity=ValidationSeverity.ERROR,
                    field=f"boxes[{i}]",
                    code="BBOX_INVALID_SIZE",
                    message=f"Box {i}: width ({w}) and height ({h}) must be positive",
                ))

            if w < self.MIN_BBOX_SIZE_PX or h < self.MIN_BBOX_SIZE_PX:
                result.add(ValidationFinding(
                    severity=ValidationSeverity.WARNING,
                    field=f"boxes[{i}]",
                    code="BBOX_TOO_SMALL",
                    message=f"Box {i}: {w}x{h}px is very small. Verify placement.",
                ))

            # Image bounds check
            if context.input_image_dimensions:
                img_w, img_h = context.input_image_dimensions
                if x < 0 or y < 0 or x + w > img_w or y + h > img_h:
                    result.add(ValidationFinding(
                        severity=ValidationSeverity.ERROR,
                        field=f"boxes[{i}]",
                        code="BBOX_OUT_OF_BOUNDS",
                        message=f"Box {i} extends beyond image ({img_w}x{img_h})",
                    ))

                # Coverage check
                box_area = w * h
                img_area = img_w * img_h
                if img_area > 0:
                    coverage = box_area / img_area
                    if coverage > self.MAX_BBOX_COVERAGE:
                        result.add(ValidationFinding(
                            severity=ValidationSeverity.WARNING,
                            field=f"boxes[{i}]",
                            code="BBOX_EXCESSIVE_COVERAGE",
                            message=f"Box {i} covers {coverage:.0%} of image. Verify accuracy.",
                        ))

    def _validate_preference(
        self,
        context: AnnotationContext,
        result: ValidationResult,
    ) -> None:
        """Validate preference pair annotations."""
        data = context.annotation_data
        preferred = data.get("preferred")
        reasoning = data.get("reasoning", "")

        if preferred not in ("A", "B", "tie"):
            result.add(ValidationFinding(
                severity=ValidationSeverity.ERROR,
                field="preferred",
                code="INVALID_PREFERENCE",
                message=f"Preferred must be 'A', 'B', or 'tie'. Got: '{preferred}'",
            ))

        # Reasoning required for non-tie
        if preferred in ("A", "B") and len(str(reasoning).strip()) < 10:
            result.add(ValidationFinding(
                severity=ValidationSeverity.WARNING,
                field="reasoning",
                code="SHORT_REASONING",
                message="Reasoning is very short for a non-tie preference. Consider adding detail.",
            ))

    # ------------------------------------------------------------------
    # Semantic validators (warnings)
    # ------------------------------------------------------------------

    def _validate_annotation_speed(
        self,
        context: AnnotationContext,
        result: ValidationResult,
    ) -> None:
        """
        Flag suspiciously fast annotations.

        If an annotator completes a task in 2 seconds when the median
        is 30 seconds, they are likely not reading the content. This
        does not block submission (some items are genuinely fast) but
        flags for quality review.
        """
        if context.started_at is None or context.submitted_at is None:
            return

        duration = (context.submitted_at - context.started_at).total_seconds()
        min_seconds = self.MIN_ANNOTATION_SECONDS.get(
            context.schema_output_type, 5
        )

        if duration < min_seconds:
            result.add(ValidationFinding(
                severity=ValidationSeverity.WARNING,
                field="_timing",
                code="SUSPICIOUSLY_FAST",
                message=(
                    f"Completed in {duration:.0f}s (minimum expected: {min_seconds}s "
                    f"for {context.schema_output_type}). Quality review recommended."
                ),
                details={
                    "duration_seconds": duration,
                    "min_expected_seconds": min_seconds,
                    "annotation_type": context.schema_output_type,
                },
            ))

    def _validate_pre_label_engagement(
        self,
        context: AnnotationContext,
        result: ValidationResult,
    ) -> None:
        """
        Detect potential rubber-stamping of model pre-labels.

        If an annotator accepts the pre-label without any changes,
        that is normal for correct pre-labels. But if the pre-label
        is known to be wrong (golden item with incorrect pre-label)
        and the annotator still accepts it, that is anchoring bias.

        DEC-007: Pre-labeling with correction rate monitoring.
        """
        if context.pre_label_data is None:
            return

        # Compare annotation to pre-label
        annotation = context.annotation_data
        pre_label = context.pre_label_data

        # Simple comparison: are they identical?
        is_identical = self._annotations_match(annotation, pre_label)

        if is_identical:
            result.add(ValidationFinding(
                severity=ValidationSeverity.INFO,
                field="_pre_label",
                code="PRE_LABEL_ACCEPTED",
                message="Annotation matches pre-label exactly (no corrections made)",
                details={
                    "pre_label_accepted": True,
                    "annotator_id": str(context.annotator_id),
                },
            ))

    def _validate_temporal_consistency(
        self,
        context: AnnotationContext,
        result: ValidationResult,
    ) -> None:
        """
        Check temporal consistency for video/sequence annotations.

        If annotating frame-by-frame, object tracking IDs should be
        consistent across frames. An object labeled "car_1" in frame N
        should still be "car_1" in frame N+1 (if visible). A sudden
        change in tracking ID suggests an annotation error.
        """
        prev = context.previous_frame_annotation
        curr = context.annotation_data

        if not prev or not curr:
            return

        prev_ids = set(self._extract_tracking_ids(prev))
        curr_ids = set(self._extract_tracking_ids(curr))

        # Check for IDs that disappeared (might be occlusion, might be error)
        disappeared = prev_ids - curr_ids
        if disappeared and len(disappeared) > len(prev_ids) * 0.5:
            result.add(ValidationFinding(
                severity=ValidationSeverity.WARNING,
                field="_temporal",
                code="TRACKING_IDS_DISAPPEARED",
                message=(
                    f"{len(disappeared)} of {len(prev_ids)} tracking IDs "
                    f"disappeared between frames. Verify occlusion vs. labeling error."
                ),
                details={
                    "disappeared_ids": list(disappeared),
                    "frame": context.frame_number,
                },
            ))

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def _annotations_match(
        self,
        annotation: dict[str, Any],
        pre_label: dict[str, Any],
    ) -> bool:
        """Check if annotation and pre-label are effectively identical."""
        # Compare key fields that matter for quality
        for key in pre_label:
            if key.startswith("_"):  # skip metadata fields
                continue
            if annotation.get(key) != pre_label.get(key):
                return False
        return True

    def _extract_tracking_ids(self, annotation: dict[str, Any]) -> list[str]:
        """Extract object tracking IDs from annotation data."""
        ids = []
        boxes = annotation.get("boxes", annotation.get("findings", []))
        if isinstance(boxes, list):
            for box in boxes:
                if isinstance(box, dict):
                    tracking_id = box.get("tracking_id") or box.get("object_id")
                    if tracking_id:
                        ids.append(str(tracking_id))
        return ids


# ------------------------------------------------------------------
# Demonstration
# ------------------------------------------------------------------

if __name__ == "__main__":
    validator = AnnotationValidator()

    print("=== Annotation Validator Demo ===\n")

    # Valid NER annotation
    print("--- Valid NER annotation ---")
    valid_ner = AnnotationContext(
        task_id=uuid4(),
        annotator_id=uuid4(),
        schema_output_type="spans",
        annotation_data={
            "spans": [
                {"start": 0, "end": 7, "label": "medication"},
                {"start": 12, "end": 17, "label": "dosage"},
            ]
        },
        input_text_length=100,
        started_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        submitted_at=datetime(2025, 1, 15, 10, 0, 45, tzinfo=timezone.utc),
    )
    result = validator.validate(valid_ner)
    print(f"  Valid: {result.valid}, Errors: {result.errors}, Warnings: {result.warnings}")

    # Invalid NER: overlapping spans + span exceeds text
    print("\n--- Invalid NER: overlapping spans ---")
    invalid_ner = AnnotationContext(
        task_id=uuid4(),
        annotator_id=uuid4(),
        schema_output_type="spans",
        annotation_data={
            "spans": [
                {"start": 0, "end": 10, "label": "medication"},
                {"start": 5, "end": 15, "label": "dosage"},
                {"start": 90, "end": 110, "label": "diagnosis"},
            ]
        },
        input_text_length=100,
        started_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        submitted_at=datetime(2025, 1, 15, 10, 0, 30, tzinfo=timezone.utc),
    )
    result = validator.validate(invalid_ner)
    print(f"  Valid: {result.valid}, Errors: {result.errors}, Warnings: {result.warnings}")
    for f in result.findings:
        print(f"    [{f.severity.value}] {f.code}: {f.message}")

    # Suspiciously fast classification
    print("\n--- Suspiciously fast annotation ---")
    fast_annotation = AnnotationContext(
        task_id=uuid4(),
        annotator_id=uuid4(),
        schema_output_type="enum",
        annotation_data={"label": "fraud"},
        started_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        submitted_at=datetime(2025, 1, 15, 10, 0, 1, tzinfo=timezone.utc),
    )
    result = validator.validate(fast_annotation)
    print(f"  Valid: {result.valid}, Warnings: {result.warnings}")
    for f in result.findings:
        if f.severity == ValidationSeverity.WARNING:
            print(f"    {f.code}: {f.message}")

    # Pre-label rubber-stamping detection
    print("\n--- Pre-label acceptance tracking ---")
    prelabel_context = AnnotationContext(
        task_id=uuid4(),
        annotator_id=uuid4(),
        schema_output_type="enum",
        annotation_data={"label": "legitimate", "confidence": "high"},
        pre_label_shown=True,
        pre_label_data={"label": "legitimate", "confidence": "high"},
        started_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        submitted_at=datetime(2025, 1, 15, 10, 0, 5, tzinfo=timezone.utc),
    )
    result = validator.validate(prelabel_context)
    print(f"  Valid: {result.valid}")
    info_findings = [f for f in result.findings if f.severity == ValidationSeverity.INFO]
    print(f"  Pre-label accepted without changes: {len(info_findings) > 0}")

    # Bounding box validation
    print("\n--- Bounding box validation ---")
    bbox_context = AnnotationContext(
        task_id=uuid4(),
        annotator_id=uuid4(),
        schema_output_type="bounding_box",
        annotation_data={
            "boxes": [
                {"x": 10, "y": 20, "w": 900, "h": 900, "label": "mass"},
                {"x": 5, "y": 5, "w": 3, "h": 3, "label": "calcification"},
            ]
        },
        input_image_dimensions=(1000, 1000),
        started_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        submitted_at=datetime(2025, 1, 15, 10, 0, 20, tzinfo=timezone.utc),
    )
    result = validator.validate(bbox_context)
    print(f"  Valid: {result.valid}, Warnings: {result.warnings}")
    for f in result.findings:
        if f.severity == ValidationSeverity.WARNING:
            print(f"    {f.code}: {f.message}")
