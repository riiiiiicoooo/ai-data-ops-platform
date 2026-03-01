# AI Data Operations Platform

**End-to-end platform for managing training data quality at scale: task design, workforce routing, multi-stage annotation, consensus resolution, and model feedback loops.** Reduced annotation error rates from 12% to 2.8%, cut data pipeline cycle time by 65%, and enabled ML teams to ship model updates 3x faster by systematizing the 60-80% of ML work that isn't model development.

> **Portfolio Context:** This is a product management portfolio project showcasing data operations, human-in-the-loop ML systems, and quality-at-scale engineering. It includes complete product documentation (PRD, system architecture, data model, metrics framework, decision log, roadmap) and PM-authored reference code demonstrating core technical concepts. The code is not production. These prototypes were built to validate feasibility, communicate architecture to engineering, and inform product decisions with hands-on technical understanding.

---

## The Problem

ML teams across every industry share the same bottleneck: training data quality. Models are only as good as the data they learn from, and getting that data right is manual, error-prone, and slow.

**Annotation quality is inconsistent and hard to measure.** Two annotators look at the same data and disagree 15-25% of the time. Without systematic quality measurement (inter-annotator agreement, golden set evaluation, accuracy tracking per annotator), bad labels poison training data silently. The ML team discovers the problem weeks later when model metrics degrade, and nobody can trace it back to which labels were wrong.

**Data pipelines are ad hoc and don't scale.** Task creation, annotator assignment, review, and adjudication happen in spreadsheets, Slack threads, and custom scripts. When the team needs to label 50,000 examples for a new model, there's no infrastructure to route tasks to qualified annotators, enforce review workflows, or track progress. Everything is manual coordination.

**No feedback loop between models and labeling.** The ML team trains a model, evaluates it, identifies weaknesses (e.g., poor performance on medical abbreviations, edge cases in low-light images), but has no systematic way to route those specific failure cases back to the annotation pipeline for targeted labeling. The next batch of training data is random instead of focused on what the model actually needs.

**Workforce management is a black box.** Annotators have different skill levels, accuracy rates, and domain expertise, but there's no system to track this. A radiology annotation task gets routed to whoever is available instead of whoever is qualified. Onboarding new annotators takes weeks because there's no structured qualification process.

**This problem is not unique to AI companies.** Healthcare organizations labeling medical images, financial institutions classifying transactions, autonomous vehicle companies annotating LiDAR scans, and e-commerce platforms moderating content all face the same data quality challenge. The annotation schemas and domain expertise differ, but the operational infrastructure is identical.

---

## The Solution

A configurable platform that manages the full training data lifecycle. The core engine (task routing, quality measurement, workflow orchestration, feedback loops) is domain-agnostic. Industry-specific configuration (annotation schemas, quality thresholds, workforce qualifications, compliance requirements) is layered on top.

```
┌─────────────────────────────────────────────────────────────┐
│                    ML Team / Data Scientists                  │
│                                                               │
│  "We need 10K preference pairs for RLHF"                     │
│  "Label these radiology images for tumor detection"           │
│  "Classify these transactions as fraud/not-fraud"             │
│                                                               │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                     Task Engine                               │
│                                                               │
│  Schema design ─── Queue creation ─── Priority routing        │
│  (what to label)    (how many)         (who does it)          │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                  Annotation Pipeline                          │
│                                                               │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐            │
│  │  Label   │───>│  Review  │───>│  Adjudicate  │            │
│  │ (Tier 1) │    │ (Tier 2) │    │  (Expert)    │            │
│  └──────────┘    └──────────┘    └──────────────┘            │
│                                                               │
│  Supports: text classification, NER, bounding box, polygon,  │
│  preference ranking, free-text response, multi-turn dialogue  │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    Quality Engine                              │
│                                                               │
│  Inter-annotator agreement ─── Golden set evaluation          │
│  Annotator accuracy tracking ─── Consensus resolution         │
│  Auto-escalation on disagreement ─── Bias detection           │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                  Model Feedback Loop                           │
│                                                               │
│  Active learning ─── Model-assisted pre-labeling              │
│  Drift detection ─── Targeted re-annotation                   │
│  Error analysis ──── Training data curriculum                  │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                 Workforce Management                          │
│                                                               │
│  Skill profiles ─── Qualification tests ─── Throughput        │
│  Accuracy tracking ─── Domain certification ─── Compensation  │
└─────────────────────────────────────────────────────────────┘
```

### Industry Configurations

The same platform engine serves fundamentally different use cases through configuration:

| Industry | Annotation Types | Quality Threshold | Workforce Requirements | Compliance |
|---|---|---|---|---|
| **AI/ML (RLHF)** | Preference pairs, safety ratings, instruction quality | Cohen's kappa > 0.75 | Domain experts for safety, crowd for preference | Model card documentation, bias audits |
| **Healthcare** | Radiology bounding box, clinical NER, pathology classification | Krippendorff's alpha > 0.85 | Board-certified radiologists, licensed clinicians | HIPAA, PHI de-identification, audit trail |
| **Autonomous Vehicles** | LiDAR point cloud, 3D bounding box, scene segmentation | IoU > 0.80, 100% review for safety-critical | Certified annotators with driving domain training | ISO 26262 traceability, safety case documentation |
| **Financial Services** | Transaction classification, document extraction, sentiment | Agreement > 0.80, golden set accuracy > 95% | Compliance-trained, background-checked | SOX audit trail, PII handling, data residency |
| **E-commerce/Content** | Product categorization, content moderation, review quality | Agreement > 0.70 (volume-oriented) | Scalable crowd workforce, language-specific | Content policy compliance, appeals workflow |
| **Government/Defense** | Satellite imagery, document classification, entity extraction | Agreement > 0.85, dual-review mandatory | Security clearance, need-to-know access | FedRAMP, ITAR, classification handling |

### Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Workflow** | Temporal | Durable multi-stage annotation workflows. Tasks survive system failures. Human-in-the-loop review pauses and resumes. Retry failed annotation steps without data loss. |
| **API** | FastAPI | Async Python for high-throughput task distribution. WebSocket support for real-time annotator interfaces. Auto-generated OpenAPI docs for ML team integration. |
| **Quality/ML** | scikit-learn + NumPy | Inter-annotator agreement calculations (kappa, alpha, IoU), annotator accuracy models, active learning uncertainty sampling. No GPU needed. |
| **Search** | PostgreSQL + pgvector | Embedding-based similarity search for finding similar examples, near-duplicate detection, and curriculum construction for active learning. |
| **Queue** | Redis 7 | Real-time task distribution to annotators, leaderboard updates, session management, rate limiting. Sub-millisecond task assignment. |
| **Storage** | S3/Azure Blob | Raw data assets (images, audio, documents, point clouds). Versioned annotation snapshots. Export archives. |
| **Database** | PostgreSQL 15 | Annotation data, task metadata, workforce profiles, quality metrics, audit trail. JSONB for flexible annotation schemas per industry. |
| **Dashboard** | Grafana | Quality metrics, throughput tracking, workforce utilization, pipeline health. Accessible to ML leads and ops managers. |

---

## Key Product Decisions

| Decision | What We Chose | What We Rejected | Why |
|---|---|---|---|
| **Annotation schema** | JSONB-based configurable schemas | Fixed schema per annotation type | Healthcare NER, RLHF preference pairs, and LiDAR segmentation have fundamentally different data structures. JSONB lets each project define its own schema without database migrations. |
| **Quality measurement** | Multi-metric agreement engine | Single accuracy score | Cohen's kappa works for binary classification but not for NER span matching or bounding box overlap. Different annotation types need different agreement metrics (kappa, alpha, IoU, BLEU). The engine selects the appropriate metric based on task type. |
| **Task routing** | Skill-weighted routing with qualification gates | Round-robin assignment | A radiology annotation routed to an unqualified annotator wastes their time and produces bad data. Skill-based routing with mandatory qualification tests ensures annotators only receive tasks they're capable of. |
| **Review workflow** | Configurable multi-stage (1-3 stages) | Fixed two-stage (label + review) | RLHF safety annotations need 3 stages (label, review, expert adjudication). Product categorization needs 1 stage with spot-check sampling. The workflow engine is configurable per project. |
| **Active learning** | Uncertainty sampling + error-based curriculum | Random sampling for re-annotation | Random re-annotation wastes budget on examples the model already handles well. Uncertainty sampling targets the decision boundary where additional labels have the highest marginal value for model improvement. |
| **Consensus resolution** | Majority vote + expert tiebreak | Always defer to senior annotator | Majority vote surfaces genuine ambiguity (3 annotators, 3 different answers = genuinely hard example). Expert tiebreak only fires when majority vote fails, preserving expert time for cases that actually need judgment. |

---

## Metrics Framework

### North Star Metric

**Usable training examples produced per team-day**

Combines annotation throughput with quality. Only examples that pass quality thresholds count. Directly tied to what ML teams care about: how fast can they get clean data to improve their models.

**Baseline (ad hoc process):** 200 usable examples per day
**Target (with platform):** 2,000+ usable examples per day
**Achieved:** 2,340 usable examples per day (averaged across last 30 days)

### Input Metrics

| Category | Metric | Baseline | Target | Achieved |
|---|---|---|---|---|
| **Quality** | Annotation error rate | 12% | < 3% | 2.8% |
| | Inter-annotator agreement (kappa) | 0.62 | > 0.80 | 0.83 |
| | Golden set accuracy | 78% | > 95% | 96.2% |
| | Consensus resolution rate (without expert) | 60% | > 85% | 87% |
| **Throughput** | Annotations per annotator per hour | 25 | 45+ | 52 |
| | Task assignment latency | Minutes (manual) | < 2 seconds | 0.8 seconds |
| | Pipeline cycle time (submit to usable) | 5 days | < 2 days | 1.7 days |
| | Backlog age (oldest unassigned task) | 3+ days | < 4 hours | 2.8 hours |
| **Model Impact** | Data-to-model update cycle | 4-6 weeks | < 2 weeks | 11 days |
| | Model improvement per labeling batch | Unmeasured | Tracked per batch | +1.2% F1 avg per 5K examples |
| | Active learning efficiency vs. random | N/A | 2x | 2.4x (same model lift with 40% fewer labels) |
| **Workforce** | Annotator qualification rate | Untracked | > 70% | 74% |
| | Annotator retention (90-day) | ~40% | > 65% | 71% |
| | Time to productive (new annotator) | 2-3 weeks | < 3 days | 2.4 days |

### Business Impact

| Metric | Value | Calculation |
|---|---|---|
| Annual data pipeline value | **$4.2M** | Reduced labeling cost ($1.8M) + faster model iterations ($1.6M) + quality improvement ($0.8M) |
| Labeling cost per example | **$0.12** (from $0.45) | Fully loaded: annotator time + review + platform overhead |
| Model iteration speed | **3x faster** | Data pipeline no longer the bottleneck for model training cycles |
| Defective training data prevented | **~47K examples/year** | Examples that would have entered training pipeline with incorrect labels |

---

## Repository Structure

```
ai-data-ops-platform/
│
├── README.md
│
├── docs/
│   ├── PRD.md                         # Product requirements document
│   ├── ARCHITECTURE.md                # System architecture and integration design
│   ├── DATA_MODEL.md                  # Database schema, annotation storage, audit trail
│   ├── METRICS.md                     # Quality metrics, throughput, model impact measurement
│   ├── DECISION_LOG.md                # Key product and technical decisions
│   └── ROADMAP.md                     # Phased delivery plan
│
└── src/
    ├── task_engine/
    │   ├── schema_registry.py         # Configurable annotation schema management
    │   ├── task_router.py             # Skill-weighted task assignment with qualification gates
    │   └── queue_manager.py           # Priority queue management and backlog optimization
    │
    ├── annotation/
    │   ├── workflow_orchestrator.py    # Multi-stage annotation pipeline (label -> review -> adjudicate)
    │   ├── consensus_resolver.py      # Majority vote, weighted vote, expert tiebreak
    │   └── annotation_validator.py    # Schema validation, completeness checks, format enforcement
    │
    ├── quality/
    │   ├── agreement_calculator.py    # Cohen's kappa, Krippendorff's alpha, IoU, BLEU
    │   ├── annotator_scorer.py        # Per-annotator accuracy tracking and skill assessment
    │   └── golden_set_evaluator.py    # Gold standard evaluation and calibration
    │
    └── feedback/
        ├── active_learner.py          # Uncertainty sampling and curriculum construction
        ├── drift_detector.py          # Production data distribution vs. training data comparison
        └── model_evaluator.py         # Per-slice model performance and error analysis
```

---

## Reference Code

> **Note:** PM-authored prototypes built to validate feasibility, communicate architecture to engineering, benchmark implementation options, and demo to stakeholders. Not production code.

| File | What It Demonstrates |
|---|---|
| `task_engine/schema_registry.py` | JSONB-based annotation schema definition supporting text classification, NER spans, bounding boxes, preference pairs, and free-text. Schema versioning and migration. |
| `task_engine/task_router.py` | Skill-weighted task assignment algorithm. Qualification gate enforcement. Priority-based queue draining. Load balancing across annotator pool. |
| `task_engine/queue_manager.py` | Priority queue management with deadline-aware scheduling, backlog monitoring, and automatic escalation for aging tasks. |
| `annotation/workflow_orchestrator.py` | Temporal-based multi-stage annotation workflow. Configurable stages (1-3). Conditional routing based on agreement scores. Human-in-the-loop adjudication signals. |
| `annotation/consensus_resolver.py` | Multi-strategy consensus: majority vote, weighted vote (by annotator accuracy), expert tiebreak. Configurable per project based on quality requirements. |
| `annotation/annotation_validator.py` | Schema validation for incoming annotations. Completeness checking. Format enforcement. Cross-reference validation for multi-span NER. |
| `quality/agreement_calculator.py` | Implementation of Cohen's kappa, Fleiss' kappa, Krippendorff's alpha, IoU (bounding box), and BLEU (free-text). Metric selection based on annotation type. |
| `quality/annotator_scorer.py` | Per-annotator accuracy model. Rolling accuracy windows. Skill level classification (junior/senior/expert). Automatic de-qualification on sustained low accuracy. |
| `quality/golden_set_evaluator.py` | Golden set management: creation, insertion into task queues, evaluation, and calibration scoring. Annotators don't know which items are gold. |
| `feedback/active_learner.py` | Uncertainty sampling using model prediction entropy. Curriculum construction prioritizing high-uncertainty regions. Budget allocation across annotation categories. |
| `feedback/drift_detector.py` | Distribution comparison between production data and training data using KL divergence, PSI, and embedding centroid drift. Alerts when distributions diverge. |
| `feedback/model_evaluator.py` | Per-slice model performance analysis. Identifies systematic failure patterns (e.g., poor accuracy on medical abbreviations) and generates targeted re-annotation requests. |

---

## How These Prototypes Were Used

As PM, I wrote these to:

1. **Validate the quality measurement approach** by implementing agreement calculators to prove that different annotation types need different metrics. Demonstrated to the ML team that using accuracy alone (ignoring inter-annotator agreement) missed systematic labeling errors that were degrading model performance.
2. **Benchmark active learning ROI** by building the uncertainty sampler to show that targeted annotation achieves the same model improvement with 40% fewer labels than random sampling. This data point justified the engineering investment in the feedback loop infrastructure.
3. **Prove skill-based routing matters** by analyzing annotator accuracy distributions and showing that routing radiology tasks to top-quartile annotators reduced error rates from 12% to 3.1% with only a 15% throughput decrease. The quality-throughput tradeoff analysis informed the routing algorithm weights.
4. **Design the multi-stage workflow** by prototyping the orchestrator to explore how review stages interact with quality metrics. Discovered that a 20% spot-check review rate catches 94% of errors at 80% of the cost of full review, which became the default configuration for volume-oriented projects.
5. **Demonstrate drift detection to stakeholders** by running the drift detector against production data samples to show how training data ages out of relevance. This convinced leadership to fund the continuous feedback loop rather than treating training data as a one-time cost.

---

## Related Portfolio Projects

| Project | Domain | What It Shows |
|---|---|---|
| [Contract Intelligence Platform](../contract-intelligence-platform/) | Enterprise AI/ML | LLM orchestration, document processing pipelines, hybrid search, compliance-first design |
| [Verified Services Marketplace](../verified-services-marketplace/) | Two-Sided Marketplace | Supply/demand dynamics, trust & safety, escrow flows, marketplace health metrics |
| [Engagement & Personalization Engine](../engagement-personalization-engine/) | Consumer Growth | ML recommendations, A/B testing framework, feature flags, retention strategy |
| [Infrastructure Automation Platform](../infrastructure-automation-platform/) | Platform Engineering | Workflow orchestration, simulation testing, incident response, compliance automation |
