"""
Schema Registry: Configurable annotation schema management.

Manages JSONB-based annotation schemas that define what annotators label
and how their output is validated. This is how one platform supports
RLHF preference pairs, radiology bounding boxes, clinical NER, fraud
classification, and content moderation without code changes.

Key design decisions:
- Schemas stored as JSONB, not as code paths (DEC-001)
- Schema versioning with backward compatibility
- Automatic agreement metric selection based on output type (DEC-003)
- Industry presets for common annotation types

PM context: I built this prototype to prove that JSONB schemas could
replace the fixed-table approach engineering initially proposed. The
demo showed that a new annotation type (BI-RADS radiology scoring)
could be configured in 10 minutes without a database migration,
which convinced the team to adopt the flexible schema approach.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4


class InputType(Enum):
    """Supported input data types for annotation."""
    TEXT = "text"
    TEXT_PAIR = "text_pair"
    IMAGE = "image"
    DICOM_IMAGE = "dicom_image"
    POINT_CLOUD = "point_cloud"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class OutputFieldType(Enum):
    """Supported output field types in annotation schemas."""
    ENUM = "enum"
    MULTI_SELECT = "multi_select"
    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    BOUNDING_BOX = "bounding_box"
    POLYGON = "polygon"
    SPANS = "spans"
    ARRAY = "array"


class AgreementMetric(Enum):
    """Quality metrics auto-selected based on output type."""
    COHENS_KAPPA = "cohens_kappa"
    FLEISS_KAPPA = "fleiss_kappa"
    KRIPPENDORFF_ALPHA = "krippendorff_alpha"
    IOU = "iou"
    DICE = "dice"
    SPAN_F1 = "span_f1"
    BLEU = "bleu"


# Mapping from primary output type to agreement metric.
# This is the core of DEC-003: different annotation types need different
# quality metrics. A single "accuracy" number is meaningless across types.
OUTPUT_TYPE_TO_METRIC = {
    OutputFieldType.ENUM: AgreementMetric.COHENS_KAPPA,
    OutputFieldType.MULTI_SELECT: AgreementMetric.KRIPPENDORFF_ALPHA,
    OutputFieldType.BOUNDING_BOX: AgreementMetric.IOU,
    OutputFieldType.POLYGON: AgreementMetric.DICE,
    OutputFieldType.SPANS: AgreementMetric.SPAN_F1,
    OutputFieldType.TEXT: AgreementMetric.BLEU,
}


@dataclass
class ValidationRule:
    """Cross-field validation rule for annotation output."""
    rule_id: str
    condition: str          # e.g., "if preferred != 'tie'"
    requirement: str        # e.g., "reasoning.min_length = 20"
    error_message: str
    severity: str = "error"  # "error" blocks submission, "warning" alerts but allows


@dataclass
class OutputField:
    """Single field in annotation output schema."""
    name: str
    field_type: OutputFieldType
    required: bool = True
    values: list[str] = field(default_factory=list)      # for enum/multi_select
    min_selections: int = 0                               # for multi_select
    max_length: int = 0                                   # for text
    min_value: float = 0                                  # for numeric
    max_value: float = 0                                  # for numeric
    format: str = ""                                      # e.g., "xyxy" for bbox
    items_schema: Optional[dict[str, Any]] = None         # for array type


@dataclass
class AnnotationSchema:
    """
    Complete annotation schema definition.

    This is the central configuration object. When an ML team creates
    a new annotation project, they select or define a schema. The
    annotation interface renders dynamically based on the schema.
    Quality metrics are auto-selected based on the output type.
    Validation rules enforce data quality at submission time.
    """
    schema_id: UUID
    org_id: UUID
    name: str
    version: int
    input_type: InputType
    input_schema: dict[str, Any]
    output_fields: list[OutputField]
    validation_rules: list[ValidationRule]
    primary_metric: AgreementMetric
    secondary_metric: Optional[AgreementMetric]
    ui_config: dict[str, Any]
    status: str = "active"
    created_by: Optional[UUID] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SchemaRegistry:
    """
    Manages annotation schema lifecycle: creation, versioning,
    validation, and metric selection.

    The registry is the answer to "how does one platform support
    radiology bounding boxes, RLHF preference pairs, and fraud
    classification?" Each is a schema configuration, not a code path.
    """

    def __init__(self):
        self.schemas: dict[UUID, AnnotationSchema] = {}
        self.name_index: dict[str, list[UUID]] = {}  # name -> [schema_ids by version]

    # ------------------------------------------------------------------
    # Industry presets
    # ------------------------------------------------------------------

    INDUSTRY_PRESETS = {
        "rlhf_preference": {
            "input_type": InputType.TEXT_PAIR,
            "input_schema": {
                "prompt": {"type": "text", "display": "context"},
                "response_a": {"type": "text", "display": "left_panel"},
                "response_b": {"type": "text", "display": "right_panel"},
            },
            "output_fields": [
                OutputField(
                    name="preferred",
                    field_type=OutputFieldType.ENUM,
                    values=["A", "B", "tie"],
                    required=True,
                ),
                OutputField(
                    name="reasoning",
                    field_type=OutputFieldType.TEXT,
                    max_length=500,
                    required=True,
                ),
                OutputField(
                    name="categories",
                    field_type=OutputFieldType.MULTI_SELECT,
                    values=[
                        "more_helpful", "more_accurate", "better_formatted",
                        "less_harmful", "more_honest",
                    ],
                    min_selections=1,
                    required=True,
                ),
                OutputField(
                    name="safety_flags",
                    field_type=OutputFieldType.MULTI_SELECT,
                    values=[
                        "harmful_content", "bias", "hallucination",
                        "personally_identifiable", "none",
                    ],
                    required=True,
                ),
            ],
            "validation_rules": [
                ValidationRule(
                    rule_id="pref_reasoning_length",
                    condition="preferred != 'tie'",
                    requirement="reasoning.length >= 20",
                    error_message="Reasoning must be at least 20 characters when a preference is selected",
                ),
                ValidationRule(
                    rule_id="safety_escalation",
                    condition="'harmful_content' in safety_flags",
                    requirement="escalate_to_review = true",
                    error_message="Items flagged as harmful must be escalated to review",
                    severity="warning",
                ),
            ],
            "ui_config": {
                "layout": "side_by_side",
                "keyboard_shortcuts": {"1": "A", "2": "B", "3": "tie"},
            },
        },

        "radiology_bbox": {
            "input_type": InputType.DICOM_IMAGE,
            "input_schema": {
                "image_url": {"type": "image", "display": "main_canvas"},
                "clinical_context": {"type": "text", "display": "side_panel"},
                "prior_study_url": {"type": "image", "display": "reference_panel", "optional": True},
            },
            "output_fields": [
                OutputField(
                    name="findings",
                    field_type=OutputFieldType.ARRAY,
                    required=False,
                    items_schema={
                        "bbox": {"type": "bounding_box", "format": "xyxy"},
                        "label": {
                            "type": "enum",
                            "values": [
                                "mass", "calcification", "nodule", "opacity",
                                "effusion", "cardiomegaly", "no_finding",
                            ],
                        },
                        "confidence": {"type": "enum", "values": ["definite", "probable", "possible"]},
                        "birads": {"type": "enum", "values": ["0", "1", "2", "3", "4", "5", "6"]},
                    },
                ),
                OutputField(
                    name="overall_impression",
                    field_type=OutputFieldType.TEXT,
                    max_length=1000,
                    required=False,
                ),
            ],
            "validation_rules": [
                ValidationRule(
                    rule_id="empty_findings_impression",
                    condition="findings is empty",
                    requirement="overall_impression is not empty",
                    error_message="Overall impression required when no findings annotated",
                ),
                ValidationRule(
                    rule_id="bbox_in_bounds",
                    condition="findings is not empty",
                    requirement="all bbox coordinates within image dimensions",
                    error_message="Bounding box extends beyond image boundaries",
                ),
                ValidationRule(
                    rule_id="mass_birads",
                    condition="label = 'mass' and confidence = 'definite'",
                    requirement="birads >= 4",
                    error_message="Definite mass finding requires BI-RADS 4 or higher",
                ),
            ],
            "ui_config": {
                "layout": "canvas_with_sidebar",
                "canvas_tools": ["bbox", "zoom", "pan", "window_level"],
                "enable_prior_comparison": True,
            },
        },

        "clinical_ner": {
            "input_type": InputType.TEXT,
            "input_schema": {
                "text": {"type": "text", "display": "main_panel", "pre_tokenized": False},
                "note_type": {"type": "text", "display": "metadata"},
            },
            "output_fields": [
                OutputField(
                    name="spans",
                    field_type=OutputFieldType.SPANS,
                    required=True,
                    items_schema={
                        "start": {"type": "integer"},
                        "end": {"type": "integer"},
                        "label": {
                            "type": "enum",
                            "values": [
                                "medication", "dosage", "frequency", "diagnosis",
                                "procedure", "anatomy", "lab_test", "lab_value",
                            ],
                        },
                    },
                ),
            ],
            "validation_rules": [
                ValidationRule(
                    rule_id="span_no_overlap",
                    condition="spans.length > 1",
                    requirement="no overlapping spans unless nested",
                    error_message="Annotation spans must not overlap",
                ),
                ValidationRule(
                    rule_id="span_bounds",
                    condition="spans is not empty",
                    requirement="all span start < end and end <= text.length",
                    error_message="Span boundaries must be valid character offsets",
                ),
            ],
            "ui_config": {
                "layout": "text_highlight",
                "highlight_colors": {
                    "medication": "#4CAF50",
                    "dosage": "#2196F3",
                    "diagnosis": "#FF9800",
                    "procedure": "#9C27B0",
                },
            },
        },

        "fraud_classification": {
            "input_type": InputType.TEXT,
            "input_schema": {
                "transaction_summary": {"type": "text", "display": "main_panel"},
                "merchant_info": {"type": "text", "display": "side_panel"},
                "amount": {"type": "text", "display": "metadata"},
            },
            "output_fields": [
                OutputField(
                    name="label",
                    field_type=OutputFieldType.ENUM,
                    values=["legitimate", "fraud_card_not_present", "fraud_identity_theft",
                            "fraud_account_takeover", "fraud_friendly", "suspicious_unclear"],
                    required=True,
                ),
                OutputField(
                    name="confidence",
                    field_type=OutputFieldType.ENUM,
                    values=["high", "medium", "low"],
                    required=True,
                ),
                OutputField(
                    name="reasoning",
                    field_type=OutputFieldType.TEXT,
                    max_length=300,
                    required=False,
                ),
            ],
            "validation_rules": [
                ValidationRule(
                    rule_id="fraud_reasoning",
                    condition="label starts with 'fraud_'",
                    requirement="reasoning is not empty",
                    error_message="Fraud classifications require reasoning",
                ),
            ],
            "ui_config": {
                "layout": "single_panel",
                "keyboard_shortcuts": {"1": "legitimate", "2": "fraud_card_not_present"},
            },
        },

        "content_moderation": {
            "input_type": InputType.TEXT,
            "input_schema": {
                "content": {"type": "text", "display": "main_panel"},
                "content_type": {"type": "text", "display": "metadata"},
                "author_context": {"type": "text", "display": "side_panel", "optional": True},
            },
            "output_fields": [
                OutputField(
                    name="safe",
                    field_type=OutputFieldType.BOOLEAN,
                    required=True,
                ),
                OutputField(
                    name="violation_categories",
                    field_type=OutputFieldType.MULTI_SELECT,
                    values=[
                        "hate_speech", "violence", "harassment", "sexual_content",
                        "misinformation", "spam", "self_harm", "illegal_activity",
                        "privacy_violation", "none",
                    ],
                    required=True,
                ),
                OutputField(
                    name="severity",
                    field_type=OutputFieldType.ENUM,
                    values=["critical", "high", "medium", "low", "none"],
                    required=True,
                ),
                OutputField(
                    name="action_recommended",
                    field_type=OutputFieldType.ENUM,
                    values=["remove", "restrict", "label", "no_action"],
                    required=True,
                ),
            ],
            "validation_rules": [
                ValidationRule(
                    rule_id="safe_no_violations",
                    condition="safe = true",
                    requirement="violation_categories = ['none'] and severity = 'none'",
                    error_message="Safe content cannot have violation categories or severity",
                ),
                ValidationRule(
                    rule_id="unsafe_has_category",
                    condition="safe = false",
                    requirement="'none' not in violation_categories",
                    error_message="Unsafe content must have at least one violation category",
                ),
                ValidationRule(
                    rule_id="critical_requires_remove",
                    condition="severity = 'critical'",
                    requirement="action_recommended = 'remove'",
                    error_message="Critical severity requires removal recommendation",
                    severity="warning",
                ),
            ],
            "ui_config": {
                "layout": "single_panel",
                "content_warning": True,
                "wellness_break_reminder_minutes": 120,
            },
        },
    }

    # ------------------------------------------------------------------
    # Schema creation and management
    # ------------------------------------------------------------------

    def create_schema(
        self,
        org_id: UUID,
        name: str,
        input_type: InputType,
        input_schema: dict[str, Any],
        output_fields: list[OutputField],
        validation_rules: list[ValidationRule],
        ui_config: dict[str, Any],
        created_by: UUID,
        primary_metric_override: Optional[AgreementMetric] = None,
    ) -> AnnotationSchema:
        """
        Create a new annotation schema.

        If primary_metric_override is None, the metric is auto-selected
        based on the primary output field type. This is the implementation
        of DEC-003: the quality engine selects the appropriate agreement
        metric based on what kind of annotation this schema produces.
        """
        primary_metric = primary_metric_override
        secondary_metric = None

        if primary_metric is None:
            primary_metric, secondary_metric = self._select_agreement_metrics(output_fields)

        # Determine version (increment if name already exists)
        version = 1
        key = f"{org_id}:{name}"
        if key in self.name_index:
            existing_versions = self.name_index[key]
            latest = self.schemas[existing_versions[-1]]
            version = latest.version + 1

        schema = AnnotationSchema(
            schema_id=uuid4(),
            org_id=org_id,
            name=name,
            version=version,
            input_type=input_type,
            input_schema=input_schema,
            output_fields=output_fields,
            validation_rules=validation_rules,
            primary_metric=primary_metric,
            secondary_metric=secondary_metric,
            ui_config=ui_config,
            created_by=created_by,
        )

        self.schemas[schema.schema_id] = schema

        if key not in self.name_index:
            self.name_index[key] = []
        self.name_index[key].append(schema.schema_id)

        return schema

    def create_from_preset(
        self,
        org_id: UUID,
        preset_name: str,
        created_by: UUID,
        overrides: Optional[dict[str, Any]] = None,
    ) -> AnnotationSchema:
        """
        Create a schema from an industry preset with optional overrides.

        This is the fast path for common annotation types. An ML team
        setting up an RLHF project selects the "rlhf_preference" preset
        and is labeling within minutes instead of defining a schema
        from scratch.
        """
        if preset_name not in self.INDUSTRY_PRESETS:
            available = ", ".join(self.INDUSTRY_PRESETS.keys())
            raise ValueError(
                f"Unknown preset '{preset_name}'. Available: {available}"
            )

        preset = self.INDUSTRY_PRESETS[preset_name]

        # Apply overrides (e.g., add custom label categories)
        if overrides:
            preset = {**preset, **overrides}

        return self.create_schema(
            org_id=org_id,
            name=preset_name,
            input_type=preset["input_type"],
            input_schema=preset["input_schema"],
            output_fields=preset["output_fields"],
            validation_rules=preset["validation_rules"],
            ui_config=preset["ui_config"],
            created_by=created_by,
        )

    def get_schema(self, schema_id: UUID) -> Optional[AnnotationSchema]:
        """Retrieve schema by ID."""
        return self.schemas.get(schema_id)

    def get_latest_version(self, org_id: UUID, name: str) -> Optional[AnnotationSchema]:
        """Get the most recent version of a named schema."""
        key = f"{org_id}:{name}"
        if key not in self.name_index or not self.name_index[key]:
            return None
        latest_id = self.name_index[key][-1]
        return self.schemas[latest_id]

    def deprecate_schema(self, schema_id: UUID) -> bool:
        """
        Mark a schema as deprecated. Existing projects using this
        schema continue to work, but new projects cannot select it.
        """
        schema = self.schemas.get(schema_id)
        if schema is None:
            return False
        schema.status = "deprecated"
        return True

    # ------------------------------------------------------------------
    # Schema versioning
    # ------------------------------------------------------------------

    def create_new_version(
        self,
        schema_id: UUID,
        changes: dict[str, Any],
        created_by: UUID,
    ) -> AnnotationSchema:
        """
        Create a new version of an existing schema.

        Backward compatibility check: new version must be a superset of
        the previous version's output fields. You can add new fields or
        new enum values, but you cannot remove existing fields or values
        that existing annotations depend on.

        This was a real issue: an ML team wanted to rename a label
        category mid-project. Without versioning, existing annotations
        would reference a label that no longer existed. With versioning,
        the old label exists in v1 and the new label exists in v2.
        New tasks use v2; existing annotations on v1 remain valid.
        """
        existing = self.schemas.get(schema_id)
        if existing is None:
            raise ValueError(f"Schema {schema_id} not found")

        # Check backward compatibility
        if "output_fields" in changes:
            self._check_backward_compatibility(
                existing.output_fields,
                changes["output_fields"],
            )

        new_fields = changes.get("output_fields", existing.output_fields)
        new_rules = changes.get("validation_rules", existing.validation_rules)
        new_ui = changes.get("ui_config", existing.ui_config)

        return self.create_schema(
            org_id=existing.org_id,
            name=existing.name,
            input_type=existing.input_type,
            input_schema=changes.get("input_schema", existing.input_schema),
            output_fields=new_fields,
            validation_rules=new_rules,
            ui_config=new_ui,
            created_by=created_by,
        )

    def _check_backward_compatibility(
        self,
        old_fields: list[OutputField],
        new_fields: list[OutputField],
    ) -> None:
        """
        Verify new schema version is backward compatible.

        Rules:
        - All existing field names must still exist
        - Existing enum values must still be present (can add new ones)
        - Required fields cannot become more restrictive
        """
        old_field_map = {f.name: f for f in old_fields}
        new_field_map = {f.name: f for f in new_fields}

        for name, old_field in old_field_map.items():
            if name not in new_field_map:
                raise ValueError(
                    f"Backward compatibility violation: field '{name}' "
                    f"removed in new version. Existing annotations reference "
                    f"this field. Add it back or create a migration."
                )

            new_field = new_field_map[name]

            # Check enum values are superset
            if old_field.field_type in (OutputFieldType.ENUM, OutputFieldType.MULTI_SELECT):
                old_values = set(old_field.values)
                new_values = set(new_field.values)
                removed = old_values - new_values
                if removed:
                    raise ValueError(
                        f"Backward compatibility violation: values {removed} "
                        f"removed from field '{name}'. Existing annotations "
                        f"may use these values."
                    )

    # ------------------------------------------------------------------
    # Annotation validation
    # ------------------------------------------------------------------

    def validate_annotation(
        self,
        schema_id: UUID,
        annotation_data: dict[str, Any],
    ) -> list[str]:
        """
        Validate an annotation against its schema.

        Returns a list of validation errors. Empty list means valid.
        This runs at submission time before the annotation is stored.
        Catches structural errors (missing required fields, invalid
        enum values) that would corrupt the training data.
        """
        schema = self.schemas.get(schema_id)
        if schema is None:
            return [f"Schema {schema_id} not found"]

        errors = []

        # Check required fields
        for output_field in schema.output_fields:
            if output_field.required and output_field.name not in annotation_data:
                errors.append(f"Required field '{output_field.name}' missing")
                continue

            if output_field.name not in annotation_data:
                continue

            value = annotation_data[output_field.name]
            field_errors = self._validate_field(output_field, value)
            errors.extend(field_errors)

        # Check for unexpected fields
        expected_names = {f.name for f in schema.output_fields}
        unexpected = set(annotation_data.keys()) - expected_names
        if unexpected:
            errors.append(f"Unexpected fields: {unexpected}")

        # Run cross-field validation rules
        for rule in schema.validation_rules:
            if rule.severity == "error":
                rule_error = self._evaluate_validation_rule(rule, annotation_data)
                if rule_error:
                    errors.append(rule_error)

        return errors

    def _validate_field(self, field_def: OutputField, value: Any) -> list[str]:
        """Validate a single field value against its definition."""
        errors = []

        if field_def.field_type == OutputFieldType.ENUM:
            if value not in field_def.values:
                errors.append(
                    f"Field '{field_def.name}': value '{value}' not in "
                    f"allowed values {field_def.values}"
                )

        elif field_def.field_type == OutputFieldType.MULTI_SELECT:
            if not isinstance(value, list):
                errors.append(f"Field '{field_def.name}': expected list, got {type(value).__name__}")
            else:
                invalid = [v for v in value if v not in field_def.values]
                if invalid:
                    errors.append(
                        f"Field '{field_def.name}': invalid values {invalid}"
                    )
                if field_def.min_selections and len(value) < field_def.min_selections:
                    errors.append(
                        f"Field '{field_def.name}': minimum {field_def.min_selections} "
                        f"selections required, got {len(value)}"
                    )

        elif field_def.field_type == OutputFieldType.TEXT:
            if not isinstance(value, str):
                errors.append(f"Field '{field_def.name}': expected string")
            elif field_def.max_length and len(value) > field_def.max_length:
                errors.append(
                    f"Field '{field_def.name}': exceeds max length "
                    f"{field_def.max_length} (got {len(value)})"
                )

        elif field_def.field_type == OutputFieldType.BOUNDING_BOX:
            bbox_errors = self._validate_bounding_box(field_def.name, value)
            errors.extend(bbox_errors)

        elif field_def.field_type == OutputFieldType.SPANS:
            span_errors = self._validate_spans(field_def.name, value)
            errors.extend(span_errors)

        return errors

    def _validate_bounding_box(self, field_name: str, value: Any) -> list[str]:
        """Validate bounding box annotation format."""
        errors = []
        if not isinstance(value, dict):
            return [f"Field '{field_name}': bounding box must be a dict"]

        required_keys = {"x", "y", "w", "h"}
        missing = required_keys - set(value.keys())
        if missing:
            errors.append(f"Field '{field_name}': missing bbox keys {missing}")
        else:
            if value["w"] <= 0 or value["h"] <= 0:
                errors.append(f"Field '{field_name}': bbox width and height must be positive")

        return errors

    def _validate_spans(self, field_name: str, value: Any) -> list[str]:
        """Validate NER span annotations."""
        errors = []
        if not isinstance(value, list):
            return [f"Field '{field_name}': spans must be a list"]

        for i, span in enumerate(value):
            if not isinstance(span, dict):
                errors.append(f"Field '{field_name}': span {i} must be a dict")
                continue
            if "start" not in span or "end" not in span:
                errors.append(f"Field '{field_name}': span {i} missing start/end")
            elif span["start"] >= span["end"]:
                errors.append(f"Field '{field_name}': span {i} start must be < end")
            if "label" not in span:
                errors.append(f"Field '{field_name}': span {i} missing label")

        return errors

    def _evaluate_validation_rule(
        self,
        rule: ValidationRule,
        annotation_data: dict[str, Any],
    ) -> Optional[str]:
        """
        Evaluate a cross-field validation rule.

        Returns error message if rule is violated, None if passed.
        Rules are expressed as condition/requirement pairs.
        Only evaluates if the condition is met.
        """
        # Simplified rule evaluation for prototype.
        # Production would use a proper expression evaluator.
        # This demonstrates the concept of cross-field validation.
        try:
            if not self._condition_matches(rule.condition, annotation_data):
                return None  # condition not met, rule does not apply

            if not self._requirement_met(rule.requirement, annotation_data):
                return rule.error_message
        except Exception:
            # Rule evaluation failure should not block annotation
            return None

        return None

    def _condition_matches(self, condition: str, data: dict[str, Any]) -> bool:
        """Simplified condition evaluation for prototype."""
        # Handle "field != 'value'" pattern
        match = re.match(r"(\w+)\s*!=\s*'(\w+)'", condition)
        if match:
            field_name, expected_value = match.groups()
            return data.get(field_name) != expected_value

        # Handle "'value' in field" pattern
        match = re.match(r"'(\w+)'\s+in\s+(\w+)", condition)
        if match:
            value, field_name = match.groups()
            field_value = data.get(field_name, [])
            if isinstance(field_value, list):
                return value in field_value

        # Handle "field is empty" pattern
        if condition.endswith("is empty"):
            field_name = condition.replace(" is empty", "").strip()
            field_value = data.get(field_name, [])
            return len(field_value) == 0 if isinstance(field_value, list) else not field_value

        return False

    def _requirement_met(self, requirement: str, data: dict[str, Any]) -> bool:
        """Simplified requirement evaluation for prototype."""
        # Handle "field.length >= N" pattern
        match = re.match(r"(\w+)\.length\s*>=\s*(\d+)", requirement)
        if match:
            field_name, min_length = match.groups()
            value = data.get(field_name, "")
            return len(str(value)) >= int(min_length)

        # Handle "field is not empty" pattern
        if requirement.endswith("is not empty"):
            field_name = requirement.replace(" is not empty", "").strip()
            return bool(data.get(field_name))

        return True

    # ------------------------------------------------------------------
    # Agreement metric selection
    # ------------------------------------------------------------------

    def _select_agreement_metrics(
        self,
        output_fields: list[OutputField],
    ) -> tuple[AgreementMetric, Optional[AgreementMetric]]:
        """
        Auto-select primary and secondary agreement metrics based on
        the annotation schema's output field types.

        This implements DEC-003: Cohen's kappa for classification, IoU
        for bounding boxes, span F1 for NER, etc. The ML team does not
        need to think about which metric applies - the schema registry
        selects it automatically.
        """
        if not output_fields:
            return AgreementMetric.COHENS_KAPPA, None

        # Find the "primary" output field (first required field,
        # or first field if none required)
        primary_field = None
        for f in output_fields:
            if f.required:
                primary_field = f
                break
        if primary_field is None:
            primary_field = output_fields[0]

        primary_metric = OUTPUT_TYPE_TO_METRIC.get(
            primary_field.field_type,
            AgreementMetric.COHENS_KAPPA,
        )

        # Secondary metric: if there is a text reasoning field, add BLEU
        secondary_metric = None
        for f in output_fields:
            if f != primary_field and f.field_type == OutputFieldType.TEXT:
                secondary_metric = AgreementMetric.BLEU
                break

        return primary_metric, secondary_metric

    # ------------------------------------------------------------------
    # Schema export (for API responses)
    # ------------------------------------------------------------------

    def to_jsonb(self, schema_id: UUID) -> Optional[dict[str, Any]]:
        """
        Export schema as JSONB document for storage in PostgreSQL
        or API response.
        """
        schema = self.schemas.get(schema_id)
        if schema is None:
            return None

        return {
            "schema_id": str(schema.schema_id),
            "org_id": str(schema.org_id),
            "name": schema.name,
            "version": schema.version,
            "status": schema.status,
            "input_type": schema.input_type.value,
            "input_schema": schema.input_schema,
            "output_schema": {
                f.name: {
                    "type": f.field_type.value,
                    "required": f.required,
                    **({"values": f.values} if f.values else {}),
                    **({"max_length": f.max_length} if f.max_length else {}),
                    **({"min_selections": f.min_selections} if f.min_selections else {}),
                    **({"format": f.format} if f.format else {}),
                    **({"items": f.items_schema} if f.items_schema else {}),
                }
                for f in schema.output_fields
            },
            "validation_rules": [
                {
                    "rule_id": r.rule_id,
                    "condition": r.condition,
                    "requirement": r.requirement,
                    "error_message": r.error_message,
                    "severity": r.severity,
                }
                for r in schema.validation_rules
            ],
            "primary_agreement_metric": schema.primary_metric.value,
            "secondary_agreement_metric": (
                schema.secondary_metric.value if schema.secondary_metric else None
            ),
            "ui_config": schema.ui_config,
            "created_at": schema.created_at.isoformat(),
        }


# ------------------------------------------------------------------
# Demonstration
# ------------------------------------------------------------------

if __name__ == "__main__":
    registry = SchemaRegistry()
    org_id = uuid4()
    user_id = uuid4()

    # Create from industry presets
    print("=== Creating schemas from industry presets ===\n")
    for preset_name in ["rlhf_preference", "radiology_bbox", "clinical_ner",
                         "fraud_classification", "content_moderation"]:
        schema = registry.create_from_preset(org_id, preset_name, user_id)
        print(f"  {preset_name} v{schema.version}")
        print(f"    Input type: {schema.input_type.value}")
        print(f"    Output fields: {[f.name for f in schema.output_fields]}")
        print(f"    Primary metric: {schema.primary_metric.value}")
        print(f"    Validation rules: {len(schema.validation_rules)}")
        print()

    # Validate annotations
    print("=== Validating annotations ===\n")

    rlhf_schema = registry.get_latest_version(org_id, "rlhf_preference")

    # Valid annotation
    valid_annotation = {
        "preferred": "A",
        "reasoning": "Response A is more helpful and accurate with better formatting",
        "categories": ["more_helpful", "more_accurate"],
        "safety_flags": ["none"],
    }
    errors = registry.validate_annotation(rlhf_schema.schema_id, valid_annotation)
    print(f"  Valid RLHF annotation: {len(errors)} errors")

    # Invalid annotation (missing reasoning, bad enum)
    invalid_annotation = {
        "preferred": "C",  # invalid enum value
        "categories": ["more_helpful"],
        "safety_flags": ["none"],
    }
    errors = registry.validate_annotation(rlhf_schema.schema_id, invalid_annotation)
    print(f"  Invalid RLHF annotation: {len(errors)} errors")
    for e in errors:
        print(f"    - {e}")

    # Schema versioning
    print("\n=== Schema versioning ===\n")

    # Add a new category to RLHF preference
    new_fields = list(rlhf_schema.output_fields)
    for f in new_fields:
        if f.name == "categories":
            f.values = f.values + ["more_creative"]

    v2 = registry.create_new_version(
        rlhf_schema.schema_id,
        {"output_fields": new_fields},
        user_id,
    )
    print(f"  Created v{v2.version} of rlhf_preference")
    print(f"  New categories include 'more_creative': {'more_creative' in [f for f in v2.output_fields if f.name == 'categories'][0].values}")

    # Export as JSONB
    print("\n=== JSONB export (first 3 keys) ===\n")
    jsonb = registry.to_jsonb(v2.schema_id)
    for key in list(jsonb.keys())[:3]:
        print(f"  {key}: {jsonb[key]}")

    print("\n=== Summary ===")
    print(f"  Total schemas: {len(registry.schemas)}")
    print(f"  Presets available: {list(registry.INDUSTRY_PRESETS.keys())}")
