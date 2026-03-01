# System Architecture: AI Data Operations Platform

**Last Updated:** February 2025

---

## Architecture Overview

The platform is organized as five services, each owning a distinct domain. Services communicate through a shared PostgreSQL database for transactional data and Redis for real-time coordination. Temporal orchestrates multi-stage annotation workflows that span hours to days and require human-in-the-loop decisions at every stage.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              API Gateway                                 │
│                          (FastAPI + WebSocket)                            │
│                                                                           │
│  /tasks  /annotations  /quality  /feedback  /workforce  /projects        │
│  /export /admin        /webhooks /health                                  │
└──────┬──────────┬──────────┬──────────┬──────────┬──────────────────────┘
       │          │          │          │          │
       ▼          ▼          ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│  Task    │ │Annotation│ │ Quality  │ │ Feedback │ │Workforce │
│  Engine  │ │ Pipeline │ │  Engine  │ │   Loop   │ │ Manager  │
│          │ │          │ │          │ │          │ │          │
│ Schema   │ │ Workflow  │ │Agreement │ │ Active   │ │ Profiles │
│ Registry │ │Orchestrat│ │Calculator│ │ Learning │ │ Routing  │
│ Router   │ │ Consensus│ │ Golden   │ │ Drift    │ │ Qualify  │
│ Queue    │ │ Validate │ │ Scoring  │ │ Evaluate │ │ Track    │
└────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
     │            │            │            │            │
     └────────────┴────────────┴────────────┴────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
     │ PostgreSQL 15│ │   Redis 7    │ │   Temporal   │
     │              │ │              │ │              │
     │ Annotations  │ │ Task queues  │ │ Annotation   │
     │ Quality data │ │ Sessions     │ │ workflows    │
     │ Workforce    │ │ Leaderboard  │ │ Review gates │
     │ Audit trail  │ │ Rate limits  │ │ Adjudication │
     │ Projects     │ │ Pub/sub      │ │ signals      │
     └──────────────┘ └──────────────┘ └──────────────┘
              │
              ▼
     ┌──────────────┐
     │  S3 / Azure  │
     │  Blob Storage│
     │              │
     │ Raw data     │
     │ (images,     │
     │  audio,      │
     │  LiDAR,      │
     │  documents)  │
     │              │
     │ Annotation   │
     │ snapshots    │
     │              │
     │ Export        │
     │ archives     │
     └──────────────┘
```

### Design Principles

**Schema-driven, not code-driven.** Annotation types (text classification, NER, bounding box, preference pairs) are defined as JSONB schemas, not as code paths. Adding a new annotation type is a configuration change, not an engineering deployment. This is how one platform serves healthcare radiology, RLHF preference labeling, and financial transaction classification.

**Quality is measured, not assumed.** Every annotation passes through quality measurement: inter-annotator agreement, golden set evaluation, or reviewer validation. Nothing enters the training data export without a quality score attached.

**Humans are in the loop at every stage.** The system assists (model-assisted pre-labeling, active learning, automatic routing) but never replaces human judgment on label correctness. Consensus resolution, expert adjudication, and quality escalation all pause for human decisions.

**Audit everything.** Every annotation action (create, modify, approve, reject, escalate) is logged with actor, timestamp, and details. This is not optional; regulated industries (healthcare, financial services, autonomous vehicles) require complete traceability from training data to model behavior.

---

## Service Architecture

### 1. Task Engine

Responsible for: annotation schema management, task creation, priority queuing, and skill-based routing to annotators.

```
Task Engine
│
├── Schema Registry
│   ├── JSONB schema definitions per annotation type
│   ├── Schema versioning (v1, v2, ...) with backward compatibility
│   ├── Validation rules (required fields, value constraints, cross-field checks)
│   └── Industry presets (RLHF preference, radiology bbox, NER clinical, fraud classification)
│
├── Task Router
│   ├── Skill-based assignment (annotator qualifications matched to task requirements)
│   ├── Load balancing across available annotators
│   ├── Priority weighting (active learning samples > backfill > re-annotation)
│   ├── Task grouping (related items to same annotator for consistency)
│   └── Reservation with timeout (30-minute default, configurable per project)
│
└── Queue Manager
    ├── Priority queues per project (Redis sorted sets)
    ├── Deadline-aware scheduling (tasks approaching SLA get priority boost)
    ├── Backlog monitoring and age tracking
    ├── Auto-escalation for aging tasks (> 4 hours unassigned)
    └── Capacity planning (projected completion based on current throughput)
```

**Schema Registry: how one platform supports every annotation type.**

Annotation schemas are stored as JSONB documents in the `annotation_schemas` table. Each schema defines the input type (text, image, video, point cloud), the expected output structure (classification label, NER spans, bounding boxes, preference pair), validation rules, and UI rendering hints.

When a project is created, the ML team selects or defines a schema. The annotation interface renders dynamically based on the schema definition. No code changes needed.

```
Schema definition example (RLHF preference pair):
{
    "schema_id": "rlhf_preference_v2",
    "input_type": "text_pair",
    "input_schema": {
        "prompt": {"type": "text", "display": "context"},
        "response_a": {"type": "text", "display": "left_panel"},
        "response_b": {"type": "text", "display": "right_panel"}
    },
    "output_schema": {
        "preferred": {"type": "enum", "values": ["A", "B", "tie"], "required": true},
        "reasoning": {"type": "text", "max_length": 500, "required": true},
        "categories": {
            "type": "multi_select",
            "values": ["more_helpful", "more_accurate", "better_formatted",
                       "less_harmful", "more_honest"],
            "min_selections": 1
        },
        "safety_flags": {
            "type": "multi_select",
            "values": ["harmful_content", "bias", "hallucination",
                       "personally_identifiable", "none"],
            "required": true
        }
    },
    "validation_rules": [
        {"rule": "if preferred != 'tie' then reasoning.min_length = 20"},
        {"rule": "if safety_flags contains 'harmful_content' then escalate_to_review = true"}
    ]
}
```

```
Schema definition example (radiology bounding box):
{
    "schema_id": "radiology_bbox_v1",
    "input_type": "dicom_image",
    "input_schema": {
        "image_url": {"type": "image", "display": "main_canvas"},
        "clinical_context": {"type": "text", "display": "side_panel"},
        "prior_study_url": {"type": "image", "display": "reference_panel", "optional": true}
    },
    "output_schema": {
        "findings": {
            "type": "array",
            "items": {
                "bbox": {"type": "bounding_box", "format": "xyxy"},
                "label": {
                    "type": "enum",
                    "values": ["mass", "calcification", "nodule", "opacity",
                               "effusion", "cardiomegaly", "no_finding"]
                },
                "confidence": {"type": "enum", "values": ["definite", "probable", "possible"]},
                "birads": {"type": "enum", "values": ["0", "1", "2", "3", "4", "5", "6"]}
            }
        },
        "overall_impression": {"type": "text", "max_length": 1000}
    },
    "validation_rules": [
        {"rule": "if findings is empty then overall_impression is required"},
        {"rule": "bbox coordinates must be within image dimensions"},
        {"rule": "if label = 'mass' and confidence = 'definite' then birads >= 4"}
    ]
}
```

**Task Router: skill-weighted assignment algorithm.**

When a task is ready for assignment, the router evaluates all available annotators against the task requirements:

```
Assignment score = (
    qualification_match     # binary: does annotator hold required certification?
    * accuracy_weight       # 0.0 - 1.0: annotator's rolling accuracy on this task type
    * workload_factor       # 1.0 when idle, decays as queue fills (prevents overload)
    * consistency_bonus     # 1.2x if annotator is already working on related items
    * priority_factor       # active learning samples assigned to top-quartile annotators
)

Filter: qualification_match = 0 eliminates annotator entirely
Rank: highest score wins
Tiebreak: least recently assigned (spread work evenly)
```

For healthcare projects, `qualification_match` requires specific certifications (board-certified radiologist, licensed clinician). For RLHF projects, it requires passing a domain-specific qualification test. For e-commerce categorization, the bar is lower: completion of onboarding tutorial + 80% accuracy on golden set quiz.

### 2. Annotation Pipeline

Responsible for: multi-stage annotation workflows, consensus resolution, annotation validation, and model-assisted pre-labeling.

```
Annotation Pipeline
│
├── Workflow Orchestrator (Temporal)
│   ├── Single-stage: label -> validate -> accept
│   ├── Two-stage: label -> review -> accept/reject/revise
│   ├── Three-stage: label -> review -> adjudicate -> accept (safety-critical)
│   ├── Conditional routing: agreement >= threshold -> auto-accept
│   │                        agreement < threshold -> escalate to review
│   └── Configurable per project (stage count, overlap count, thresholds)
│
├── Consensus Resolver
│   ├── Majority vote (3+ annotators, configurable quorum)
│   ├── Weighted vote (votes weighted by annotator accuracy score)
│   ├── Expert tiebreak (when majority vote fails, route to expert queue)
│   └── No-consensus handling (flag as genuinely ambiguous, exclude or multi-label)
│
├── Annotation Validator
│   ├── Schema compliance (required fields, value ranges, format checks)
│   ├── Completeness (all items in a batch annotated, no partial submissions)
│   ├── Cross-reference validation (NER spans don't overlap unless schema allows)
│   └── Temporal consistency (frame-to-frame tracking IDs consistent)
│
└── Pre-labeling Service
    ├── Model prediction fetcher (calls ML team's model serving endpoint)
    ├── Prediction-to-annotation converter (maps model output to schema format)
    ├── Confidence threshold (only show pre-labels above configurable threshold)
    └── Anchoring monitor (track correction rate to detect rubber-stamping)
```

**Workflow Orchestrator: how Temporal manages multi-stage annotation.**

Each annotation project creates a Temporal workflow definition specifying the stage configuration:

```
Workflow: three_stage_safety_review
│
│  ┌─────────────┐
│  │ Create task  │  Task enters queue with schema, priority, and routing rules
│  └──────┬──────┘
│         │
│         ▼
│  ┌─────────────┐
│  │  Stage 1:   │  Route to 3 qualified annotators (overlap = 3)
│  │   Label     │  Each annotator independently labels the item
│  │  (3-way)    │  Timeout: 4 hours per annotator (auto-reassign on expiry)
│  └──────┬──────┘
│         │
│         ▼
│  ┌─────────────┐
│  │  Agreement   │  Calculate inter-annotator agreement
│  │  Check       │  If kappa >= 0.80 AND majority vote is unanimous:
│  └──┬───────┬──┘     -> auto-accept, skip review (saves expert time)
│     │       │      If kappa < 0.80 OR split vote:
│     │       │        -> route to Stage 2
│     │       │
│  auto-      route
│  accept     to review
│     │       │
│     │       ▼
│     │  ┌─────────────┐
│     │  │  Stage 2:   │  Senior annotator sees: original data + all 3 annotations
│     │  │   Review    │  + agreement score + guideline reference
│     │  │             │  Can: accept best annotation, correct and accept, or
│     │  └──┬───────┬──┘  escalate to adjudication
│     │     │       │
│     │  accept   escalate
│     │     │       │
│     │     │       ▼
│     │     │  ┌─────────────┐
│     │     │  │  Stage 3:   │  Domain expert (e.g., senior radiologist, safety lead)
│     │     │  │ Adjudicate  │  Sees: all annotations + reviewer notes + quality context
│     │     │  │             │  Makes final determination. Decision is authoritative.
│     │     │  └──────┬──────┘
│     │     │         │
│     ▼     ▼         ▼
│  ┌─────────────────────┐
│  │  Final Annotation    │  Accepted annotation stored with full provenance:
│  │  + Quality Record    │  annotator IDs, agreement score, resolution method,
│  │  + Audit Trail       │  stage path, timestamps, reviewer/adjudicator identity
│  └─────────────────────┘
```

The key insight: most items (60-70% based on benchmarks) achieve high agreement and auto-accept at the agreement check. Only genuinely ambiguous or difficult items flow to Stage 2 and Stage 3. This preserves expert capacity for cases that actually need judgment.

**Conditional routing thresholds are configurable per project:**

| Project Type | Auto-accept Threshold | Review Trigger | Adjudication Trigger |
|---|---|---|---|
| RLHF Preference | kappa >= 0.80, unanimous | kappa < 0.80 or split | Reviewer escalates (safety flag) |
| Radiology Bbox | IoU >= 0.85, all annotators | IoU < 0.85 | Any finding disagreement on mass/nodule |
| Fraud Classification | 3/3 agree | 2/3 agree | No majority (3-way split) |
| Content Moderation | 2/2 agree | Disagree on policy violation | Potential legal/CSAM content |
| Clinical NER | Span F1 >= 0.90 | Span F1 < 0.90 | Disagreement on diagnosis entities |

**Consensus Resolution: multiple strategies for different situations.**

The resolver supports three strategies, selected per project:

**Majority vote.** 3 annotators label an item. If 2+ agree, that label wins. Simple, fast, works well for classification tasks where labels are unambiguous.

**Weighted vote.** Same as majority vote, but each annotator's vote is weighted by their rolling accuracy score on this task type. An annotator with 97% accuracy contributes a 0.97 vote; an annotator with 85% accuracy contributes 0.85. This means high-accuracy annotators effectively outweigh low-accuracy annotators without requiring explicit seniority. Weighted vote is the default for most projects because it naturally corrects for annotator quality differences.

**Expert tiebreak.** When majority or weighted vote cannot resolve (e.g., 3 annotators give 3 different labels), the item routes to an expert queue. The expert sees all annotations, the agreement score, and guideline references. The expert's decision is authoritative. Expert tiebreak preserves expert time by only firing when automated resolution fails.

### 3. Quality Engine

Responsible for: inter-annotator agreement measurement, per-annotator accuracy tracking, golden set evaluation, quality alerts, and bias detection.

```
Quality Engine
│
├── Agreement Calculator
│   ├── Cohen's kappa (2 annotators, categorical)
│   ├── Fleiss' kappa (3+ annotators, categorical)
│   ├── Krippendorff's alpha (any count, handles missing data)
│   ├── IoU (bounding box overlap)
│   ├── Dice coefficient (segmentation mask overlap)
│   ├── Span-level F1 (NER span matching)
│   └── BLEU/ROUGE (free-text response similarity)
│
├── Annotator Scorer
│   ├── Rolling accuracy: last 100 golden items, last 7 days, lifetime
│   ├── Per-task-type accuracy (annotator may be great at classification, weak at NER)
│   ├── Skill level classification: junior (< 85%), senior (85-95%), expert (95%+)
│   ├── Accuracy trend detection (improving, stable, degrading)
│   └── Auto-dequalification: accuracy < threshold for N consecutive golden items
│
├── Golden Set Manager
│   ├── Gold item creation (expert-labeled items with known correct answers)
│   ├── Random insertion into task queues (annotators don't know which are gold)
│   ├── Insertion rate: configurable (default 5% of tasks are golden)
│   ├── Evaluation: compare annotator response to gold truth, score immediately
│   ├── Calibration sessions: new annotators get higher gold rate (15%) during first week
│   └── Gold pool rotation: refresh monthly to prevent memorization
│
├── Quality Alerts
│   ├── Agreement drop: project-level kappa falls below threshold for 2+ consecutive batches
│   ├── Annotator accuracy decline: individual accuracy drops 10%+ in rolling window
│   ├── Bias detection: annotator's label distribution deviates 2+ std from project mean
│   ├── Throughput anomaly: annotator completing tasks 3x faster than peers (quality concern)
│   └── Alert routing: annotation lead (Slack/email), ops manager (dashboard), ML team (quality gate)
│
└── Quality Reporter
    ├── Per-project quality summary (agreement, accuracy, consensus rate, error categories)
    ├── Per-annotator quality card (accuracy by type, trend, golden set performance)
    ├── Per-batch quality certificate (attached to every data export)
    └── Compliance report (audit trail summary, data handling verification, access log)
```

**Agreement metric selection: different annotation types need different metrics.**

This is a key architectural decision. A single "accuracy" number is meaningless across annotation types. The quality engine automatically selects the appropriate agreement metric based on the annotation schema:

| Schema Output Type | Primary Metric | Secondary Metric | Why |
|---|---|---|---|
| `enum` (single label) | Cohen's kappa (2 raters) or Fleiss' kappa (3+) | Raw agreement % | Kappa accounts for chance agreement. Two annotators agreeing on a binary label 50% of the time is not 50% accuracy; it is chance. |
| `multi_select` | Krippendorff's alpha | Per-category agreement | Alpha handles partial overlap in multi-select responses. |
| `bounding_box` | IoU (Intersection over Union) | Center distance, size ratio | IoU captures both position and size accuracy in one metric. |
| `polygon` (segmentation) | Dice coefficient | Hausdorff distance | Dice is more sensitive to small regions than IoU, which matters for segmentation. |
| `spans` (NER) | Span-level F1 | Exact match %, partial overlap % | F1 handles both missed spans (recall) and extra spans (precision). |
| `text` (free-text) | BLEU (4-gram) | ROUGE-L, human eval sample | Automated text metrics are approximate. Periodic human evaluation calibrates them. |
| `preference` (A/B) | Cohen's kappa on preference direction | Agreement on reasoning categories | Preference direction is the primary signal; reasoning alignment is secondary. |

**Golden set evaluation: trust but verify.**

Golden items are expert-labeled examples with known correct answers. They are inserted into the annotation queue at a configurable rate (default: 5% of tasks). Annotators do not know which items are golden.

When an annotator completes a golden item, the quality engine immediately compares their annotation to the gold truth using the appropriate agreement metric. The result updates the annotator's rolling accuracy score.

This serves three purposes:
1. **Real-time accuracy measurement.** No need to wait for redundant annotation to measure quality. Golden set gives immediate signal.
2. **Calibration.** New annotators receive golden items at a higher rate (15% in first week) to establish their accuracy baseline quickly.
3. **Drift detection.** If an annotator's golden set accuracy drops over time, something has changed (fatigue, misunderstanding, gaming). The system alerts the annotation lead before bad labels accumulate.

**Anti-gaming measures.** Annotators who memorize golden items show suspiciously high golden accuracy relative to their peer agreement scores. The system flags annotators where golden accuracy exceeds peer-validated accuracy by more than 15% for investigation. Golden item pools are rotated monthly with 30% replacement to limit memorization opportunity.

### 4. Model Feedback Loop

Responsible for: active learning (selecting the most informative examples for annotation), drift detection, model error analysis, and training data curriculum construction.

```
Feedback Loop
│
├── Active Learner
│   ├── Uncertainty sampling: model prediction entropy on unlabeled pool
│   ├── Margin sampling: difference between top-2 prediction probabilities
│   ├── Committee disagreement: multiple model checkpoints vote, select disagreements
│   ├── Budget allocation: distribute annotation budget across categories by model weakness
│   └── Mixed sampling: 70% active learning + 30% random (prevent distribution collapse)
│
├── Drift Detector
│   ├── Feature distribution: KL divergence between production and training features
│   ├── Prediction distribution: PSI on model output distribution over time
│   ├── Embedding drift: centroid distance between production and training embeddings
│   ├── Temporal windowing: compare weekly cohorts to detect gradual drift
│   └── Alert policy: sustained drift (3+ consecutive windows) triggers re-annotation request
│
├── Model Evaluator
│   ├── Per-slice performance: accuracy broken down by category, source, difficulty
│   ├── Error pattern analysis: cluster model errors to identify systematic failure modes
│   ├── Confusion matrix tracking: which classes get confused with which, and how that changes
│   └── Re-annotation request generator: create targeted task batches from error slices
│
└── Provenance Tracker
    ├── Batch-to-model: which annotation batches were used in which training runs
    ├── Annotation-to-prediction: trace model predictions back to training examples
    ├── Quality-to-performance: correlate annotation quality metrics with model accuracy
    └── Model card generation: automated data provenance section for model documentation
```

**Active learning: label what the model needs, not random examples.**

The naive approach to training data collection is random sampling: grab 10K unlabeled examples, send them to annotators, train on the results. The active learning approach: ask the model which examples it is most uncertain about, send those to annotators instead.

```
Active Learning Pipeline:

1. ML team uploads unlabeled candidate pool (e.g., 100K examples)
                    │
                    ▼
2. Platform sends candidates to model serving endpoint (batch inference)
   Model returns prediction + confidence for each example
                    │
                    ▼
3. Active learner ranks candidates by informativeness:
   - Uncertainty: entropy of prediction probability distribution
     H(p) = -sum(p_i * log(p_i)) for each class probability p_i
     High entropy = model is confused = high value for annotation
   - Margin: difference between top-2 class probabilities
     Small margin = model is torn between two classes = high value
                    │
                    ▼
4. Budget allocation: if budget = 5,000 annotations:
   - 3,500 (70%) from top uncertainty scores (active learning)
   - 1,500 (30%) random from remaining pool (distribution coverage)
   The 30% random prevents a known failure mode: pure uncertainty
   sampling concentrates all labels on the decision boundary,
   leaving the model blind to distribution shifts elsewhere.
                    │
                    ▼
5. Selected items enter task queue as high-priority tasks
   Routed to top-quartile annotators (high-value data gets best annotators)
                    │
                    ▼
6. Completed annotations exported to ML team for model retraining
   Post-training evaluation compared to baseline to measure annotation ROI
```

Benchmark: active learning achieves the same model improvement (measured by F1 on held-out test set) with 40% fewer labels than random sampling. On a 100K labeling project at $0.12/label, that is $4,800 saved per batch while reaching the same model performance.

**Drift detection: when production data stops looking like training data.**

Models degrade silently. The distribution of production data shifts over time (new product categories, seasonal patterns, adversarial inputs), but the model was trained on the old distribution. Drift detection catches this before model performance degrades visibly.

```
Drift Detection Pipeline:

              Production data         Training data
              (rolling 7-day window)  (reference distribution)
                      │                       │
                      ▼                       ▼
              ┌───────────────────────────────────┐
              │        Distribution Comparison     │
              │                                    │
              │  Feature-level:                    │
              │    KL divergence per feature        │
              │    Alert if KL > 0.1 on any feature│
              │                                    │
              │  Prediction-level:                 │
              │    PSI on model output distribution │
              │    Alert if PSI > 0.2              │
              │                                    │
              │  Embedding-level:                  │
              │    Cosine distance between          │
              │    production and training centroids│
              │    Alert if distance > 0.15        │
              └───────────────┬────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────────┐
              │        Sustained Drift Check       │
              │                                    │
              │  Single-window spike: log, no alert│
              │  (could be transient anomaly)       │
              │                                    │
              │  3+ consecutive windows: ALERT      │
              │  Generate drift report with:        │
              │  - Which features drifted            │
              │  - Distribution comparison plots    │
              │  - Recommended re-annotation volume │
              └───────────────┬────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────────┐
              │     Re-annotation Request           │
              │                                    │
              │  Sample from drifted distribution  │
              │  Create task batch targeting        │
              │  the new production patterns        │
              │  High priority in task queue         │
              └───────────────────────────────────┘
```

### 5. Workforce Manager

Responsible for: annotator profiles, skill tracking, qualification testing, onboarding, throughput analytics, and workload management.

```
Workforce Manager
│
├── Profile Service
│   ├── Annotator profiles (skills, certifications, languages, availability)
│   ├── Accuracy history per task type (rolling windows)
│   ├── Skill level classification (junior/senior/expert)
│   └── Activity history (tasks completed, accuracy trend, hours worked)
│
├── Qualification Engine
│   ├── Per-domain qualification tests (golden set quiz + timed assessment)
│   ├── Pass thresholds configurable per domain
│   │   Healthcare radiology: 95% on 50-item golden set, board certification required
│   │   RLHF preference: 80% agreement with expert labels on 30-item quiz
│   │   AV 3D bbox: IoU > 0.80 on 40-item calibration set
│   │   Content moderation: 85% on 100-item policy quiz + wellness assessment
│   ├── Re-qualification triggers (accuracy drop, extended absence, guideline update)
│   └── Certification tracking with expiration dates
│
├── Onboarding Pipeline
│   ├── Tutorial: annotation guidelines + worked examples + edge cases
│   ├── Practice set: low-stakes tasks with immediate feedback (not counted in production)
│   ├── Calibration set: golden items at 15% rate during first week
│   ├── Graduated complexity: simple tasks -> medium -> complex as accuracy is demonstrated
│   └── Mentor pairing: new annotator's work reviewed by senior annotator for first 3 days
│
├── Workforce Analytics
│   ├── Throughput: items per hour per annotator, per project, per task type
│   ├── Utilization: active annotation time vs. idle time vs. review time
│   ├── Quality-throughput frontier: scatter plot of accuracy vs. speed per annotator
│   ├── Capacity forecasting: projected completion dates based on current throughput
│   └── Burnout indicators: declining throughput + declining accuracy + increased flagging
│
└── Workload Manager
    ├── Maximum items per shift (configurable, default: 200)
    ├── Mandatory breaks for sensitive content (15 min every 2 hours)
    ├── Content rotation for moderators (no more than 2 hours on harmful content)
    ├── Availability scheduling (annotators set available hours)
    └── Fair distribution (no single annotator receives more than 2x average workload)
```

**Graduated onboarding: from weeks to days.**

The old process: shadow a senior annotator for 1-2 weeks, read a 50-page guideline document, get thrown into production tasks. Time to productive: 2-3 weeks. Error rate during ramp-up: 25%+.

The platform approach:

```
Day 1: Tutorial + Practice (not production)
├── Interactive tutorial with annotation guidelines
├── 20 practice items with immediate feedback
│   "Your label: mass. Correct label: calcification.
│    Here is why: note the irregular border pattern..."
├── Practice items do not enter production pipeline
└── Annotator sees their practice accuracy: "You scored 75%. Threshold is 80%."

Day 1-2: Calibration (production, high monitoring)
├── Real tasks with 15% golden item rate (3x normal)
├── Golden item feedback within the session
├── Tasks start with "easy" difficulty (clear examples, high inter-annotator agreement)
├── Mentor reviews all work for first 50 items
└── System tracks accuracy trend in real-time

Day 2-3: Graduated Complexity
├── If calibration accuracy > 85%: medium-difficulty tasks unlocked
├── If calibration accuracy > 90%: full task pool unlocked
├── Golden rate drops to 10% (still above the 5% steady-state)
├── Mentor review drops to 20% spot-check
└── Annotator flagged for extra golden items for another 2 weeks

Day 3+: Full Production
├── Normal task routing (skill-weighted, no restrictions)
├── Golden rate at 5% (standard)
├── Rolling accuracy tracked like all annotators
└── Qualification for additional domains available
```

Measured result: time-to-productive dropped from 2-3 weeks to 2.4 days. New annotator error rate during first week dropped from 25% to 8%.

---

## Cross-Cutting Concerns

### Data Flow: from raw data to model training

```
Raw Data                Annotation              Quality                  Export
(S3/Blob)               (PostgreSQL)            (PostgreSQL)             (S3/Blob)

┌──────────┐   ingest   ┌──────────┐  measure   ┌──────────┐  export   ┌──────────┐
│ Images   │──────────> │ Task     │──────────> │ Quality  │────────> │ JSONL    │
│ Text     │            │ queue    │            │ scores   │          │ TFRecord │
│ Audio    │   create   │          │  score     │ per item │  filter  │ HuggingF │
│ LiDAR    │   tasks    │ Assigned │  per       │ per batch│  by      │ COCO     │
│ Docs     │            │ items    │  annotator │ per ann. │  quality │          │
└──────────┘            │          │            │          │          │ Only     │
                        │ Annotated│            │ Golden   │          │ items    │
     ▲                  │ items    │            │ set eval │          │ that     │
     │                  │          │            │          │          │ pass     │
     │ model            │ Reviewed │            │ Agreement│          │ quality  │
     │ predictions      │ items    │            │ metrics  │          │ threshold│
     │ for pre-label    │          │            │          │          │          │
     │                  │ Accepted │            │ Consensus│          │ + quality│
     └──────────────────│ items    │            │ resolved │          │ metadata │
                        └──────────┘            └──────────┘          └──────────┘
                                                                            │
                                                                            ▼
                                                                      ML Training
                                                                      Pipeline
```

Every exported dataset includes a quality certificate:

```json
{
    "export_id": "exp_20250215_001",
    "project_id": "proj_rlhf_safety_v3",
    "item_count": 8472,
    "quality_summary": {
        "mean_agreement_kappa": 0.83,
        "golden_set_accuracy": 0.962,
        "consensus_method": "weighted_vote",
        "items_auto_accepted": 5891,
        "items_reviewed": 2104,
        "items_adjudicated": 477,
        "items_excluded_quality": 312
    },
    "annotator_count": 23,
    "annotation_period": "2025-01-15 to 2025-02-14",
    "schema_version": "rlhf_preference_v2",
    "provenance_hash": "sha256:a1b2c3..."
}
```

### Security and Compliance Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      API Gateway                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐ │
│  │ AuthN      │  │ AuthZ      │  │ Audit Logger           │ │
│  │ (JWT/OIDC) │  │ (RBAC +   │  │ (every request logged) │ │
│  │            │  │  project   │  │                        │ │
│  │            │  │  scope)    │  │                        │ │
│  └────────────┘  └────────────┘  └────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘

Roles:
├── ml_engineer: create projects, define schemas, export data, view quality
├── annotation_lead: manage workforce, configure workflows, view all annotations
├── annotator: annotate assigned tasks, flag for review, view own quality scores
├── reviewer: review annotations, accept/reject/revise, escalate to adjudication
├── expert: adjudicate disagreements, author golden sets, update guidelines
├── ops_manager: cross-project dashboards, budget tracking, compliance reports
└── admin: user management, system configuration, audit log access
```

**Industry-specific compliance layers:**

| Requirement | Healthcare (HIPAA) | Financial (SOX) | AV (ISO 26262) | AI Safety |
|---|---|---|---|---|
| Data handling | PHI de-identified before annotation exposure | PII masked (names, accounts, SSN) | Sensor data residency requirements | User-generated content handling policies |
| Access control | Role-based + need-to-know per study | Background check required | Security clearance for classified data | Domain expert access for safety annotations |
| Audit trail | Every annotation action logged with BAA compliance | 7-year retention, tamper-proof | Full traceability from annotation to safety case | Model card data provenance documentation |
| Data residency | US-only for certain datasets | Jurisdiction-specific | Varies by market/regulator | Varies by deployment region |
| Reporting | HIPAA compliance certificate per export | SOX audit package on demand | ISO 26262 evidence package | Bias audit report per annotation batch |

### Observability

```
Platform Health (Grafana dashboards):
├── Task queue depth by project (real-time)
├── Annotation throughput (items/hour, rolling 1h window)
├── API latency p50/p95/p99 per endpoint
├── Temporal workflow failure rate
├── Redis memory usage and eviction rate
├── PostgreSQL connection pool utilization
├── Active annotator count per project
└── Export queue depth

Quality Health (Grafana dashboards):
├── Inter-annotator agreement trend per project (weekly)
├── Golden set accuracy per annotator (rolling 100 items)
├── Consensus resolution distribution (auto-accept vs. review vs. adjudicate)
├── Error rate trend per project (weekly)
├── Bias detection alerts (annotator label distribution outliers)
├── Re-qualification triggers
└── Flagged item volume (annotators flagging ambiguous items)

Business Health (Grafana dashboards):
├── Usable examples per team-day (North Star)
├── Cost per labeled example by project
├── Pipeline cycle time (submit to export)
├── Active learning efficiency (model improvement per label)
├── Annotator utilization and capacity
├── Budget burn rate vs. projection
└── Model feedback loop latency (drift detection to re-annotation)
```

### Error Handling and Failure Modes

| Failure | Impact | Recovery |
|---|---|---|
| Annotator submits but save fails | Annotation data lost | Client-side optimistic save with retry. Annotation stored locally until server confirms. |
| Temporal workflow crashes mid-review | Review stage stuck | Durable execution: Temporal replays from last completed step. Reviewer picks up where they left off. |
| Model serving endpoint down (pre-labeling) | Pre-labels unavailable | Degrade gracefully: serve tasks without pre-labels. Annotators label from scratch. No pipeline blockage. |
| Golden set pool exhausted | Accuracy tracking paused | Alert annotation lead. Fallback: increase peer agreement checks until new gold items created. |
| Redis failure | Task assignment down | PostgreSQL-backed fallback queue (slower but functional). Tasks assigned from database instead of Redis. |
| Quality metric computation timeout | Dashboard stale | Pre-compute incrementally. Dashboard shows "last computed at" timestamp. Background job retries. |
| Export generation fails | ML team blocked | Retry with exponential backoff. Partial export available. Alert ML team with estimated resolution. |

---

## Infrastructure Requirements

### Production Deployment

| Component | Specification | Scaling Strategy |
|---|---|---|
| API (FastAPI) | 4 pods, 2 vCPU / 4GB each | Horizontal: HPA on request rate |
| Temporal Server | 3-node cluster, 2 vCPU / 4GB each | Horizontal: add workers per queue |
| Temporal Workers | 2 workers per queue (task, annotation, quality, feedback) | Horizontal: scale workers by queue depth |
| PostgreSQL | Primary + 1 read replica, 8 vCPU / 32GB, 500GB SSD | Vertical initially, read replicas for dashboards |
| Redis | 2 nodes (primary + replica), 4GB each | Vertical: memory scales with active task count |
| S3/Blob | Standard tier, lifecycle to cold after 90 days | Automatic: storage scales with data volume |

### Estimated Infrastructure Cost

| Environment | Monthly Cost | Notes |
|---|---|---|
| Development | ~$800 | Minimal resources, single-node everything |
| Staging | ~$2,500 | Production-like but smaller scale |
| Production (200 concurrent annotators) | ~$6,500 | Full HA, monitoring, backups |
| Production (1,000 concurrent annotators) | ~$18,000 | Scaled API and worker pools, larger database |
