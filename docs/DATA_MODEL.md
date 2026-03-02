# Data Model: AI Data Operations Platform

**Last Updated:** February 2025

---

## Entity Relationship Overview

```
organizations
    │
    ├──> projects
    │       │
    │       ├──> annotation_schemas (JSONB, versioned)
    │       │
    │       ├──> task_batches
    │       │       │
    │       │       └──> tasks
    │       │               │
    │       │               ├──> annotations (1-5 per task, redundant labeling)
    │       │               │       │
    │       │               │       └──> annotation_versions (change history)
    │       │               │
    │       │               └──> consensus_results (resolved label per task)
    │       │
    │       ├──> golden_sets
    │       │       │
    │       │       └──> golden_items (expert-labeled ground truth)
    │       │
    │       ├──> quality_reports
    │       │
    │       ├──> model_endpoints (for pre-labeling + active learning)
    │       │
    │       └──> exports
    │
    ├──> annotators
    │       │
    │       ├──> annotator_qualifications (per-domain certifications)
    │       │
    │       ├──> annotator_accuracy (rolling accuracy per task type)
    │       │
    │       └──> annotator_sessions (work tracking)
    │
    ├──> users (ml_engineer, annotation_lead, ops_manager, admin)
    │
    └──> audit_log (append-only)

Separate concerns:
    drift_snapshots (production vs. training distribution comparisons)
    active_learning_batches (uncertainty-sampled candidate sets)
    model_training_runs (links annotation batches to model evaluations)
```

---

## Core Schema (PostgreSQL 15)

### organizations

```sql
CREATE TABLE organizations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,
    settings        JSONB NOT NULL DEFAULT '{}',
    -- settings: {
    --   "default_overlap": 3,
    --   "default_golden_rate": 0.05,
    --   "max_annotators": 500,
    --   "compliance_frameworks": ["hipaa", "sox"],
    --   "data_residency": "us-east-1",
    --   "notification_channels": {"slack": "#data-ops", "email": "ops@company.com"}
    -- }
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active       BOOLEAN NOT NULL DEFAULT true
);
```

### projects

```sql
CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    name            TEXT NOT NULL,
    description     TEXT,
    schema_id       UUID NOT NULL REFERENCES annotation_schemas(id),
    status          TEXT NOT NULL DEFAULT 'draft',
    -- draft -> active -> paused -> completed -> archived

    -- Workflow configuration
    workflow_config  JSONB NOT NULL DEFAULT '{}',
    -- {
    --   "stages": 3,                    (1 = label-only, 2 = label+review, 3 = +adjudicate)
    --   "overlap": 3,                   (annotators per task)
    --   "auto_accept_threshold": 0.80,  (agreement above this = skip review)
    --   "consensus_method": "weighted_vote",
    --   "review_sample_rate": 1.0,      (1.0 = review all disagreements, 0.2 = 20% spot-check)
    --   "pre_labeling_enabled": true,
    --   "pre_labeling_confidence_threshold": 0.85
    -- }

    -- Quality configuration
    quality_config   JSONB NOT NULL DEFAULT '{}',
    -- {
    --   "golden_rate": 0.05,
    --   "min_agreement_kappa": 0.75,
    --   "annotator_accuracy_threshold": 0.85,
    --   "dequalification_consecutive_failures": 5,
    --   "bias_detection_std_threshold": 2.0
    -- }

    -- Routing configuration
    routing_config   JSONB NOT NULL DEFAULT '{}',
    -- {
    --   "required_qualifications": ["radiology_certified"],
    --   "min_accuracy": 0.85,
    --   "task_grouping": "by_study",
    --   "reservation_timeout_minutes": 30,
    --   "max_items_per_shift": 200
    -- }

    -- Industry compliance
    compliance_config JSONB NOT NULL DEFAULT '{}',
    -- {
    --   "framework": "hipaa",
    --   "phi_scan_required": true,
    --   "audit_retention_years": 7,
    --   "data_residency": "us-east-1",
    --   "export_requires_approval": true
    -- }

    model_endpoint_id UUID REFERENCES model_endpoints(id),
    created_by       UUID NOT NULL REFERENCES users(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ
);

CREATE INDEX idx_projects_org ON projects(org_id);
CREATE INDEX idx_projects_status ON projects(status) WHERE status = 'active';
```

### annotation_schemas

```sql
CREATE TABLE annotation_schemas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    name            TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'active',  -- active, deprecated

    input_type      TEXT NOT NULL,
    -- "text", "text_pair", "image", "dicom_image", "point_cloud", "video", "audio", "document"

    input_schema    JSONB NOT NULL,             -- defines input fields and display hints
    output_schema   JSONB NOT NULL,             -- defines annotation output structure
    validation_rules JSONB NOT NULL DEFAULT '[]', -- cross-field validation rules

    -- Quality metric selection (auto-selected based on output type if null)
    primary_agreement_metric TEXT,
    -- "cohens_kappa", "fleiss_kappa", "krippendorff_alpha", "iou", "dice", "span_f1", "bleu"
    secondary_agreement_metric TEXT,

    -- UI configuration
    ui_config       JSONB NOT NULL DEFAULT '{}',
    -- {
    --   "layout": "side_by_side",
    --   "canvas_tools": ["bbox", "polygon", "zoom"],
    --   "keyboard_shortcuts": {"1": "label_a", "2": "label_b"},
    --   "guideline_url": "https://docs.internal/guidelines/rlhf_v2"
    -- }

    created_by      UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(org_id, name, version)
);

CREATE INDEX idx_schemas_org_active ON annotation_schemas(org_id) WHERE status = 'active';
```

### task_batches

```sql
CREATE TABLE task_batches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    name            TEXT,
    source          TEXT NOT NULL,
    -- "upload", "s3_manifest", "api", "active_learning", "drift_reannot", "error_curriculum"
    source_reference TEXT,

    status          TEXT NOT NULL DEFAULT 'created',
    -- created -> ingesting -> queued -> in_progress -> completed -> exported
    -- created -> ingesting -> failed

    total_items     INTEGER NOT NULL DEFAULT 0,
    completed_items INTEGER NOT NULL DEFAULT 0,
    accepted_items  INTEGER NOT NULL DEFAULT 0,
    rejected_items  INTEGER NOT NULL DEFAULT 0,

    priority        TEXT NOT NULL DEFAULT 'normal',  -- critical, high, normal, low
    deadline        TIMESTAMPTZ,

    created_by      UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_batches_project ON task_batches(project_id);
CREATE INDEX idx_batches_active ON task_batches(status) WHERE status IN ('queued', 'in_progress');
```

### tasks

```sql
CREATE TABLE tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id        UUID NOT NULL REFERENCES task_batches(id),
    project_id      UUID NOT NULL REFERENCES projects(id),

    -- Input data (pointer to raw asset + metadata)
    data_reference  TEXT NOT NULL,              -- S3 path or URL to raw data asset
    input_data      JSONB NOT NULL DEFAULT '{}', -- structured input per schema
    input_hash      TEXT NOT NULL,              -- SHA-256 of input for deduplication

    status          TEXT NOT NULL DEFAULT 'queued',
    -- queued -> assigned -> annotated -> in_review -> accepted
    -- queued -> assigned -> annotated -> in_review -> in_adjudication -> accepted
    -- queued -> assigned -> annotated -> auto_accepted (high agreement)
    -- queued -> assigned -> annotated -> rejected (failed quality)
    -- assigned -> expired -> queued (reservation timeout, re-queued)
    -- assigned -> flagged -> queued (annotator flagged as ambiguous)

    -- Workflow tracking
    current_stage   TEXT NOT NULL DEFAULT 'label',  -- label, review, adjudicate, complete
    overlap_target  INTEGER NOT NULL DEFAULT 3,
    annotations_received INTEGER NOT NULL DEFAULT 0,

    -- Quality (populated after annotation)
    agreement_score FLOAT,
    agreement_metric TEXT,
    consensus_method TEXT,
    is_golden       BOOLEAN NOT NULL DEFAULT false,

    -- Pre-labeling
    pre_label       JSONB,
    pre_label_confidence FLOAT,

    -- Difficulty (computed from agreement patterns)
    difficulty_score FLOAT,                    -- 0.0 (easy) to 1.0 (hard)

    priority        INTEGER NOT NULL DEFAULT 0, -- higher = more urgent
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,

    temporal_workflow_id TEXT
);

CREATE INDEX idx_tasks_batch ON tasks(batch_id);
CREATE INDEX idx_tasks_project_status ON tasks(project_id, status);
CREATE INDEX idx_tasks_queued ON tasks(project_id, priority DESC) WHERE status = 'queued';
CREATE INDEX idx_tasks_golden ON tasks(project_id) WHERE is_golden = true;
CREATE INDEX idx_tasks_input_hash ON tasks(input_hash);
```

### annotations

```sql
CREATE TABLE annotations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks(id),
    annotator_id    UUID NOT NULL REFERENCES annotators(id),
    project_id      UUID NOT NULL REFERENCES projects(id),

    -- The annotation itself (JSONB matching project output_schema)
    annotation_data JSONB NOT NULL,
    -- Classification: {"label": "fraud", "confidence": 0.9}
    -- NER: {"spans": [{"start": 12, "end": 25, "label": "medication"}]}
    -- Bbox: {"boxes": [{"x": 100, "y": 200, "w": 50, "h": 60, "label": "mass"}]}
    -- Preference: {"preferred": "A", "reasoning": "more helpful", "categories": ["more_accurate"]}

    status          TEXT NOT NULL DEFAULT 'submitted',
    -- submitted -> accepted | revised | rejected | superseded

    -- Quality signals
    golden_evaluation JSONB,
    -- if task was golden: {"correct": true, "expected": {...}, "metric": "kappa", "score": 0.95}

    reviewer_id     UUID REFERENCES annotators(id),
    reviewer_action TEXT,                       -- "accepted", "rejected", "revised", "escalated"
    reviewer_notes  TEXT,
    reviewed_at     TIMESTAMPTZ,

    -- Timing
    started_at      TIMESTAMPTZ NOT NULL,
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_seconds INTEGER,

    -- Pre-label tracking
    pre_label_shown BOOLEAN NOT NULL DEFAULT false,
    pre_label_accepted BOOLEAN,
    pre_label_corrections JSONB,

    UNIQUE(task_id, annotator_id)
);

CREATE INDEX idx_annotations_task ON annotations(task_id);
CREATE INDEX idx_annotations_annotator ON annotations(annotator_id);
CREATE INDEX idx_annotations_project_status ON annotations(project_id, status);
CREATE INDEX idx_annotations_golden ON annotations(task_id) WHERE golden_evaluation IS NOT NULL;
```

### annotation_versions

```sql
CREATE TABLE annotation_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    annotation_id   UUID NOT NULL REFERENCES annotations(id),
    version         INTEGER NOT NULL,
    annotation_data JSONB NOT NULL,
    changed_by      UUID NOT NULL,
    change_reason   TEXT,
    -- "initial_submission", "reviewer_feedback", "self_correction", "adjudication"
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(annotation_id, version)
);

CREATE INDEX idx_annotation_versions ON annotation_versions(annotation_id);
```

### consensus_results

```sql
CREATE TABLE consensus_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL UNIQUE REFERENCES tasks(id),
    project_id      UUID NOT NULL REFERENCES projects(id),

    resolved_annotation JSONB NOT NULL,        -- the final label for this task

    resolution_method TEXT NOT NULL,
    -- "auto_accept", "majority_vote", "weighted_vote", "expert_tiebreak", "single_annotator"
    agreement_score FLOAT,
    agreement_metric TEXT,

    contributing_annotation_ids UUID[] NOT NULL,
    adjudicator_id  UUID REFERENCES annotators(id),
    adjudicator_notes TEXT,

    passed_quality  BOOLEAN NOT NULL DEFAULT true,
    quality_failure_reason TEXT,
    -- "low_agreement", "no_consensus", "flagged_ambiguous"

    resolved_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_consensus_project ON consensus_results(project_id);
CREATE INDEX idx_consensus_quality ON consensus_results(project_id, passed_quality);
```

### golden_sets and golden_items

```sql
CREATE TABLE golden_sets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    name            TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'active',  -- active, retired
    item_count      INTEGER NOT NULL DEFAULT 0,
    created_by      UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    retired_at      TIMESTAMPTZ,

    UNIQUE(project_id, name, version)
);

CREATE TABLE golden_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    golden_set_id   UUID NOT NULL REFERENCES golden_sets(id),
    task_id         UUID REFERENCES tasks(id),

    gold_annotation JSONB NOT NULL,            -- expert-labeled ground truth
    labeled_by      UUID NOT NULL REFERENCES users(id),
    difficulty      TEXT NOT NULL DEFAULT 'medium',  -- easy, medium, hard

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_golden_items_set ON golden_items(golden_set_id);
```

### annotators

```sql
CREATE TABLE annotators (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    user_id         UUID REFERENCES users(id),  -- null for external/crowd annotators
    email           TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'onboarding',
    -- onboarding -> active -> paused -> deactivated

    skills          JSONB NOT NULL DEFAULT '[]',
    -- [
    --   {"domain": "radiology", "qualified": true, "qualified_at": "2024-06-15"},
    --   {"domain": "rlhf_preference", "qualified": true, "qualified_at": "2024-08-01"},
    --   {"domain": "clinical_ner", "qualified": false, "failed_at": "2024-07-20"}
    -- ]

    overall_accuracy FLOAT,
    skill_level     TEXT NOT NULL DEFAULT 'junior',  -- junior, senior, expert
    total_annotations INTEGER NOT NULL DEFAULT 0,

    languages       TEXT[] NOT NULL DEFAULT '{}',
    timezone        TEXT,
    availability    JSONB NOT NULL DEFAULT '{}',
    -- {"mon": ["09:00-17:00"], "tue": ["09:00-17:00"], ...}
    max_items_per_shift INTEGER NOT NULL DEFAULT 200,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at  TIMESTAMPTZ
);

CREATE INDEX idx_annotators_org ON annotators(org_id);
CREATE INDEX idx_annotators_active ON annotators(org_id, status) WHERE status = 'active';
CREATE INDEX idx_annotators_skills ON annotators USING GIN(skills);
```

### annotator_qualifications

```sql
CREATE TABLE annotator_qualifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    annotator_id    UUID NOT NULL REFERENCES annotators(id),
    domain          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    -- pending -> passed -> active -> expired -> requalification_required
    -- pending -> failed

    test_score      FLOAT,
    test_items      INTEGER,
    pass_threshold  FLOAT NOT NULL,

    certification_type TEXT,                   -- "board_certified_radiologist", "hipaa_trained"
    certification_ref TEXT,

    qualified_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_qualifications_annotator ON annotator_qualifications(annotator_id);
CREATE UNIQUE INDEX idx_qualifications_unique ON annotator_qualifications(annotator_id, domain)
    WHERE status = 'active';
```

### annotator_accuracy

```sql
CREATE TABLE annotator_accuracy (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    annotator_id    UUID NOT NULL REFERENCES annotators(id),
    project_id      UUID NOT NULL REFERENCES projects(id),
    task_type       TEXT NOT NULL,

    -- Rolling accuracy windows
    accuracy_last_100  FLOAT,
    accuracy_last_7d   FLOAT,
    accuracy_lifetime  FLOAT,

    -- Golden set performance
    golden_items_evaluated INTEGER NOT NULL DEFAULT 0,
    golden_items_correct   INTEGER NOT NULL DEFAULT 0,
    consecutive_failures   INTEGER NOT NULL DEFAULT 0,

    -- Peer agreement
    peer_agreement_rate FLOAT,

    -- Throughput
    avg_annotation_seconds FLOAT,
    annotations_per_hour   FLOAT,

    -- Trend
    accuracy_trend  TEXT,                      -- "improving", "stable", "degrading"

    last_updated    TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(annotator_id, project_id, task_type)
);

CREATE INDEX idx_accuracy_annotator ON annotator_accuracy(annotator_id);
CREATE INDEX idx_accuracy_project ON annotator_accuracy(project_id);
```

### annotator_sessions

```sql
CREATE TABLE annotator_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    annotator_id    UUID NOT NULL REFERENCES annotators(id),
    project_id      UUID NOT NULL REFERENCES projects(id),

    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    items_completed INTEGER NOT NULL DEFAULT 0,
    items_flagged   INTEGER NOT NULL DEFAULT 0,
    active_minutes  FLOAT,
    idle_minutes    FLOAT,

    -- Content wellness tracking (for moderation projects)
    sensitive_content_minutes FLOAT DEFAULT 0,
    break_taken     BOOLEAN DEFAULT false
);

CREATE INDEX idx_sessions_annotator ON annotator_sessions(annotator_id);
CREATE INDEX idx_sessions_project ON annotator_sessions(project_id);
```

### model_endpoints

```sql
CREATE TABLE model_endpoints (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    name            TEXT NOT NULL,
    endpoint_url    TEXT NOT NULL,
    auth_config     JSONB NOT NULL DEFAULT '{}',  -- Vault path reference, not plaintext

    supports_pre_labeling   BOOLEAN NOT NULL DEFAULT false,
    supports_uncertainty     BOOLEAN NOT NULL DEFAULT false,
    supports_embeddings      BOOLEAN NOT NULL DEFAULT false,

    input_format    TEXT NOT NULL DEFAULT 'json',
    output_format   TEXT NOT NULL DEFAULT 'json',
    batch_size_limit INTEGER NOT NULL DEFAULT 100,
    timeout_seconds  INTEGER NOT NULL DEFAULT 30,

    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_health_check TIMESTAMPTZ
);
```

### drift_snapshots

```sql
CREATE TABLE drift_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    model_endpoint_id UUID NOT NULL REFERENCES model_endpoints(id),

    window_start    TIMESTAMPTZ NOT NULL,
    window_end      TIMESTAMPTZ NOT NULL,

    feature_kl_divergence   JSONB NOT NULL,    -- {"feature_name": kl_value, ...}
    prediction_psi          FLOAT NOT NULL,
    embedding_centroid_distance FLOAT,

    drift_detected  BOOLEAN NOT NULL DEFAULT false,
    alert_sent      BOOLEAN NOT NULL DEFAULT false,
    consecutive_drift_windows INTEGER NOT NULL DEFAULT 0,

    recommended_reannot_volume INTEGER,
    reannot_batch_id UUID REFERENCES task_batches(id),

    snapshot_data   JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_drift_project ON drift_snapshots(project_id, created_at DESC);
```

### active_learning_batches

```sql
CREATE TABLE active_learning_batches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    model_endpoint_id UUID NOT NULL REFERENCES model_endpoints(id),

    candidate_pool_size INTEGER NOT NULL,
    candidate_source    TEXT NOT NULL,
    sampling_strategy   TEXT NOT NULL,
    -- "uncertainty", "margin", "committee", "mixed"

    budget              INTEGER NOT NULL,
    active_learning_count INTEGER NOT NULL,
    random_count        INTEGER NOT NULL,

    uncertainty_stats JSONB NOT NULL,
    -- {"min": 0.01, "max": 0.98, "mean": 0.72, "p50": 0.74, "p95": 0.96}

    task_batch_id   UUID REFERENCES task_batches(id),

    -- Filled after model retrains on this data
    model_improvement JSONB,
    -- {
    --   "baseline_f1": 0.82, "retrained_f1": 0.85, "improvement": 0.03,
    --   "random_baseline_improvement": 0.012, "efficiency_ratio": 2.5
    -- }

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_al_batches_project ON active_learning_batches(project_id);
```

### model_training_runs

```sql
CREATE TABLE model_training_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    model_endpoint_id UUID NOT NULL REFERENCES model_endpoints(id),

    annotation_batch_ids UUID[] NOT NULL,
    total_examples  INTEGER NOT NULL,
    quality_summary JSONB NOT NULL,

    evaluation_metrics JSONB NOT NULL,
    -- {"accuracy": 0.94, "f1_macro": 0.91, "per_class": {...}, "confusion_matrix": [...]}

    previous_run_id UUID REFERENCES model_training_runs(id),
    improvement     JSONB,

    error_slices    JSONB,
    -- [{"slice": "medical_abbreviations", "accuracy": 0.72, "count": 340, "priority": "high"}]

    created_by      UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_training_runs_project ON model_training_runs(project_id);
```

### exports

```sql
CREATE TABLE exports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),

    format          TEXT NOT NULL,              -- "jsonl", "csv", "tfrecord", "huggingface", "coco"
    status          TEXT NOT NULL DEFAULT 'generating',
    -- generating -> completed -> downloaded | generating -> failed

    item_count      INTEGER NOT NULL,
    batch_ids       UUID[],
    min_agreement   FLOAT,
    quality_certificate JSONB NOT NULL,

    output_path     TEXT,
    file_size_bytes BIGINT,

    requires_approval BOOLEAN NOT NULL DEFAULT false,
    approved_by     UUID REFERENCES users(id),
    approved_at     TIMESTAMPTZ,

    created_by      UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_exports_project ON exports(project_id);
```

### users

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    email           TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    role            TEXT NOT NULL,
    -- "ml_engineer", "annotation_lead", "ops_manager", "expert", "admin"
    status          TEXT NOT NULL DEFAULT 'active',
    auth_provider   TEXT NOT NULL DEFAULT 'oidc',
    auth_subject    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_org ON users(org_id);
```

### quality_reports

```sql
CREATE TABLE quality_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    report_type     TEXT NOT NULL,
    -- "project_summary", "annotator_card", "batch_certificate", "compliance"
    period_start    TIMESTAMPTZ,
    period_end      TIMESTAMPTZ,

    metrics         JSONB NOT NULL,
    generated_by    TEXT NOT NULL DEFAULT 'system',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_quality_reports_project ON quality_reports(project_id, report_type);
```

### audit_log

```sql
CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    actor_id        UUID NOT NULL,
    actor_type      TEXT NOT NULL,             -- "user", "annotator", "system", "temporal_workflow"
    action          TEXT NOT NULL,
    -- annotation.created, annotation.submitted, annotation.reviewed, annotation.accepted,
    -- annotation.rejected, annotation.escalated, annotation.revised,
    -- task.created, task.assigned, task.completed, task.expired, task.flagged,
    -- golden.evaluated, golden.created,
    -- export.requested, export.approved, export.completed,
    -- annotator.qualified, annotator.dequalified, annotator.onboarded,
    -- project.created, project.configured, project.completed,
    -- quality.alert_triggered, quality.report_generated

    resource_type   TEXT NOT NULL,
    resource_id     UUID NOT NULL,
    details         JSONB NOT NULL DEFAULT '{}',
    ip_address      INET,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Append-only: no updates, no deletes
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;

CREATE INDEX idx_audit_org ON audit_log(org_id, created_at DESC);
CREATE INDEX idx_audit_resource ON audit_log(resource_type, resource_id);
CREATE INDEX idx_audit_actor ON audit_log(actor_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_log(action, created_at DESC);
```

---

## Row-Level Security

All org-scoped tables have RLS enabled. API middleware sets session variables per request.

```sql
SET app.current_org = 'org_uuid';
SET app.user_id = 'user_uuid';
SET app.user_role = 'ml_engineer';

-- Projects: org isolation
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
CREATE POLICY projects_org_isolation ON projects
    USING (org_id = current_setting('app.current_org')::UUID);

-- Annotations: annotators see own, leads see all in org
CREATE POLICY annotations_annotator_own ON annotations
    FOR SELECT TO annotator_role
    USING (annotator_id = current_setting('app.user_id')::UUID);

CREATE POLICY annotations_lead_all ON annotations
    FOR SELECT TO annotation_lead_role
    USING (project_id IN (
        SELECT id FROM projects WHERE org_id = current_setting('app.current_org')::UUID
    ));

-- Audit log: read-only for compliance roles
CREATE POLICY audit_read ON audit_log
    FOR SELECT TO ops_manager_role, admin_role
    USING (org_id = current_setting('app.current_org')::UUID);
```

---

## State Machines

### Task Lifecycle

```
                    ┌──────────────────────────────────────────────────┐
                    │                                                    │
         ┌──────┐  │  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
         │queued│──┼─>│ assigned  │─>│ annotated │─>│ auto_accepted│──┼─> complete
         └──────┘  │  └──────────┘  └───────────┘  └──────────────┘  │
                    │       │              │                            │
                    │  timeout/expire      │ low agreement              │
                    │       │              ▼                            │
                    │       └──────> ┌───────────┐  ┌──────────────┐  │
                    │    (re-queue)  │ in_review  │─>│   accepted   │──┼─> complete
                    │                └───────────┘  └──────────────┘  │
                    │                      │                            │
                    │                 escalate                          │
                    │                      ▼                            │
                    │               ┌──────────────┐                   │
                    │               │in_adjudication│──────────────────┼─> complete
                    │               └──────────────┘                   │
                    │                      │                            │
                    │                 no consensus                      │
                    │                      ▼                            │
                    │               ┌──────────────┐                   │
                    │               │   rejected   │ (excluded)        │
                    │               └──────────────┘                   │
                    └──────────────────────────────────────────────────┘

Special paths:
  assigned -> flagged -> queued (annotator flags ambiguous, re-queued)
  annotated -> rejected (quality gate failure, excluded from export)
```

### Annotator Lifecycle

```
  ┌────────────┐   pass qualification   ┌────────┐
  │ onboarding │ ─────────────────────> │ active │ <───────────┐
  └────────────┘                        └────────┘             │
        │                                  │    │              │
   fail qualification              pause   │    │ accuracy     │
        │                           │      │    │ drop         │
        ▼                           ▼      │    ▼              │
  ┌────────────┐              ┌────────┐   │  ┌────────────┐  │
  │  failed    │              │ paused │   │  │ requalify  │──┘ pass
  │ (can retry)│              └────────┘   │  │ required   │
  └────────────┘                           │  └────────────┘
                                      deactivate    │ fail
                                           │        ▼
                                    ┌──────────────┐
                                    │ deactivated  │
                                    └──────────────┘
```

---

## Common Query Patterns

**Project quality dashboard:**
```sql
SELECT
    p.name AS project_name,
    COUNT(DISTINCT t.id) AS total_tasks,
    COUNT(DISTINCT t.id) FILTER (WHERE t.status IN ('accepted', 'auto_accepted')) AS completed,
    ROUND(AVG(t.agreement_score)::numeric, 3) AS avg_agreement,
    COUNT(DISTINCT t.id) FILTER (WHERE t.current_stage = 'adjudicate') AS in_adjudication,
    COUNT(DISTINCT t.id) FILTER (WHERE t.status = 'queued') AS queued
FROM projects p
JOIN tasks t ON t.project_id = p.id
WHERE p.id = $1
GROUP BY p.id, p.name;
```

**Consensus resolution distribution:**
```sql
SELECT
    resolution_method,
    COUNT(*) AS item_count,
    ROUND(AVG(agreement_score)::numeric, 3) AS avg_agreement,
    COUNT(*) FILTER (WHERE passed_quality = true) AS passed,
    COUNT(*) FILTER (WHERE passed_quality = false) AS excluded
FROM consensus_results
WHERE project_id = $1
GROUP BY resolution_method
ORDER BY item_count DESC;
```

**Active learning efficiency comparison:**
```sql
SELECT
    sampling_strategy,
    budget,
    active_learning_count,
    random_count,
    (model_improvement->>'improvement')::float AS model_lift,
    (model_improvement->>'efficiency_ratio')::float AS efficiency_ratio,
    created_at
FROM active_learning_batches
WHERE project_id = $1
ORDER BY created_at DESC;
```

**Annotator gaming detection (golden accuracy vs. peer agreement):**
```sql
SELECT
    an.display_name,
    aa.accuracy_last_100 AS golden_accuracy,
    aa.peer_agreement_rate,
    aa.accuracy_last_100 - aa.peer_agreement_rate AS suspicion_gap
FROM annotators an
JOIN annotator_accuracy aa ON aa.annotator_id = an.id
WHERE aa.project_id = $1
  AND aa.accuracy_last_100 - aa.peer_agreement_rate > 0.15
ORDER BY suspicion_gap DESC;
```

---

## Retention Policy

| Data | Hot (PostgreSQL) | Cold (S3 Archive) | Rationale |
|---|---|---|---|
| Active project data | Until project archived | 7 years after archive | Compliance (SOX, HIPAA) |
| Completed annotations | 1 year after project completion | 7 years | Training data provenance |
| Consensus results | 1 year after project completion | 7 years | Model card documentation |
| Audit log | 1 year | 7 years (Glacier) | Regulatory compliance |
| Golden sets | Indefinite (active), 1 year (retired) | 7 years | Calibration reference |
| Annotator accuracy | 2 years | 5 years | Workforce analytics |
| Drift snapshots | 6 months | 2 years | Model performance tracking |
| Active learning batches | 1 year | 2 years | ROI measurement |
| Model training runs | 2 years | 7 years | Model provenance |

---

## Migration Order

```
001_organizations.sql
002_users.sql
003_annotation_schemas.sql
004_model_endpoints.sql
005_projects.sql
006_annotators.sql
007_annotator_qualifications.sql
008_annotator_accuracy.sql
009_annotator_sessions.sql
010_golden_sets.sql
011_golden_items.sql
012_task_batches.sql
013_tasks.sql
014_annotations.sql
015_annotation_versions.sql
016_consensus_results.sql
017_drift_snapshots.sql
018_active_learning_batches.sql
019_model_training_runs.sql
020_exports.sql
021_quality_reports.sql
022_audit_log.sql
023_row_level_security.sql
024_indexes.sql
025_seeds.sql (industry-preset schemas, default golden sets)
```
