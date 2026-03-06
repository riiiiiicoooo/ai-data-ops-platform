# Architecture Decision Records

This document captures key architectural decisions made during the design and implementation of the AI Data Operations Platform. Each ADR explains the context, the decision, what alternatives were evaluated, and the resulting trade-offs.

For product-level decisions (e.g., build vs. buy, metrics framework choices), see [DECISION_LOG.md](./DECISION_LOG.md).

---

## ADR-001: Temporal-Based Durable Workflow Orchestration for Annotation Pipelines

**Status:** Accepted
**Date:** 2024-01
**Context:** Annotation workflows are multi-stage (label, review, adjudicate), span hours to days waiting for human decisions, and must survive system failures without losing annotator work. The platform needs configurable 1-3 stage pipelines per project, conditional routing based on agreement scores, timeout-based reassignment, and human-in-the-loop signals where a workflow pauses indefinitely until a reviewer submits their decision.
**Decision:** Use Temporal as the durable workflow orchestration engine. Workflow logic is expressed as Python code in `workflow_orchestrator.py`, where each stage is modeled as a Temporal activity or signal handler. The orchestrator creates a workflow per task, collects annotations until the overlap target is met, computes agreement, and routes based on configurable thresholds: high agreement auto-accepts (skipping review), low agreement routes to review, and reviewer escalation triggers adjudication.
**Alternatives Considered:**
- *Celery task chains:* Designed for short-lived execution, not multi-day waits. Human-in-the-loop pausing would require periodic polling hacks, which are fragile and resource-wasteful.
- *State machine in application code with PostgreSQL:* Works for simple flows but becomes unmaintainable as complexity grows. The platform has 3 workflow variants, conditional routing based on agreement scores, timeout-based reassignment, and escalation -- resulting in 15+ state transitions that are difficult to reason about in a transition table.
- *Simple queue-based processing (Redis + custom workers):* No built-in durability, replay, or signal handling. Every failure mode would need custom recovery logic.

**Consequences:**
- Workflows survive crashes and resume from the last completed step via Temporal's replay mechanism. Zero annotation data loss on system failure.
- Human-in-the-loop decisions are handled natively via `wait_for_signal("review_decision")`, eliminating polling.
- Adds infrastructure complexity: Temporal server requires its own PostgreSQL database, gRPC port (7233), and worker processes, as visible in `docker-compose.yml`.
- Workflow logic in `workflow_orchestrator.py` is readable Python rather than a state transition table, making it accessible to the engineering team.
- The `WorkflowConfig` dataclass enables per-project configuration of stages (1-3), overlap count, auto-accept threshold, consensus method, review sample rate, and timeout durations without code changes.

---

## ADR-002: JSONB-Based Configurable Annotation Schemas with Auto-Metric Selection

**Status:** Accepted
**Date:** 2024-01
**Context:** The platform must support fundamentally different annotation types across industries -- RLHF preference pairs, radiology bounding boxes, clinical NER spans, fraud classification, and content moderation -- each with different input types, output structures, validation rules, and UI configurations. New annotation types need to be deployable without database migrations or code changes.
**Decision:** Store annotation schemas as JSONB documents managed by a `SchemaRegistry` (in `schema_registry.py`). Each schema defines input type, output fields with typed validation, cross-field validation rules, UI configuration, and auto-selected agreement metrics. The registry supports schema versioning with backward compatibility checks (new versions must be supersets of previous versions), industry presets for rapid project setup, and automatic agreement metric selection based on output field type (e.g., `ENUM` maps to Cohen's kappa, `BOUNDING_BOX` maps to IoU, `SPANS` maps to span F1).
**Alternatives Considered:**
- *Fixed database tables per annotation type:* Would require a new migration, code deployment, and QA cycle for each new annotation type. With 9 distinct types across 4 clients in the first 6 months, this would have meant 9 migrations. JSONB required zero.
- *Code-based annotation type definitions:* Each type as a Python class with its own validation. Faster than migrations but still requires a code deployment for new types, preventing self-service by annotation leads.
- *External schema service (e.g., JSON Schema validator):* Adds a network dependency to the validation hot path. Schema validation runs at submission time and must be fast.

**Consequences:**
- A new annotation type (e.g., BI-RADS radiology scoring) can be configured in 10 minutes without a database migration, as demonstrated in the schema registry's `create_from_preset` method.
- Five industry presets (`rlhf_preference`, `radiology_bbox`, `clinical_ner`, `fraud_classification`, `content_moderation`) provide instant project setup.
- Schema versioning prevents breaking existing annotations: the `_check_backward_compatibility` method enforces that existing field names and enum values cannot be removed.
- Weaker database-level validation compared to typed columns. Compensated by application-layer validation in `SchemaRegistry.validate_annotation()` and `AnnotationValidator`.
- JSONB aggregation queries are slower than typed column queries. Mitigated by pre-computing quality metrics incrementally rather than querying raw JSONB at dashboard time.

---

## ADR-003: Multi-Strategy Consensus Resolution with Accuracy-Weighted Voting

**Status:** Accepted
**Date:** 2024-02
**Context:** When multiple annotators label the same item and disagree, the platform must produce a single resolved label. The resolution method directly affects training data quality. A backtest on 2,000 annotations with expert ground truth showed that the choice of consensus method has measurable impact on label correctness.
**Decision:** Implement three consensus strategies in `ConsensusResolver` with accuracy-weighted voting as the default: (1) majority vote for new projects without established accuracy baselines, (2) weighted vote where each annotator's vote is weighted by their rolling accuracy score on the task type, and (3) expert tiebreak as a fallback when automated methods fail. The weighted vote selects the winning label's annotation from the highest-accuracy annotator who voted for it, ensuring the best-quality annotation data (e.g., tightest bounding box, most detailed reasoning) is preserved.
**Alternatives Considered:**
- *Simple majority vote only:* Straightforward but two lower-accuracy annotators can outvote one expert. The backtest showed 86% agreement with expert ground truth vs. 91% for weighted vote -- a 5% gap that at 100K annotations means 5,000 fewer incorrect consensus labels.
- *Always defer to highest-rated annotator:* Ignores the wisdom of multiple perspectives. When two annotators agree on a label that the expert disagrees with, the majority is often correct because the expert may have misread the specific item.
- *Probabilistic models (Dawid-Skene):* More statistically rigorous but significantly more complex to implement and explain to stakeholders. The weighted vote approach is transparent and the 91% accuracy is sufficient.

**Consequences:**
- Weighted vote agrees with expert ground truth 91% of the time, a 5% improvement over majority vote at scale.
- The `MIN_WEIGHTED_MARGIN` threshold (0.05) prevents false consensus when weighted scores are nearly tied, routing genuinely ambiguous items to expert review rather than forcing a low-confidence resolution.
- Batch resolution via `resolve_batch` processes multiple tasks and produces distribution analytics (resolution rate, average agreement, expert needs count) for the ops dashboard.
- Expert time is preserved for genuinely ambiguous cases. Target: 85%+ of items resolve without expert involvement.
- The system tracks which annotator's full annotation data is selected for the consensus label, maintaining provenance.

---

## ADR-004: Multi-Metric Agreement Engine with Automatic Metric Selection

**Status:** Accepted
**Date:** 2024-02
**Context:** The platform needs to measure annotation quality, but a single accuracy percentage is misleading across different annotation types. Raw accuracy on imbalanced classification (90% legitimate, 10% fraud) shows 90% for an annotator who labels everything "legitimate." Spatial annotations (bounding boxes) and sequential annotations (NER spans) cannot be evaluated with classification metrics at all.
**Decision:** Implement seven agreement metrics in `AgreementCalculator`, auto-selected by the schema registry based on annotation output type: Cohen's kappa (2 annotators, categorical), Fleiss' kappa (3+ annotators, categorical), Krippendorff's alpha (variable annotator counts, handles missing data), IoU (bounding box spatial agreement), Dice coefficient (segmentation masks), span-level F1 (NER with both exact and relaxed matching), and BLEU (free-text similarity). The `OUTPUT_TYPE_TO_METRIC` mapping in `schema_registry.py` automatically selects the primary metric, with optional secondary metrics (e.g., BLEU for reasoning text fields).
**Alternatives Considered:**
- *Single accuracy score:* Fails on imbalanced data, inapplicable to spatial/sequential annotations. A fraud classification annotator labeling everything "legitimate" scores 90% accuracy but 0.0 kappa.
- *Only kappa-family metrics:* Handles classification well but provides no information about spatial quality of bounding boxes or character-level precision of NER spans.
- *External quality service:* Adds latency and a network dependency. Agreement calculations need to run inline during the workflow's agreement check stage.

**Consequences:**
- Per-project quality thresholds are tuned to the annotation type: healthcare radiology requires IoU > 0.80 for bounding boxes; RLHF preference projects require kappa > 0.70.
- The `compute_agreement` method in `AgreementCalculator` provides a single entry point that auto-selects the metric based on annotation type. Callers do not need to know which metric applies.
- All metrics include an `interpretation` field using the Landis & Koch scale (strong/moderate/fair/slight/poor), providing standardized quality assessment across metric types.
- Implementation is approximately 600 lines of pure Python with no external ML library dependency for the core calculations, keeping the quality engine lightweight.

---

## ADR-005: Skill-Weighted Task Routing with Qualification Gates

**Status:** Accepted
**Date:** 2024-02
**Context:** Task assignment determines annotation quality at the source. Analysis showed that routing radiology tasks to top-quartile annotators reduced error rates from 12% to 3.1% with only a 15% throughput decrease. Unqualified annotators on specialized tasks produce bad data 40-50% of the time. The platform needs a routing algorithm that balances qualification, accuracy, workload, task consistency, and priority.
**Decision:** Implement a multi-factor scoring algorithm in `TaskRouter` that computes a composite assignment score: qualification match (binary gate: 0 eliminates the annotator entirely), accuracy weight (40%, based on rolling accuracy for the task type), workload factor (30%, inverse of current load), consistency bonus (15%, for same task group continuity), and priority factor (15%, boosting top-quartile annotators for active learning and error curriculum tasks). The router supports both pull (annotator requests next task) and push (high-priority task assigned to best annotator) models, with task reservation timeouts that re-queue abandoned tasks.
**Alternatives Considered:**
- *Round-robin assignment:* Ignores annotator capabilities entirely. A radiology task goes to whoever is next, regardless of qualification or accuracy.
- *Simple qualification filter + FIFO:* Checks qualifications but does not optimize for accuracy or workload balance. Does not prioritize high-value tasks (active learning samples) to the most accurate annotators.
- *ML-based assignment model:* Potentially optimal but opaque, hard to debug when assignments seem wrong, and requires training data that does not exist for a new platform.

**Consequences:**
- Qualification gates are non-negotiable binary filters: annotators without required qualifications (e.g., `radiology_certified`) are completely excluded regardless of other factors.
- Active learning and error curriculum tasks are preferentially routed to top-quartile annotators (accuracy >= 0.93) via a 1.3x priority boost, ensuring high-value data gets the best annotators.
- Task reservation with configurable timeout (default 30 minutes) prevents abandoned tasks from blocking the pipeline. The `_expire_reservations` method re-queues stale assignments.
- The `QueueManager` complements the router with Redis-backed priority queues, deadline proximity boosts, auto-escalation for aging tasks (4h warning, 8h critical), and capacity forecasting for ops planning.

---

## ADR-006: Three-Window Drift Confirmation to Eliminate False Positive Alerts

**Status:** Accepted
**Date:** 2024-03
**Context:** Production data distributions shift over time (e.g., seasonal transaction patterns, new fraud vectors), potentially degrading model performance. Single-window drift alerting generated 12 alerts in the first month; 9 were transient artifacts (weekend traffic patterns, batch processing anomalies). The annotation team lost trust in drift alerts within a week.
**Decision:** Implement three-window confirmation in `DriftDetector` before generating drift alerts. Weekly distribution snapshots are compared against the training baseline using KL divergence (per-feature), Population Stability Index (prediction distribution), and cosine distance (embedding centroids). Drift must persist across 3 consecutive weekly windows before an alert is confirmed and a re-annotation request is auto-generated. Exception: PSI > 0.5 (dramatic shift) bypasses the confirmation requirement and triggers an immediate alert with 3x the standard re-annotation volume.
**Alternatives Considered:**
- *Single-window alerting:* Triggers on transient anomalies. 75% false positive rate in the first month destroyed team trust in the system.
- *Statistical hypothesis testing per window:* More rigorous per-window but does not solve the transient artifact problem. Weekend patterns can be statistically significant but operationally irrelevant.
- *Model performance degradation only (no distribution monitoring):* Detects drift only after model quality has already degraded in production. Distribution monitoring provides leading indicators before performance impact.

**Consequences:**
- Eliminated all 9 false positive alerts while detecting all 3 genuine distribution shifts, with only a 2-week detection delay (3 weekly windows).
- Automatic re-annotation requests are generated on confirmed drift, with volume proportional to severity (500 base items, 1000 for moderate PSI, 1500 for severe).
- The `DriftDetector` tracks per-feature KL divergence, enabling identification of which specific features have shifted (e.g., "online transaction percentage increased from 60% to 84%").
- Weekly snapshot frequency balances detection speed with compute cost. Daily snapshots would reduce detection delay but triple the compute budget.
- The severe drift bypass (PSI > 0.5) prevents the 3-week delay from missing catastrophic distribution changes.
