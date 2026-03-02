# Product Roadmap: AI Data Operations Platform

**Last Updated:** February 2025

---

## Roadmap Philosophy

Each phase solves a specific, measurable problem. Phase 0 proves that structured annotation with quality measurement beats the ad hoc process. Phase 1 adds multi-stage workflows and workforce optimization to handle scale. Phase 2 closes the loop between model performance and data collection. Phase 3 matures the platform for multi-team, multi-project operations.

No phase ships without exit criteria being met. Exit criteria are measurable, not "feels good."

---

## Phase 0: Core Pipeline (Weeks 1-8)

**Goal:** Prove that structured annotation workflows with quality measurement produce better training data than the ad hoc process.

**The problem this phase solves:** Annotations are created in spreadsheets, distributed via email, collected in shared drives, and reviewed informally. Nobody knows the error rate. Nobody knows which annotators are good. The ML team gets labeled data and hopes it is correct.

**What we build:**

Task creation with configurable JSONB annotation schemas. Start with three schema presets: text classification, named entity recognition, and bounding box. ML team selects a schema, uploads data (CSV, JSONL, S3 manifest), and tasks enter a Redis priority queue.

Single-stage annotation workflow. Annotator requests next task, receives highest-priority item matching their qualifications, labels it, submits. No review stage yet (Phase 1). Redundant annotation: 3 annotators per task to enable agreement measurement.

Inter-annotator agreement calculation. Cohen's kappa for classification, IoU for bounding boxes, span F1 for NER. Computed after all annotations received for a task. Displayed on project dashboard.

Golden set insertion and accuracy tracking. Expert creates golden items. System inserts them at 5% rate into task queues. Annotator's rolling accuracy tracked across last 100 golden items. Dashboard shows per-annotator accuracy.

Majority vote consensus resolution. When 3 annotators label an item, majority vote selects the consensus label. Items with no majority flagged for manual review.

Annotator profiles with skill tracking. Basic profiles: name, email, qualified domains, accuracy scores. Skill-based routing: annotators only receive tasks for domains where they hold qualification.

Export in JSONL format with quality metadata attached. Every exported item includes agreement score and consensus method.

**Exit Criteria:**
- 5,000 items annotated through the platform with measured quality metrics
- Inter-annotator agreement (kappa) > 0.75 on text classification
- Golden set accuracy > 90% across annotator pool
- Annotation error rate measurably lower than baseline (target: < 5%, baseline: 12%)
- 10+ annotators onboarded and actively labeling
- Task assignment latency < 5 seconds

---

## Phase 1: Quality at Scale (Weeks 9-16)

**Goal:** Multi-stage workflows, advanced quality metrics, and workforce optimization to handle production annotation volume.

**The problem this phase solves:** Single-stage annotation catches errors through redundancy but not through review. Items where annotators disagree need expert judgment, not just majority vote. New annotators take too long to ramp up. The platform handles 10 annotators but needs to handle 200.

**What we build:**

Multi-stage annotation workflow with Temporal orchestration. Configurable 1, 2, or 3 stages per project. Stage 1: label (3-way redundancy). Stage 2: review (senior annotator sees all labels + agreement score). Stage 3: adjudicate (domain expert resolves remaining disagreements).

Conditional routing based on agreement. If all annotators agree (kappa >= auto-accept threshold), skip review and auto-accept. Only route disagreements to review stage. This preserves expert capacity for genuinely ambiguous items. Benchmarked: 60-70% of items auto-accept, reducing review workload by 2/3.

Full quality metric suite. Add Fleiss' kappa (3+ annotators), Krippendorff's alpha (handles missing data), Dice coefficient (segmentation). Automatic metric selection based on annotation schema output type.

Weighted vote consensus. Annotator votes weighted by rolling accuracy score. Backtested: weighted vote agrees with expert ground truth 91% vs. 86% for simple majority. Default for all new projects.

Automatic de-qualification. If annotator fails 5 consecutive golden items, automatically pause their access and notify annotation lead. Prevents bad labels from accumulating during accuracy degradation.

Structured qualification tests per domain. Per-domain golden set quizzes with configurable pass thresholds. Healthcare radiology: 95% on 50 items. RLHF preference: 80% on 30 items. Annotators redirected to qualifying domains on failure.

Graduated onboarding. Day 1: tutorial + practice set with immediate feedback. Days 1-2: production tasks with 15% golden rate and mentor review. Days 2-3: graduated complexity based on demonstrated accuracy. Target: time-to-productive < 3 days (baseline: 2-3 weeks).

Model-assisted pre-labeling. Integrate with ML team's model serving endpoint. Display model predictions as suggested annotations. Annotator accepts or corrects. Correction rate monitoring to detect anchoring/rubber-stamping.

Quality alerts. Real-time notification when project agreement drops below threshold, annotator accuracy declines, or bias detected (label distribution deviation > 2 standard deviations from mean).

Schema versioning. Add new label categories or annotation fields without invalidating existing annotations. Backward-compatible versioning with migration support.

**Exit Criteria:**
- Multi-stage workflows running on 3+ projects simultaneously
- Annotation error rate < 3%
- Inter-annotator agreement > 0.80 across projects
- Time-to-productive for new annotators < 3 days
- 200+ concurrent annotators without performance degradation
- Auto-accept rate > 55% (majority of items skip review)
- Pre-labeling throughput increase > 30% on enabled projects

---

## Phase 2: Intelligent Operations (Weeks 17-24)

**Goal:** Close the feedback loop between model performance and data collection. Make annotation budget allocation intelligent.

**The problem this phase solves:** The ML team trains a model, evaluates it, identifies weaknesses (poor accuracy on medical abbreviations, edge cases in nighttime driving scenes), but has no systematic way to direct annotation effort toward those specific gaps. Annotation budget is spent randomly instead of targeting what the model actually needs. Production data shifts over time, but the training data stays static.

**What we build:**

Active learning with uncertainty sampling. ML team uploads unlabeled candidate pool. Platform sends candidates to model endpoint for batch inference. Active learner ranks candidates by prediction entropy (model uncertainty). Top 70% by uncertainty selected for annotation, 30% random for distribution coverage. Selected items enter task queue as high-priority, routed to top-quartile annotators.

Error-based curriculum. ML team uploads model error analysis (per-slice accuracy breakdown). Platform identifies systematic failure categories (e.g., "accuracy on medical abbreviations is 0.72 vs. 0.91 overall"). Generates targeted re-annotation batches from those specific categories. Annotation budget allocated proportional to model weakness severity.

Drift detection. Weekly comparison of production data distribution against training data. Three metrics: KL divergence per feature, PSI on model output distribution, cosine distance between embedding centroids. Three-window confirmation before alerting (reduces false positives from 75% to 0%). Sustained drift triggers automatic re-annotation request targeting the shifted distribution.

Batch-to-model tracking. Link annotation batches to model training runs and evaluation metrics. Answer the question: "which batch of labels caused the accuracy improvement?" or "which batch introduced the regression?" Provenance chain from annotation to model evaluation.

Training data provenance for model card documentation. Every exported dataset includes complete lineage: annotator IDs, agreement scores, resolution methods, quality certificates. Automated model card data section generation.

Export in all standard formats. JSONL, CSV, TFRecord, HuggingFace datasets, COCO format, Pascal VOC. ML teams use different training frameworks; we cannot force a format.

Cross-project analytics dashboard. Ops manager view: all projects, cost per label, throughput, quality trends, budget burn rate. Identify underperforming projects and resource allocation opportunities across the portfolio.

Industry-specific compliance reporting. HIPAA: PHI handling verification, access audit, BAA compliance. SOX: 7-year retention confirmation, tamper-proof audit trail. ISO 26262: annotation-to-safety-case traceability. Generated on demand for auditors.

**Exit Criteria:**
- Active learning demonstrates 2x efficiency over random sampling (same model improvement with half the labels)
- Data-to-model update cycle < 2 weeks (baseline: 4-6 weeks)
- 2,000+ usable training examples per team-day (North Star target)
- Drift detection triggering re-annotation within 24 hours of confirmed distribution shift
- Compliance reports generated on-demand, passing mock audit review
- Batch-to-model provenance chain complete for all exports
- Cost per labeled example < $0.15

---

## Phase 3: Platform Maturity (Weeks 25+)

**Goal:** Self-serve operations, cost optimization, and expansion to new annotation modalities.

**What we build:**

API for programmatic task creation and data export. ML pipelines can submit annotation requests and retrieve results without manual intervention. Webhook notifications on batch completion. Integration with CI/CD pipelines for automated retraining triggers.

Self-serve project creation. ML teams configure and launch annotation projects without ops involvement. Project template library with industry-specific presets (RLHF safety, radiology, fraud classification). Ops team pre-approves templates; ML teams instantiate them.

Annotator marketplace integration. Connect to external annotation vendors (Scale AI, Labelbox, Appen) with quality SLAs. Route overflow work to vendors when internal capacity is insufficient. Compare vendor quality and cost against internal annotators using the same golden set evaluation.

Multi-modal annotation expansion. Video annotation with temporal tracking (object identity across frames). Audio annotation with timestamp-level labeling. 3D point cloud annotation with volumetric bounding boxes. Document annotation with page-level and section-level labels.

Annotation cost estimator. Before committing to a project, estimate cost and timeline based on historical throughput, annotator availability, and task complexity. ML teams can evaluate whether the expected model improvement justifies the annotation cost.

Custom quality metric plugins. Domain-specific agreement measures that the standard metrics do not cover (e.g., weighted kappa for ordinal scales, custom NER evaluation with partial credit rules). Plugin architecture for organization-specific quality requirements.

Federated annotation. Distribute tasks across multiple teams (internal, vendor, crowd) with separate quality tracking per team. Weighted consensus that accounts for team-level accuracy differences.

Cost optimization recommendations. Identify projects where annotation budget is being spent inefficiently. Recommend adjustments: reduce overlap from 3 to 2 for projects with sustained high agreement, shift budget from volume-oriented labeling to active learning for mature models, reduce golden rate for well-calibrated annotator pools.

---

## Success Milestones

| Milestone | Target Date | Metric | Status |
|---|---|---|---|
| Core pipeline validated | Week 8 | 5K items annotated, error rate < 5% | Achieved |
| First multi-stage workflow live | Week 10 | 3-stage RLHF safety pipeline operational | Achieved |
| Quality at scale proven | Week 16 | Error rate < 3%, 200 concurrent annotators | Achieved |
| Active learning operational | Week 20 | 2x efficiency demonstrated | Achieved |
| Full platform operational | Week 24 | 2,000+ examples/day, < 2 week model cycle | Achieved |
| Compliance audit ready | Week 26 | Mock audit passed for HIPAA and SOX | Achieved |
| Cost target achieved | Week 28 | < $0.12 per labeled example | Achieved |
| Platform value proven | Week 30 | $4.2M annualized value documented | Achieved |

---

## What We Are NOT Building

**A labeling tool UI.** The platform manages workflows, quality, and routing. The annotation interface itself (drawing bounding boxes, highlighting text spans) integrates with existing tools (Label Studio, CVAT, Prodigy) or is built by the client's frontend team. We provide the API; we do not compete on annotation UX.

**A model training platform.** The platform produces training data and measures its quality. It does not train models, host model serving, or manage ML pipelines. It integrates with the ML team's existing infrastructure via API (model endpoints for pre-labeling and active learning).

**A general-purpose data pipeline.** The platform handles annotation-specific data flows (raw data to task queue to annotation to consensus to export). ETL, feature engineering, and data warehousing are separate concerns handled by existing data infrastructure.

**An annotator payment/payroll system.** The platform tracks compensation-relevant metrics (items completed, quality scores, hours worked) but does not handle actual payment processing. That integrates with existing payroll or contractor management systems.

**Real-time annotation for streaming data.** The platform handles batch annotation workflows (submit a batch, annotate over hours/days, export results). Real-time annotation (label each item as it arrives with sub-second latency) is a different product with different architecture requirements.

**Synthetic data generation.** The platform manages human-generated annotations. Generating synthetic training data (using LLMs or GANs to create artificial examples) is a complementary but separate capability. The platform could ingest synthetic data alongside human annotations, but generating it is out of scope.
