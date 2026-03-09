# Decision Log: AI Data Operations Platform

**Last Updated:** February 2025

This document captures key product and technical decisions, what alternatives were considered, and why we chose the path we did. Decisions are numbered chronologically.

---

## DEC-001: JSONB Annotation Schemas vs. Fixed Tables per Type

**Date:** January 2024
**Status:** Accepted
**Decider:** PM + Tech Lead

**Context:** The platform needs to support fundamentally different annotation types: text classification (single label), NER (character-level spans), bounding boxes (spatial coordinates), preference pairs (A/B comparison with reasoning), and more. Each type has a different output structure.

**Option A: Fixed tables per annotation type.** Create `text_classification_annotations`, `ner_annotations`, `bbox_annotations`, `preference_annotations` tables with typed columns specific to each format.

**Option B: JSONB-based configurable schemas.** Single `annotations` table with `annotation_data JSONB` column. Annotation schemas defined as JSONB documents in a schema registry. Validation at the application layer.

**Decision:** Option B (JSONB schemas).

**Rationale:**
- A healthcare client defines a new radiology annotation type (BI-RADS scoring with findings). With fixed tables, that is a database migration, code deployment, and QA cycle. With JSONB, the annotation lead creates a schema definition in the registry and it is live immediately.
- We counted 9 distinct annotation types in the first 6 months across 4 clients. Fixed tables would have required 9 migrations. JSONB schemas required zero.
- Cross-type queries ("show me all annotations for this task regardless of type") are trivial with a single table. With fixed tables, every dashboard query becomes a UNION across N tables.
- The tradeoff is weaker database-level validation. We compensate with schema validation in the API layer (FastAPI + Pydantic models generated from JSONB schema definitions) and golden set evaluation as a runtime quality check.

**Risk accepted:** JSONB queries are slower than typed column queries for aggregation. Mitigated by pre-computing quality metrics incrementally rather than querying raw JSONB at dashboard time.

---

## DEC-002: Temporal for Workflow Orchestration vs. Celery Task Chains vs. State Machine in Application

**Date:** January 2024
**Status:** Accepted
**Decider:** PM + Engineering Lead

**Context:** Annotation workflows are multi-stage (label, review, adjudicate), span hours to days, require human-in-the-loop signals (reviewer approves, expert adjudicates), and must survive system failures without losing annotator work.

**Option A: Celery task chains.** Chain annotation stages as Celery tasks with Redis broker. Use Celery Canvas for workflow composition.

**Option B: State machine in application code.** Track workflow state in PostgreSQL. Application logic transitions state based on events (annotation submitted, review completed).

**Option C: Temporal durable workflow engine.** Define workflows as Python code. Temporal handles durable execution, human-in-the-loop signals, retries, and workflow state persistence.

**Decision:** Option C (Temporal).

**Rationale:**
- The critical requirement is human-in-the-loop pausing. When annotations disagree and the task routes to a reviewer, the workflow must pause for hours or days waiting for the reviewer's decision. Celery tasks are designed for short-lived execution, not multi-day waits. You can hack it with periodic polling, but that is fragile and wasteful.
- Temporal signals handle this natively. The workflow calls `workflow.wait_for_signal("review_decision")` and pauses. When the reviewer submits their decision, the API sends a signal and the workflow resumes from exactly where it stopped. No polling, no state management code.
- Durability matters. If the system crashes mid-workflow, Celery loses the task state unless you build custom checkpointing. Temporal replays the workflow from the last completed step automatically. Zero annotation data loss.
- State machine in application (Option B) works for simple flows but becomes a maintenance burden as workflow complexity grows. We have 3 workflow variants (1-stage, 2-stage, 3-stage), conditional routing based on agreement scores, timeout-based reassignment, and flagging. That is 15+ state transitions. Temporal expresses this as readable Python code; a state machine expresses it as a transition table that nobody can reason about after 6 months.

**Tradeoff:** Temporal adds infrastructure complexity (3-node cluster, separate worker processes). Worth it for the workflow requirements.

---

## DEC-003: Multi-Metric Agreement Engine vs. Single Accuracy Score

**Date:** February 2024
**Status:** Accepted
**Decider:** PM

**Context:** The platform needs to measure annotation quality. The simplest approach is a single "accuracy" percentage. The question is whether that is sufficient.

**Option A: Single accuracy score.** Compute percentage of annotations that match the majority vote or golden set answer.

**Option B: Multi-metric engine.** Select agreement metric based on annotation type (kappa for classification, IoU for bounding boxes, span F1 for NER, etc.).

**Decision:** Option B (multi-metric engine).

**Rationale:**
- Raw accuracy is misleading for imbalanced classification. If 90% of transactions are legitimate and 10% are fraud, an annotator who labels everything "legitimate" achieves 90% accuracy. Cohen's kappa accounts for chance agreement and would correctly score this annotator near 0.
- Spatial annotations (bounding boxes, segmentation) cannot be evaluated with classification metrics at all. Two annotators might both correctly identify a tumor, but one draws a tight bounding box and the other draws a loose one. IoU (Intersection over Union) captures this spatial quality; accuracy would just say "both correct."
- NER span matching needs span-level F1. If one annotator marks "aspirin 81mg" as a medication and another marks just "aspirin," raw accuracy says they disagree. Span F1 with partial credit says they mostly agree. The distinction matters for training data quality.
- The implementation cost is moderate: ~400 lines of Python for all 7 agreement metrics (kappa, Fleiss, Krippendorff, IoU, Dice, span F1, BLEU). The schema registry maps each output type to the appropriate metric automatically. ML engineers never have to think about which metric applies.

**What this decision enabled:** Per-project quality thresholds tuned to the annotation type. Healthcare radiology projects require IoU > 0.80 for bounding boxes. RLHF preference projects require kappa > 0.70 (lower threshold because human preference is inherently more subjective). Content moderation requires kappa > 0.75. These thresholds would be meaningless with a single accuracy score.

---

## DEC-004: Weighted Vote as Default Consensus vs. Simple Majority

**Date:** February 2024
**Status:** Accepted
**Decider:** PM + ML Lead

**Context:** When 3 annotators label the same item and disagree, the platform needs a method to resolve the disagreement and produce a single "correct" label.

**Option A: Simple majority vote.** 2-of-3 agree, that label wins. Ties route to expert.

**Option B: Weighted vote.** Each annotator's vote weighted by their rolling accuracy score. Annotator with 97% accuracy contributes more than annotator with 85% accuracy.

**Option C: Always defer to highest-rated annotator.** Ignore lower-accuracy annotators' labels entirely.

**Decision:** Option B (weighted vote) as default, with Option A available per project.

**Rationale:**
- We ran a backtest on 2,000 annotations where we had expert ground truth. Weighted vote agreed with expert 91% of the time. Simple majority agreed 86% of the time. The 5% difference is meaningful at scale: on 100K annotations, that is 5,000 fewer incorrect consensus labels.
- The difference comes from cases where two lower-accuracy annotators agree on the wrong answer and one high-accuracy annotator has the right answer. Simple majority picks the wrong answer. Weighted vote often picks the right answer because the high-accuracy annotator's vote carries more weight.
- Option C (always defer to highest-rated) wastes the information from other annotators. If two annotators with 90% accuracy agree and one with 95% accuracy disagrees, the 90% pair might be right. Weighted vote handles this gracefully; pure deference does not.
- Simple majority is still available for projects where annotator accuracy scores are not yet established (new project, new annotator pool) or where the client prefers simplicity.

---

## DEC-005: 70/30 Active Learning / Random Split vs. Pure Active Learning

**Date:** March 2024
**Status:** Accepted
**Decider:** PM + ML Lead

**Context:** Active learning selects the most informative unlabeled examples for annotation (where the model is most uncertain). The question is whether to use pure active learning or mix in random samples.

**Option A: Pure active learning (100% uncertainty sampling).** Maximize information gain per label by only annotating what the model is confused about.

**Option B: Mixed sampling (70% active learning, 30% random).** Mostly uncertainty sampling with a random component for distribution coverage.

**Decision:** Option B (70/30 split).

**Rationale:**
- Pure uncertainty sampling has a known failure mode called "sampling bias collapse." The model becomes very accurate on the decision boundary (where it was uncertain) but remains blind to distribution shifts in regions where it was confident. If production data shifts into a region the model thought it understood, there are no labels to correct the error.
- We observed this in a controlled experiment. Pure active learning outperformed 70/30 by Week 2 (+0.04 F1 vs. +0.03 F1). But by Week 8, after a production data shift, the 70/30 model maintained F1 while the pure active learning model dropped 0.02 F1 because it had no labels in the shifted region.
- The 30% random component costs ~$1,800/year in "suboptimal" label allocation (labels on examples the model already handles well). This is insurance against distribution shift. Cheap insurance given the retraining cost of a model that silently degrades.
- The 70/30 ratio is configurable per project. Stable domains (medical imaging, where the distribution of X-rays changes slowly) could safely use 80/20 or 90/10. Fast-moving domains (content moderation, where new policy violations emerge frequently) should use 60/40 or even 50/50.

---

## DEC-006: Golden Set Rotation vs. Static Gold Pool

**Date:** March 2024
**Status:** Accepted
**Decider:** PM + Annotation Ops Lead

**Context:** Golden items (pre-labeled examples with known correct answers) are inserted into the annotation queue to measure annotator accuracy. The question is whether the golden pool should be static or rotated over time.

**Option A: Static gold pool.** Create golden items once. Use them indefinitely.

**Option B: Monthly rotation with 30% replacement.** Each month, retire 30% of the golden pool and replace with fresh expert-labeled items.

**Decision:** Option B (monthly rotation).

**Rationale:**
- Annotators who process 50+ golden items per week will eventually recognize them. One client reported an annotator whose golden accuracy was 99% but peer agreement was only 78%. Investigation revealed memorization: the annotator recognized golden items by their content and answered from memory.
- 30% monthly replacement means the entire pool turns over in ~3.5 months. An annotator who works continuously will encounter mostly fresh golden items, making memorization impractical.
- The cost is expert time to create new golden items. At 30% replacement of a 200-item pool, that is 60 new items per month. With expert annotation taking ~2 minutes per item, this costs 2 hours of expert time per month per project. Acceptable.
- Statistical detection supplements rotation. The system flags annotators where golden accuracy exceeds peer agreement by > 15 percentage points. This catches gaming even before the pool rotates.

---

## DEC-007: Pre-labeling Anchoring Mitigation vs. No Pre-labeling

**Date:** April 2024
**Status:** Accepted
**Decider:** PM + ML Lead + Annotation Ops Lead

**Context:** Model-assisted pre-labeling shows model predictions to annotators as suggested annotations, which they can accept or correct. This increases throughput 40-60%. But there is a risk: annotators may rubber-stamp model predictions instead of evaluating independently (anchoring bias).

**Option A: No pre-labeling.** Annotators label from scratch every time.

**Option B: Pre-labeling with anchoring mitigation.** Enable pre-labeling but monitor correction rate and intervene when it drops too low.

**Option C: Pre-labeling on alternate items.** Show pre-labels on 50% of items, blank on 50%. Use the blank items as an anchoring calibration.

**Decision:** Option B (pre-labeling with monitoring).

**Rationale:**
- The throughput benefit is too large to forgo. 40-60% more annotations per hour translates to $0.05-0.08 saved per label. On 150K annual labels, that is $7,500-12,000/year.
- Anchoring is a real risk but measurable. The correction rate is the percentage of pre-labeled items where the annotator changes something from the model's suggestion. A healthy correction rate on a model with 85% accuracy should be ~15-20% (the annotator corrects the 15% of cases the model gets wrong, plus some borderline cases).
- If correction rate drops below 10% on a batch where the model is known to have errors (golden items with incorrect pre-labels), the system flags the annotator. Repeated low correction rates trigger a warning and temporary pre-labeling suspension for that annotator.
- Option C (alternating) was considered but adds complexity. The monitoring approach in Option B catches the same problem with simpler implementation.

**Monitoring thresholds:**
- Correction rate < 10% with known errors in batch: disable pre-labeling for annotator, quality review of recent work
- Correction rate < 5% sustained (2+ weeks): flag to annotation lead for intervention
- Golden items with incorrect pre-labels where annotator accepted the wrong pre-label: count toward consecutive failure tracking

---

## DEC-012: Pivot From Custom Experimentation Framework to PostHog Feature Flags

**Date:** September 2024
**Status:** Accepted (supersedes earlier approach)
**Decider:** PM + Engineering Lead

**Context:**

V1 of the platform included a custom A/B testing framework for measuring annotator quality. The system could run experiments to test whether a new UI change (e.g., golden item highlighting) improved annotator accuracy. The framework was built in-house over 6 weeks and included: experiment assignment, metric collection, statistical analysis, and reporting dashboards.

For three months, the team used the custom framework to test hypotheses: "Does UI highlighting improve accuracy?" (yes, +3%), "Does annotator training reduce error rate?" (yes, +4%). The experiments generated insights but consumed significant engineering effort to maintain.

**What Happened:**

By month 4, the team discovered that PostHog (already integrated for product analytics) had a powerful feature flag and A/B testing system that was nearly identical to what we'd built. More importantly, PostHog's system was:
- Deployed and maintained by PostHog (not us)
- Already integrated with our event tracking
- Capable of all the statistical analyses we'd built
- Battle-tested across 1,000+ companies

The realization: we spent 6 weeks rebuilding PostHog's product.

**Decision:**

Migrated all experiment infrastructure to PostHog. Disabled custom framework. Consolidated all A/B testing under PostHog feature flags.

**Rationale:**

1. **Maintenance burden eliminated:** PostHog handles updates, bug fixes, and scalability. Our custom framework required ongoing fixes (edge cases in statistical calculation, UI bugs in reporting dashboard).

2. **Feature completeness:** PostHog's A/B testing includes advanced features we hadn't implemented: multivariate testing, sequential testing, correlation analysis with other events. We immediately started using these.

3. **Integration leverage:** PostHog was already tracking annotator events (session start, annotation submitted, correction made). Feature flags within PostHog can automatically analyze impact on these events without additional ETL.

4. **6 weeks of engineering freed:** The team that built the custom framework could focus on the novel part of the platform — the multi-metric agreement engine (the actual product value).

**Consequences:**

- **Short-term:** Migrating 12 active experiments from custom framework to PostHog took 2 days. Dashboard retraining took 1 day.
- **Long-term:** Saved 6 weeks of maintenance per year (estimated). PostHog's simpler mental model (flags = assignment, variants = treatment groups) reduced cognitive overhead.
- **Cost:** PostHog charge scales with event volume; at 500K events/month cost is ~$200/month. Offset by engineering time savings.

**Lesson:**

Before building platform infrastructure, check if an existing product already solved the problem 95% of the way there. Especially true for cross-cutting concerns like experimentation that aren't core to the product.

---

## DEC-008: Per-Domain Qualification Gates vs. Universal Onboarding

**Date:** April 2024
**Status:** Accepted
**Decider:** PM + Annotation Ops Lead

**Context:** Annotators working on healthcare radiology tasks need fundamentally different skills than annotators working on RLHF preference pairs or content moderation. The question is whether to have a single onboarding process or domain-specific qualification.

**Option A: Universal onboarding.** All annotators go through the same training. Route based on availability, not qualification.

**Option B: Per-domain qualification gates.** Each domain has a specific qualification test. Annotators can only receive tasks in domains where they have passed qualification.

**Decision:** Option B (per-domain qualification).

**Rationale:**
- A radiology annotation routed to an unqualified annotator produces a bad label 40-50% of the time. That bad label enters the review queue, wastes reviewer time, and if it passes review (reviewers make mistakes too), it enters the training pipeline. The cost of one bad radiology label (expert re-annotation + potential model damage) far exceeds the cost of a qualification gate.
- Data from first 3 months: before qualification gates, radiology error rate was 18%. After gates, it dropped to 4.1%. The qualification test filters out annotators who would struggle, and the filtered annotators are redirected to domains where they can contribute productively.
- Qualification tests use golden set items from the domain. Radiology: 50-item test, pass at 95% (high bar, reflects safety-critical nature). RLHF preference: 30-item test, pass at 80% (lower bar, preference is more subjective). Content moderation: 100-item test, pass at 85% (high volume of policy edge cases).
- The cost is expert time to create domain-specific qualification tests. One-time investment of 4-8 hours per domain. Re-usable across all annotators.

---

## DEC-009: Configurable Workflow Stages (1-3) vs. Fixed Three-Stage Pipeline

**Date:** May 2024
**Status:** Accepted
**Decider:** PM

**Context:** Some annotation types need heavy quality assurance (RLHF safety: 3 stages with expert adjudication). Others need speed (product categorization: high volume, moderate quality bar). Should the platform enforce a fixed pipeline or allow configuration?

**Option A: Fixed three-stage pipeline for all projects.** Every annotation goes through label, review, adjudicate.

**Option B: Configurable stages (1, 2, or 3) per project.** Project owner selects the appropriate pipeline depth.

**Decision:** Option B (configurable).

**Rationale:**
- Forcing three stages on a product categorization project where we need 50,000 labels at kappa > 0.70 would triple the annotation cost with minimal quality benefit. Product categorization with single-stage + 10% spot-check review achieves kappa 0.74 at 1/3 the cost of full three-stage review.
- Conversely, RLHF safety annotations with single-stage labeling missed 8% of harmful content that would have been caught by review. The three-stage pipeline catches 99.2% of safety-relevant labels before they enter training data.
- The configuration lives in `projects.workflow_config` as JSONB. Changing the stage count is a project setting update, not a code change. The Temporal workflow reads the config and dynamically constructs the pipeline.

**Default configuration by industry:**

| Industry | Default Stages | Review Rate | Rationale |
|---|---|---|---|
| AI Safety (RLHF) | 3 | 100% of disagreements | Safety-critical, cannot afford false negatives |
| Healthcare | 3 | 100% of disagreements | Patient safety, regulatory requirements |
| Autonomous Vehicles | 3 | 100% for safety-critical objects | ISO 26262 traceability |
| Financial Services | 2 | 100% of fraud-positive labels | False positives cause customer friction |
| Content Moderation | 2 | 100% for policy violations | Balance speed and accuracy |
| E-commerce Categorization | 1 | 10% spot-check | Volume-oriented, moderate quality bar |

---

## DEC-010: Drift Detection with 3-Window Confirmation vs. Single-Window Alerting

**Date:** June 2024
**Status:** Accepted
**Decider:** PM + ML Lead

**Context:** Drift detection compares production data distributions against training data. The question is when to trigger a re-annotation request: immediately on any detected drift, or after confirming sustained drift over multiple windows.

**Option A: Single-window alert.** Any window where PSI > 0.2 triggers re-annotation.

**Option B: Three-window confirmation.** Require 3 consecutive windows with drift before alerting.

**Decision:** Option B (3-window confirmation).

**Rationale:**
- Single-window alerting generated 12 alerts in the first month. 9 were transient (weekend traffic patterns, batch processing artifacts, one-time data pipeline issues). Only 3 reflected genuine distribution shifts. The annotation team lost trust in drift alerts after the first week and started ignoring them.
- Three-window confirmation eliminated all 9 false positives. The 3 genuine shifts were detected with a 2-week delay (3 weekly windows), which is acceptable because distribution drift is a slow-moving problem. If production data shifted dramatically overnight, the model would fail on other metrics (accuracy monitoring, error rate alerts) before drift detection caught it.
- Exception for dramatic shifts: single-window PSI > 0.5 bypasses confirmation and triggers immediate alert. This threshold has never fired in production, which confirms it is appropriately set for true anomalies.

---

## DEC-011: Content Moderation Wellness Policies Built into Platform vs. External HR Process

**Date:** July 2024
**Status:** Accepted
**Decider:** PM + Annotation Ops Lead + HR

**Context:** Annotators working on content moderation review harmful, violent, and disturbing content. Industry research shows this leads to psychological harm without proper safeguards. Should the platform enforce wellness policies technically, or leave it to HR/management process?

**Option A: External HR process.** Managers track annotator wellness manually. Breaks and rotation managed through scheduling.

**Option B: Platform-enforced wellness policies.** The system enforces mandatory breaks, content rotation limits, and exposure tracking automatically.

**Decision:** Option B (platform-enforced).

**Rationale:**
- Relying on managers to track breaks across 50+ annotators working different shifts is unreliable. During a high-volume content review sprint, a manager admitted that 3 annotators worked 6+ hours on harmful content without breaks because "we needed to clear the queue."
- The platform enforces: mandatory 15-minute break every 2 hours for sensitive content projects. Maximum 2 continuous hours on harmful content categories before automatic rotation to non-sensitive tasks. Session-level tracking of sensitive content exposure minutes. Alert to annotation lead if cumulative weekly exposure exceeds threshold.
- This is not just ethical; it is a quality concern. Annotator accuracy on sensitive content degrades measurably after 2+ hours of continuous exposure. Enforcing breaks maintains both annotator well-being and annotation quality.
