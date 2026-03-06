# AI Data Operations Platform - Improvements & Technology Roadmap

## Product Overview

The AI Data Operations Platform is an end-to-end annotation quality management system designed for ML teams that need high-quality labeled data at scale. It orchestrates the full annotation lifecycle: from schema-driven task creation and skill-based annotator routing, through multi-stage review workflows (label, review, adjudicate), to automated quality measurement via inter-annotator agreement metrics, golden set evaluation, and annotator performance scoring.

The platform closes the feedback loop between model performance and data collection by integrating active learning (selecting the most uncertain samples for annotation), production data drift detection, and per-slice model evaluation to generate targeted re-annotation requests where they will have the highest marginal impact.

**Core use cases supported:** RLHF preference labeling, radiology bounding box annotation, clinical NER, fraud classification, and content moderation -- all configurable via JSONB-based annotation schemas without code changes.

---

## Current Architecture

### Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend API** | FastAPI 0.115.0 / Python 3.11 | REST API serving annotation workflows |
| **Database** | PostgreSQL 15 + pgvector | Primary data store with embedding search |
| **Managed DB** | Supabase (PostgreSQL + RLS) | Hosted database with row-level security |
| **Cache/Queue** | Redis 7 / Upstash Redis | Task queuing, real-time updates |
| **Workflow Engine** | Temporal 1.3.0 (legacy) / Trigger.dev v3 (current) | Durable workflow orchestration |
| **Background Jobs** | Trigger.dev | Quality scoring, active learning batch jobs |
| **Visual Workflows** | n8n | Low-code automation pipelines |
| **Auth** | Clerk | User authentication |
| **Email** | Resend + React Email | Transactional notifications |
| **Deployment** | Vercel (Next.js frontend) + Docker | Hosting and containerization |
| **Monitoring** | OpenTelemetry + Prometheus + Grafana | Observability stack |
| **ML Libraries** | scikit-learn 1.3.2, numpy 1.26, pandas 2.1, scipy 1.11 | Agreement metrics, statistics |
| **ORM** | SQLAlchemy 2.0.36 + Alembic 1.14.0 | Database access and migrations |

### Key Components

| Module | File | Responsibility |
|--------|------|---------------|
| **Schema Registry** | `src/task_engine/schema_registry.py` | JSONB-based annotation schema management with industry presets, versioning, validation |
| **Task Router** | `src/task_engine/task_router.py` | Skill-weighted task assignment with qualification gates and accuracy-weighted scoring |
| **Queue Manager** | `src/task_engine/queue_manager.py` | Priority queuing with deadline awareness, auto-escalation, capacity forecasting |
| **Workflow Orchestrator** | `src/annotation/workflow_orchestrator.py` | Multi-stage workflows (label/review/adjudicate) with conditional routing |
| **Consensus Resolver** | `src/annotation/consensus_resolver.py` | Multi-strategy label resolution (majority vote, weighted vote, expert tiebreak) |
| **Annotation Validator** | `src/annotation/annotation_validator.py` | Structural/semantic validation, speed anomaly detection, pre-label anchoring detection |
| **Agreement Calculator** | `src/quality/agreement_calculator.py` | 7 inter-annotator agreement metrics auto-selected by annotation type |
| **Annotator Scorer** | `src/quality/annotator_scorer.py` | Rolling accuracy tracking, skill classification, gaming detection |
| **Golden Set Evaluator** | `src/quality/golden_set_evaluator.py` | Ground truth insertion, rotation, anti-gaming detection |
| **Active Learner** | `src/feedback/active_learner.py` | Uncertainty/margin sampling with 70/30 AL/random split |
| **Drift Detector** | `src/feedback/drift_detector.py` | KL divergence, PSI, embedding centroid drift with 3-window confirmation |
| **Model Evaluator** | `src/feedback/model_evaluator.py` | Per-slice performance analysis, error pattern clustering, re-annotation generation |

### How It Works

1. **Schema Definition** -- ML teams select an industry preset or define a custom JSONB schema. The schema determines annotation UI, validation rules, and quality metrics.
2. **Task Ingestion** -- Data items are enqueued with priority scores. Active learning items and deadline-approaching tasks get boosted.
3. **Routing** -- The task router matches tasks to annotators using a weighted scoring formula (accuracy 40%, workload 30%, consistency 15%, priority 15%) with binary qualification gates.
4. **Annotation** -- Multiple annotators label each item (configurable overlap). Submissions are validated at submission time.
5. **Agreement & Consensus** -- Inter-annotator agreement is computed using the metric appropriate to the annotation type. High agreement auto-accepts; low agreement routes to review.
6. **Quality Tracking** -- Golden set items measure annotator accuracy in real time. Rolling windows detect degradation. Auto-dequalification fires after 5 consecutive golden failures.
7. **Feedback Loop** -- Active learning selects high-uncertainty samples. Drift detection monitors production data. Model evaluation identifies weak slices and generates targeted re-annotation requests.

---

## Recommended Improvements

### 1. Persistent Storage for Core Engine Classes

**Problem:** All core Python classes (`SchemaRegistry`, `TaskRouter`, `QueueManager`, `WorkflowOrchestrator`, etc.) use in-memory `dict` storage. Data is lost on restart.

**Files affected:**
- `src/task_engine/schema_registry.py` (line 143-145: `self.schemas: dict[UUID, AnnotationSchema] = {}`)
- `src/task_engine/task_router.py` (line 155-158: `self.annotators`, `self.task_queue`, `self.assignments`)
- `src/task_engine/queue_manager.py` (line 119-121: `self.project_queues`, `self.completion_log`)
- `src/annotation/workflow_orchestrator.py` (line 160: `self.workflows: dict[UUID, WorkflowState] = {}`)

**Recommendation:** Implement a repository pattern with Supabase/SQLAlchemy backends. The Supabase schema (`supabase/migrations/001_initial_schema.sql`) already defines the tables; the Python classes need corresponding repository classes that serialize/deserialize dataclass instances to/from the database.

```python
# Example: SchemaRepository backed by Supabase
class SchemaRepository:
    def __init__(self, supabase_client):
        self.client = supabase_client

    async def save(self, schema: AnnotationSchema) -> None:
        data = schema_to_jsonb(schema)
        await self.client.table("annotation_schemas").upsert(data).execute()

    async def get(self, schema_id: UUID) -> Optional[AnnotationSchema]:
        result = await self.client.table("annotation_schemas").select("*").eq("id", str(schema_id)).single().execute()
        return jsonb_to_schema(result.data) if result.data else None
```

### 2. Replace Simplified Rule Evaluator with a Proper Expression Engine

**Problem:** The validation rule evaluator in `schema_registry.py` (lines 769-834) uses fragile regex matching for conditions like `"preferred != 'tie'"`. It only handles 3 patterns and silently passes on any unrecognized pattern.

**Recommendation:** Integrate a safe expression evaluation library:

- **Option A:** Use `pycel` or `simpleeval` (https://github.com/danthedeckie/simpleeval) for sandboxed expression evaluation
- **Option B:** Define a small DSL using Lark parser (https://github.com/lark-parser/lark) for type-safe rule expressions
- **Option C:** Use JSON Logic (https://jsonlogic.com/) via `json-logic-py` for portable rule definitions that can be evaluated in both Python and JavaScript

JSON Logic is the best fit because rules are already stored as JSONB and would need to be evaluated on both the backend (Python) and frontend (TypeScript annotation UI).

### 3. Async Support Across the Codebase

**Problem:** The FastAPI application uses `uvicorn` with async capabilities, and `httpx` and `aiohttp` are in `requirements.txt`, but all core Python classes are synchronous. Database queries, Redis operations, and external API calls will block the event loop.

**Files affected:** All 12 core Python modules use synchronous methods exclusively.

**Recommendation:** Convert core methods to `async/await`, especially:
- Database operations (use `sqlalchemy.ext.asyncio`)
- Redis operations (use `redis.asyncio`)
- Temporal/workflow calls
- Any I/O-bound computation in the quality pipeline

### 4. Proper Error Handling and Structured Logging

**Problem:** Error handling is minimal. Many methods return `None` or empty dicts on failure without logging. The `structlog` dependency is declared in `requirements.txt` but not used in any source file.

**Recommendation:**
- Add structured logging with `structlog` throughout the pipeline
- Define custom exception hierarchy: `SchemaValidationError`, `QualificationError`, `ConsensusError`, `DriftAlertError`
- Add correlation IDs (trace IDs) that flow through the entire annotation lifecycle for end-to-end debugging
- Integrate with OpenTelemetry spans (already in requirements) for distributed tracing

### 5. Implement Real API Layer

**Problem:** The Dockerfile references `src.api.main:app` but no API module exists in the source tree. The system has no REST endpoints.

**Recommendation:** Build a FastAPI router layer that exposes the core engine:

```
POST /api/v1/schemas                    -- Create annotation schema
POST /api/v1/tasks                      -- Enqueue annotation tasks
POST /api/v1/tasks/{id}/annotations     -- Submit annotation
POST /api/v1/tasks/{id}/review          -- Submit review decision
GET  /api/v1/quality/batch/{batch_id}   -- Get batch quality scores
GET  /api/v1/annotators/{id}/scorecard  -- Get annotator performance
POST /api/v1/active-learning/select     -- Trigger AL batch selection
GET  /api/v1/drift/{project_id}         -- Get drift monitoring status
```

### 6. Add Comprehensive Test Coverage

**Problem:** Only 2 test files exist (`test_agreement_calculator.py`, `test_consensus_resolver.py`). 10 out of 12 core modules have no tests.

**Recommendation:**
- Add unit tests for all core modules, especially edge cases in:
  - `task_router.py`: qualification gates, deadline boost calculations, reservation expiration
  - `queue_manager.py`: escalation sweep logic, capacity forecasting with zero throughput
  - `workflow_orchestrator.py`: all stage transition paths, duplicate annotator detection
  - `annotation_validator.py`: all validation rules, temporal consistency
  - `drift_detector.py`: three-window confirmation, severe drift bypass
- Add integration tests for the full pipeline (schema creation through model evaluation)
- Target 80%+ line coverage

### 7. Strengthen the Consensus Resolver with Bayesian Methods

**Problem:** The weighted vote in `consensus_resolver.py` uses simple accuracy-weighted averaging. This does not account for per-class accuracy differences or annotator bias patterns.

**Recommendation:** Implement Dawid-Skene (1979) or GLAD (Generative model of Labels, Abilities, and Difficulties) for probabilistic consensus estimation:

- **Dawid-Skene** models each annotator's confusion matrix and iteratively estimates both true labels and annotator reliability via EM
- This naturally handles cases where an annotator is accurate on class A but biased on class B
- Libraries: `crowdkit` by Toloka (https://github.com/Toloka/crowd-kit) provides production-ready implementations of Dawid-Skene, GLAD, MACE, and other aggregation methods

### 8. Connection Pooling and Database Performance

**Problem:** The `docker-compose.yml` sets `max_connections=200` but there is no connection pooling configured. Each request creating a new database connection will exhaust the pool under load.

**Recommendation:**
- Configure SQLAlchemy async connection pool with `pool_size=20`, `max_overflow=10` (matching `.env.example`)
- Add PgBouncer as a connection pooler in `docker-compose.yml` for production deployments
- Add database query caching for frequently accessed data (schema definitions, annotator profiles) using Redis

---

## New Technologies & Trends

### Data Annotation Quality

#### 1. Crowd-Kit by Toloka
- **What:** Open-source library implementing 20+ annotation aggregation algorithms (Dawid-Skene, GLAD, MACE, BCC, ZeroBasedSkill, etc.)
- **Version:** 1.4.1+
- **Repository:** https://github.com/Toloka/crowd-kit
- **Why it helps:** The current `ConsensusResolver` implements only majority vote and accuracy-weighted vote. Crowd-Kit provides probabilistic aggregation methods that jointly estimate true labels and annotator reliability, achieving 3-8% higher accuracy than simple voting on benchmarks.
- **Integration:** Replace `ConsensusResolver._weighted_vote()` with Crowd-Kit's `DawidSkene` or `GLAD` estimators. The `AnnotatorVote` dataclass already carries the `accuracy_score` and `annotator_id` fields needed.

```python
from crowdkit.aggregation import DawidSkene
import pandas as pd

# Convert votes to Crowd-Kit format
df = pd.DataFrame([
    {"task": str(v.task_id), "worker": str(v.annotator_id), "label": v.annotation_data.get("label")}
    for v in votes
])
result = DawidSkene(n_iter=20).fit_predict(df)
```

#### 2. Cleanlab
- **What:** Data-centric AI library for finding label errors, outliers, and data quality issues automatically using confident learning
- **Version:** 2.6+
- **Repository:** https://github.com/cleanlab/cleanlab
- **Why it helps:** Complements the golden set approach by automatically detecting label errors in the training data without requiring ground truth. Can identify mislabeled items that passed consensus but are still wrong.
- **Integration:** Run Cleanlab's `find_label_issues()` on completed annotation batches as a post-consensus quality check. Items flagged by Cleanlab would be routed back to expert review. This would be a new module: `src/quality/label_error_detector.py`.

#### 3. Argilla
- **What:** Open-source platform for data curation and AI feedback, designed for RLHF, instruction tuning, and text classification
- **Version:** 2.x (major rewrite from v1)
- **Repository:** https://github.com/argilla-io/argilla
- **Why it helps:** Provides a mature annotation UI with built-in support for RLHF preference pairs, NER, text classification -- matching this platform's schema presets. Could serve as the annotation frontend while this platform handles the quality/routing backend.
- **Integration:** Use Argilla's REST API as the annotation interface layer. The platform's `WorkflowOrchestrator` would push tasks to Argilla workspaces and receive completed annotations via webhooks.

### ML Monitoring & Observability

#### 4. Evidently AI
- **What:** Open-source ML observability platform for data drift detection, model quality monitoring, and test suites
- **Version:** 0.5.x+
- **Repository:** https://github.com/evidentlyai/evidently
- **Why it helps:** The current `DriftDetector` implements KL divergence, PSI, and cosine distance manually. Evidently provides 100+ pre-built data drift detection methods (Wasserstein distance, KS test, Jensen-Shannon divergence, chi-squared test) with automatic statistical test selection, visualization dashboards, and alerting.
- **Integration:** Replace `DriftDetector._kl_divergence()`, `_psi()`, and `_cosine_distance()` with Evidently's `DataDriftPreset`. Evidently can generate HTML reports that integrate with the existing Grafana dashboard.

```python
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset

report = Report(metrics=[DataDriftPreset()])
report.run(reference_data=baseline_df, current_data=production_df)
```

#### 5. Whylogs by WhyLabs
- **What:** Lightweight data logging library that profiles datasets with approximate statistics (histograms, frequent items, distribution summaries) in a mergeable, privacy-preserving format
- **Version:** 1.4+
- **Repository:** https://github.com/whylabs/whylogs
- **Why it helps:** Enables continuous data profiling at ingestion time rather than batch snapshot comparison. The `DriftDetector` currently requires full distribution snapshots; whylogs profiles are ~1000x smaller and can be computed on streaming data.
- **Integration:** Add whylogs profiling to the annotation ingestion pipeline. Compare profiles over time windows for drift detection. Profiles can be uploaded to WhyLabs for managed monitoring.

### Data Validation

#### 6. Great Expectations
- **What:** Data validation and documentation framework with 300+ built-in expectations
- **Version:** 1.x (major rewrite, previously 0.18.x)
- **Repository:** https://github.com/great-expectations/great_expectations
- **Why it helps:** The `AnnotationValidator` implements structural validation manually. Great Expectations provides a declarative approach to data validation with automatic documentation, data profiling, and integration with data pipelines.
- **Integration:** Define annotation quality expectations as GX expectation suites. For example: `expect_column_values_to_be_in_set("preferred", ["A", "B", "tie"])`, `expect_column_value_lengths_to_be_between("reasoning", min_value=20)`. These would complement the JSONB schema validation rules.

#### 7. Pandera
- **What:** Statistical data validation library for pandas DataFrames with type annotations
- **Version:** 0.20+
- **Repository:** https://github.com/unionai-contrib/pandera
- **Why it helps:** Lighter-weight alternative to Great Expectations, better suited for validating annotation batches represented as DataFrames. Supports hypothesis testing and schema inference.
- **Integration:** Define Pandera schemas for annotation batch exports, ensuring statistical properties (e.g., label distribution within expected range, no annotator contributing >30% of labels in a batch).

### Workflow Orchestration

#### 8. Inngest
- **What:** Event-driven workflow orchestration platform with durable execution, step functions, and automatic retries
- **Repository:** https://github.com/inngest/inngest
- **Why it helps:** The project already migrated from Temporal to Trigger.dev for simpler background jobs. Inngest offers a middle ground: simpler than Temporal but more powerful than Trigger.dev for complex multi-step workflows with human-in-the-loop signals. Supports fan-out/fan-in patterns needed for multi-annotator workflows.
- **Integration:** Model the annotation workflow stages (label, agreement check, review, adjudicate) as Inngest step functions. Use Inngest's `waitForEvent` for human-in-the-loop review decisions, replacing the current in-memory workflow state.

#### 9. Hatchet
- **What:** Open-source distributed task queue and workflow engine built on PostgreSQL, designed as a modern alternative to Celery/Temporal
- **Version:** 0.40+
- **Repository:** https://github.com/hatchet-dev/hatchet
- **Why it helps:** Unlike Trigger.dev (SaaS-only runtime), Hatchet is self-hostable and uses PostgreSQL (already in the stack) as its backing store. It provides durable execution with DAG-based workflows, rate limiting, and concurrency control.
- **Integration:** Replace the in-memory workflow orchestration with Hatchet workflows. The annotation pipeline becomes a DAG: ingest -> assign -> (parallel annotations) -> agreement check -> (conditional) review -> complete.

### LLM-Assisted Annotation

#### 10. LLM-as-Judge for Pre-labeling and Quality Checks
- **What:** Using large language models (GPT-4, Claude, Llama) as automated annotators for pre-labeling, quality estimation, and second-opinion generation
- **Why it helps:** The platform already supports pre-label anchoring detection (`annotation_validator.py`, lines 448-483). LLM-generated pre-labels could replace or augment model prediction-based pre-labels, especially for subjective tasks like RLHF preference labeling and content moderation.
- **Integration:**
  - Add an `LLMPreLabeler` module that generates pre-labels using configurable LLM endpoints
  - Use LLM confidence scores as an additional signal in the `ActiveLearner` uncertainty calculation
  - Implement "LLM-as-third-annotator" for borderline disagreement cases, reducing expert review load
  - Libraries: LangChain (https://github.com/langchain-ai/langchain), LiteLLM (https://github.com/BerriAI/litellm) for multi-provider LLM access

#### 11. Embedding-Based Similarity for Smart Routing
- **What:** Using sentence/image embeddings to cluster similar annotation items and route them to the same annotator for consistency
- **Why it helps:** The `TaskRouter` already has a `consistency_bonus` (1.2x) for same task group, but task groups are manually assigned. Embedding-based clustering would automatically group semantically similar items.
- **Integration:**
  - The database already has a `vector(768)` column on `model_predictions` with an IVFFlat index
  - Use sentence-transformers or OpenAI embeddings to cluster incoming annotation items
  - Route clustered items to the same annotator via the task group mechanism
  - Libraries: `sentence-transformers` (https://github.com/UKPLab/sentence-transformers), `FAISS` (https://github.com/facebookresearch/faiss)

### Infrastructure & DevOps

#### 12. BullMQ (Redis Queue Upgrade)
- **What:** Modern, TypeScript-native Redis-based queue with built-in support for priorities, rate limiting, delayed jobs, and flows
- **Version:** 5.x
- **Repository:** https://github.com/taskforcesh/bullmq
- **Why it helps:** The current `QueueManager` implements priority queuing in-memory with plans for Redis sorted sets. BullMQ provides production-ready priority queues on Redis with built-in job lifecycle management, rate limiting, and dashboard (Bull Board).
- **Integration:** Replace the in-memory `QueueManager` with BullMQ for the TypeScript layer (Trigger.dev jobs, Next.js API routes). The priority tier mapping (`PriorityTier` enum values) maps directly to BullMQ's priority parameter.

#### 13. Supabase Realtime for Live Annotation Updates
- **What:** Supabase's built-in Postgres Changes feature that broadcasts database changes over WebSocket
- **Why it helps:** Annotation workflows require real-time status updates (new task assigned, annotation submitted, review needed). The current architecture has WebSocket support (`websockets==12.0` in requirements) but no implementation.
- **Integration:** Subscribe to Supabase Realtime channels for `annotation_tasks`, `annotations`, and `consensus_results` table changes. Push updates to annotator UIs and the ops dashboard without polling.

#### 14. Sentry for Error Tracking (Already Configured, Not Integrated)
- **What:** Application error monitoring with context-rich error reports
- **Why it helps:** The `.env.example` declares `SENTRY_DSN` but Sentry SDK is not in `requirements.txt` or used in any source file.
- **Integration:** Add `sentry-sdk[fastapi]==2.x` to requirements. Initialize in the FastAPI app with performance monitoring. Tag errors with annotation project, task type, and annotator context.

---

## Priority Roadmap

### P0 -- Critical (Week 1-2)

| # | Improvement | Rationale |
|---|------------|-----------|
| 1 | **Build the FastAPI API layer** (`src/api/`) | The Dockerfile references `src.api.main:app` but it does not exist. Without API endpoints, the system cannot be used. |
| 2 | **Connect core classes to Supabase/PostgreSQL** | All 12 modules use in-memory dicts. The database schema already exists in `supabase/migrations/001_initial_schema.sql`. Wire them together with async repository classes. |
| 3 | **Add async support to core modules** | FastAPI is async-native. Synchronous database and Redis calls in request handlers will block the event loop and destroy throughput under load. |

### P1 -- High Priority (Week 3-6)

| # | Improvement | Rationale |
|---|------------|-----------|
| 4 | **Implement structured logging with structlog** | Already in requirements but unused. Critical for production debugging and audit trails. Add correlation IDs flowing through annotation workflows. |
| 5 | **Add unit tests for all core modules** | Only 2 of 12 modules have tests. The workflow orchestrator, task router, and drift detector have complex branching logic that is easily broken during refactoring. Target 80% coverage. |
| 6 | **Replace regex rule evaluator with JSON Logic** | The current rule engine (`schema_registry.py` lines 769-834) handles only 3 regex patterns and silently passes on unrecognized rules. JSON Logic provides portable, safe expression evaluation in both Python and TypeScript. |
| 7 | **Integrate Crowd-Kit for probabilistic consensus** | Replace simple weighted voting with Dawid-Skene or GLAD. The 5% accuracy improvement demonstrated in DEC-004 backtest would increase further with proper probabilistic aggregation. |
| 8 | **Integrate Evidently for drift detection** | Replace hand-rolled KL divergence and PSI with Evidently's 100+ statistical tests. Adds automatic test selection, visualization, and alerting. |

### P2 -- Medium Priority (Week 7-12)

| # | Improvement | Rationale |
|---|------------|-----------|
| 9 | **Integrate Cleanlab for automated label error detection** | Post-consensus quality check that finds mislabeled items without ground truth. Catches errors that pass through agreement thresholds. |
| 10 | **Add LLM-as-Judge pre-labeling** | Use LLM predictions as pre-labels for subjective tasks (RLHF, content moderation). The anchoring detection in `annotation_validator.py` already monitors pre-label acceptance rates. |
| 11 | **Implement embedding-based task clustering** | Auto-group semantically similar items for routing consistency. The pgvector infrastructure and IVFFlat index already exist in the database schema. |
| 12 | **Add Supabase Realtime for live updates** | Replace polling with WebSocket-based real-time updates for annotation dashboards and task assignment notifications. |
| 13 | **Add Sentry error tracking** | Already configured in `.env.example` but not integrated. Add SDK, initialize in FastAPI, tag with annotation context. |
| 14 | **Add connection pooling with PgBouncer** | Production deployment will exhaust PostgreSQL connection limits without a connection pooler. Add to `docker-compose.yml`. |

### P3 -- Nice to Have (Quarter 2+)

| # | Improvement | Rationale |
|---|------------|-----------|
| 15 | **Migrate workflow engine to Hatchet or Inngest** | The in-memory `WorkflowOrchestrator` needs durable execution for production. Hatchet is self-hostable on PostgreSQL (already in stack). Inngest provides managed durable functions with `waitForEvent` for human-in-the-loop. |
| 16 | **Integrate Argilla as annotation frontend** | Argilla 2.x provides a mature annotation UI for RLHF, NER, and classification. Use this platform as the quality/routing backend with Argilla as the labeling interface. |
| 17 | **Add whylogs for continuous data profiling** | Replace batch snapshot comparison in `DriftDetector` with continuous profiling. 1000x smaller profiles enable real-time drift monitoring on streaming data. |
| 18 | **Implement Pandera for batch export validation** | Validate statistical properties of annotation exports (label distribution, annotator contribution balance, completeness) before training data delivery. |
| 19 | **Add BullMQ for production Redis queuing** | Replace in-memory priority queues with BullMQ's production-ready implementation. Includes rate limiting, job lifecycle management, and Bull Board dashboard. |
| 20 | **Build annotation efficiency analytics** | Track cost-per-label, time-to-consensus, escalation rates, and active learning ROI across projects. The `EfficiencyMetrics` dataclass in `active_learner.py` provides the foundation. |
| 21 | **Add multi-modal annotation support** | The `InputType` enum already includes `VIDEO`, `AUDIO`, `POINT_CLOUD`, and `DOCUMENT` but the validation and agreement calculation only handles text, images, and bounding boxes. Extend `AgreementCalculator` and `AnnotationValidator` for these input types. |
| 22 | **Implement annotation guideline versioning** | Track which version of annotation guidelines each annotator trained on. When guidelines change, flag annotations created under old guidelines for potential re-review. |

---

## Technology Reference Links

| Technology | Repository / Documentation |
|-----------|---------------------------|
| Crowd-Kit (annotation aggregation) | https://github.com/Toloka/crowd-kit |
| Cleanlab (label error detection) | https://github.com/cleanlab/cleanlab |
| Argilla (annotation UI) | https://github.com/argilla-io/argilla |
| Evidently AI (ML monitoring) | https://github.com/evidentlyai/evidently |
| whylogs (data profiling) | https://github.com/whylabs/whylogs |
| Great Expectations (data validation) | https://github.com/great-expectations/great_expectations |
| Pandera (DataFrame validation) | https://github.com/unionai-contrib/pandera |
| Inngest (workflow orchestration) | https://github.com/inngest/inngest |
| Hatchet (task queue/workflows) | https://github.com/hatchet-dev/hatchet |
| BullMQ (Redis queue) | https://github.com/taskforcesh/bullmq |
| JSON Logic (rule engine) | https://jsonlogic.com/ / https://github.com/nadirizr/json-logic-py |
| LiteLLM (multi-LLM gateway) | https://github.com/BerriAI/litellm |
| sentence-transformers (embeddings) | https://github.com/UKPLab/sentence-transformers |
| FAISS (vector search) | https://github.com/facebookresearch/faiss |
| simpleeval (safe expressions) | https://github.com/danthedeckie/simpleeval |
| Sentry (error tracking) | https://github.com/getsentry/sentry-python |
| Supabase Realtime | https://supabase.com/docs/guides/realtime |
