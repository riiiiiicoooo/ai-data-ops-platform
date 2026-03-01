# Product Requirements Document: AI Data Operations Platform

**Author:** Jacob George, Principal Product Manager
**Last Updated:** February 2025
**Status:** Delivered (multi-client)

---

## 1. Problem Statement

Machine learning teams across healthcare, autonomous vehicles, financial services, AI research, and e-commerce share a common operational bottleneck: training data quality. Models degrade not because of architecture choices but because the data they learn from is inconsistently labeled, incompletely reviewed, and disconnected from the model's actual failure modes.

### 1.1 Current State (Without Platform)

**Quality is unmeasured and inconsistent.**
Annotation teams produce labels with no systematic quality tracking. Inter-annotator agreement is unknown. When two annotators disagree on the same example, the disagreement is either invisible (only one annotator sees each item) or resolved informally ("ask the senior person"). Error rates average 12% across annotation projects, but nobody knows the error rate until the model trained on that data underperforms.

Concrete impact: A healthcare AI company trained a tumor detection model on 15,000 radiology annotations. Post-deployment analysis revealed 8% of bounding boxes were incorrectly placed, concentrated in a specific annotator's work over a 3-week period. The model learned those errors as ground truth. Retraining cost $180K and delayed the product launch by 6 weeks.

**Annotation workflows are manual and fragile.**
Project managers create tasks in spreadsheets, assign them via email or Slack, collect completed annotations in shared drives, and manually track progress. There is no queue system, no routing logic, and no automatic handoff between annotation stages. When an annotator goes on vacation mid-task, their work sits in limbo until someone notices.

Concrete impact: An autonomous vehicle company needed to label 200,000 LiDAR frames for a model update. The manual coordination process took 3 weeks just for task distribution and assignment. Actual annotation took 4 weeks. Total pipeline time: 7 weeks for work that should have taken 4.

**No feedback loop between model performance and data collection.**
ML engineers identify model weaknesses (poor performance on nighttime driving scenes, medical abbreviations, financial jargon) but have no systematic way to feed those insights back into the annotation pipeline. The next batch of training data is selected randomly instead of targeting the specific gaps the model needs filled.

Concrete impact: A financial services firm spent $400K labeling 100K transactions for fraud detection. Post-training analysis showed the model already performed well on 70% of those transaction types. The labeling budget would have been 3x more impactful if directed at the transaction categories where the model was weakest.

**Workforce is untracked and unoptimized.**
Annotator quality varies by 5-10x across individuals, but without per-annotator accuracy tracking, task routing treats everyone equally. New annotators receive complex tasks on day one. Expert annotators waste time on trivial items. Qualification is informal ("shadow someone for a week") rather than structured.

Concrete impact: Annotation teams show a bimodal accuracy distribution. Top quartile annotators achieve 97%+ accuracy. Bottom quartile is below 85%. Without routing, every task has a 25% chance of landing with a low-accuracy annotator.

### 1.2 Success Metrics

| Metric | Current | Target | Timeline |
|---|---|---|---|
| Annotation error rate | 12% | < 3% | Phase 1 (Week 8) |
| Inter-annotator agreement (Cohen's kappa) | 0.62 (unmeasured for most projects) | > 0.80 | Phase 1 (Week 8) |
| Pipeline cycle time (task creation to usable data) | 5+ days | < 2 days | Phase 1 (Week 8) |
| Golden set accuracy (annotator calibration) | Untracked | > 95% | Phase 1 (Week 8) |
| Active learning efficiency vs. random sampling | N/A (random only) | 2x improvement | Phase 2 (Week 16) |
| Data-to-model-update cycle | 4-6 weeks | < 2 weeks | Phase 2 (Week 16) |
| Annotator time-to-productive | 2-3 weeks | < 3 days | Phase 1 (Week 8) |
| Usable training examples per team-day | 200 | 2,000+ | Phase 2 (Week 16) |

---

## 2. User Personas

### 2.1 ML Engineer (Priya)

**Role:** Trains and evaluates models. Primary consumer of annotated data.

**Current pain:** Receives batches of labeled data with no quality metadata. Discovers labeling errors only after training a model and seeing degraded metrics. Spends 30% of her time cleaning data that should have been labeled correctly the first time. Cannot request targeted re-annotation of specific failure categories without manually assembling a spreadsheet of examples and emailing the annotation lead.

**Needs from platform:**
- Submit annotation requests with schema definition and quality requirements
- Track annotation progress in real-time (not "I'll check with the annotation team")
- Export labeled data in model-ready format (JSONL, TFRecord, HuggingFace datasets)
- Trigger targeted re-annotation based on model error analysis
- View quality metrics (agreement, accuracy) per batch before using data for training

### 2.2 Annotation Lead (David)

**Role:** Manages annotation team. Responsible for quality and throughput.

**Current pain:** Manually assigns tasks, tracks progress in spreadsheets, and resolves disagreements by asking annotators to discuss. Has no visibility into per-annotator accuracy. Onboarding new annotators takes weeks because there's no structured qualification process. When quality drops, he doesn't know until the ML team complains.

**Needs from platform:**
- Dashboard showing task queues, annotator utilization, and quality metrics
- Automatic task routing based on annotator skill and qualification
- Real-time quality alerts (agreement drops, annotator accuracy decline)
- Structured onboarding: qualification tests, golden set calibration, graduated complexity
- Workforce analytics: throughput per annotator, accuracy trends, burnout indicators

### 2.3 Annotator (Maria)

**Role:** Labels data items according to annotation guidelines.

**Current pain:** Receives tasks via email with inconsistent instructions. Doesn't know if her annotations are correct because she never gets feedback. Bored by trivial tasks that don't match her expertise. Gets stuck on ambiguous examples with no way to flag them for expert review.

**Needs from platform:**
- Clear task interface with annotation guidelines, examples, and edge case references
- Immediate feedback on golden set items (did I get this right?)
- Ability to flag ambiguous items for expert review instead of guessing
- Task difficulty matched to skill level (challenging enough to be engaging, not so hard she's guessing)
- Transparent quality score so she knows where she stands

### 2.4 Data Operations Manager (Kevin)

**Role:** Oversees annotation programs across multiple projects. Reports to VP of ML.

**Current pain:** No visibility into annotation program health across projects. Cannot answer basic questions: How much are we spending per labeled example? Which projects are behind schedule? What's our quality trend over the last quarter? Compliance requirements (HIPAA for healthcare data, SOX for financial data) are tracked manually.

**Needs from platform:**
- Cross-project dashboard: cost, throughput, quality, timeline per project
- Budget tracking: cost per labeled example, projected spend, budget alerts
- Compliance reporting: audit trail, data access logs, PHI handling verification
- Vendor management: if using external annotation services, compare quality and cost

---

## 3. Industry-Specific Configuration

The platform engine is domain-agnostic. Industry requirements are met through configuration:

### 3.1 AI/ML Research (RLHF, Safety, Instruction Tuning)

**Annotation types:** Preference pairs (A is better than B), safety ratings (safe/unsafe with category), instruction quality scoring (1-5 with criteria), multi-turn dialogue evaluation, red-team prompt generation.

**Quality requirements:** Cohen's kappa > 0.75 for preference pairs. Safety annotations require 3-way agreement with expert adjudication on disagreement. All safety labels are 100% reviewed (no spot-check sampling).

**Workforce:** Domain experts for safety evaluation (background in content policy, ethics, or relevant domain). Crowd workforce for preference pairs with quality qualification gate. Red-team specialists for adversarial prompt generation.

**Compliance:** Model card documentation linking training data provenance to model behavior. Bias auditing on annotation distributions (demographic, topic, sentiment). Data retention policies for personally-generated content.

### 3.2 Healthcare (Radiology, Clinical NLP, Pathology)

**Annotation types:** Bounding box (tumor localization), polygon segmentation (organ delineation), named entity recognition (medications, diagnoses, procedures), classification (pathology slide grading), temporal relation extraction (symptom onset to diagnosis timeline).

**Quality requirements:** Krippendorff's alpha > 0.85 for diagnostic annotations. IoU > 0.80 for bounding boxes. 100% dual-review for annotations that will inform clinical decision support. Golden set accuracy > 97% for annotators working on diagnostic data.

**Workforce:** Board-certified radiologists for radiology annotation. Licensed clinicians (RN, MD, PA) for clinical NER. Pathology-trained specialists for slide classification. All annotators must complete HIPAA training and pass domain-specific qualification exam.

**Compliance:** HIPAA: PHI must be de-identified before annotation. Access controls with role-based permissions. Audit trail for every annotation action. Data residency requirements (annotation data stays in approved regions). BAA with any external annotation vendors.

### 3.3 Autonomous Vehicles (Perception, Planning, Prediction)

**Annotation types:** 3D bounding box (vehicles, pedestrians, cyclists), LiDAR point cloud segmentation, lane marking annotation, traffic sign classification, scene-level attributes (weather, time of day, road type), temporal tracking (object identity across frames).

**Quality requirements:** IoU > 0.80 for 3D bounding boxes. 100% review for safety-critical object classes (pedestrians, cyclists). Frame-to-frame tracking consistency validation. Edge case annotations (partially occluded, unusual objects) get mandatory expert review.

**Workforce:** Certified annotators with 40+ hours of domain training. Separate certification for each annotation type (bounding box, segmentation, tracking). Monthly re-certification with updated golden sets reflecting new edge cases.

**Compliance:** ISO 26262 traceability: every annotation linked to the sensor data, annotator, reviewer, and quality metrics. Safety case documentation: annotation quality evidence for regulatory submissions. Version control on annotation guidelines with change history.

### 3.4 Financial Services (Fraud, Document Processing, Sentiment)

**Annotation types:** Transaction classification (fraud categories, merchant codes), document entity extraction (KYC fields, financial statement line items), sentiment classification (earnings call transcripts, news articles), intent classification (customer service interactions).

**Quality requirements:** Inter-annotator agreement > 0.80. Golden set accuracy > 95%. Fraud label audit: every fraud-positive label reviewed by Tier 2 before entering training data (false positives in fraud training data cause customer friction).

**Workforce:** Compliance-trained annotators with background checks. Domain expertise in financial instruments for complex transaction classification. Language-specific annotators for multi-market sentiment analysis.

**Compliance:** SOX audit trail for annotation decisions on financial data. PII handling: names, account numbers, SSNs masked before annotation. Data residency: annotation data stays in approved jurisdictions. Retention policies: annotation data retained for 7 years (regulatory requirement).

### 3.5 E-commerce and Content Platforms

**Annotation types:** Product categorization (taxonomy classification), content moderation (policy violation detection), review quality scoring (helpful/not helpful, fake review detection), image quality assessment, search relevance judgment.

**Quality requirements:** Inter-annotator agreement > 0.70 (lower threshold, higher volume). Spot-check sampling at 10% for content moderation. Full review for escalated content (potential legal issues, CSAM detection).

**Workforce:** Scalable crowd workforce for product categorization. Language-specific annotators for multi-market content. Trained moderators for sensitive content with mandatory wellness support and rotation policies.

**Compliance:** Content policy documentation with version history. Appeals workflow for moderation decisions. Annotator wellness: mandatory breaks, content exposure limits, counseling access for moderators reviewing harmful content.

---

## 4. Core Functional Requirements

### 4.1 Task Engine

| ID | Requirement | Priority | Industry Notes |
|---|---|---|---|
| TE-01 | Define annotation schemas as JSONB configurations supporting text classification, NER spans, bounding boxes, polygons, preference pairs, free-text, and custom types | P0 | Schema flexibility is how we support all industries with one engine |
| TE-02 | Create task queues from data sources (S3 bucket, database query, API upload, streaming ingestion) | P0 | AV companies need streaming from sensor pipelines; healthcare needs batch from PACS |
| TE-03 | Route tasks to qualified annotators based on skill profile, domain certification, and current workload | P0 | Healthcare: only certified radiologists see radiology tasks |
| TE-04 | Priority queue with configurable urgency levels (critical, high, normal, low) and deadline-aware scheduling | P0 | Active learning samples should be high priority; backfill can be low |
| TE-05 | Task grouping: assign related items to same annotator for consistency (e.g., all frames from one driving scene) | P1 | AV: temporal consistency across frames. Healthcare: all slices from one study |
| TE-06 | Annotation guidelines embedded in task interface with examples, edge cases, and decision trees | P0 | Reduces training time and improves consistency across annotators |
| TE-07 | Schema versioning with migration support (add new label categories without invalidating existing annotations) | P1 | ML teams iterate on label taxonomies frequently |
| TE-08 | Task reservation with configurable timeout (prevent abandoned tasks from blocking queue) | P0 | Annotator starts task, gets interrupted, task auto-returns to queue after 30 min |
| TE-09 | Bulk task creation from dataset upload (CSV, JSONL, S3 manifest) | P0 | ML teams submit 50K items at once |
| TE-10 | Real-time task progress dashboard (assigned, in-progress, completed, in-review, accepted) | P0 | Annotation lead and ML engineer both need pipeline visibility |

### 4.2 Annotation Pipeline

| ID | Requirement | Priority | Industry Notes |
|---|---|---|---|
| AP-01 | Multi-stage workflow: configurable 1-3 stages (label, review, adjudicate) per project | P0 | RLHF safety: 3 stages mandatory. Product categorization: 1 stage + sampling |
| AP-02 | Redundant annotation: configurable overlap (1-5 annotators per item) for agreement measurement | P0 | 3-way annotation for quality-critical projects, 1-way for volume projects |
| AP-03 | Conditional routing: if annotators agree, auto-accept. If they disagree, route to review/adjudication | P0 | Saves expert time by only escalating genuine disagreements |
| AP-04 | Annotation interface supporting text, image, video, audio, LiDAR point cloud, and document types | P0 | Different media types per industry |
| AP-05 | Side-by-side comparison view for reviewers (original data + annotator labels + guideline reference) | P0 | Reviewer needs to see what the annotator did in context |
| AP-06 | Adjudication interface: show all annotator responses, agreement metrics, and allow expert to select/override | P0 | Expert resolves disagreements with full context |
| AP-07 | Flag-for-review: annotators can flag ambiguous items with a comment explaining the ambiguity | P0 | Better to flag than guess. Flagged items route to expert queue |
| AP-08 | Annotation versioning: track all changes to an annotation with actor and timestamp | P0 | Audit trail for compliance (HIPAA, SOX, ISO 26262) |
| AP-09 | Real-time collaboration: allow reviewer to send annotation back to original annotator with feedback | P1 | Training opportunity: annotator learns from reviewer's correction |
| AP-10 | Batch accept/reject for reviewers processing high-volume queues | P1 | Reviewer efficiency on volume-oriented projects |
| AP-11 | Model-assisted pre-labeling: display model predictions as suggested annotations that annotators accept/correct | P1 | Reduces annotation time by 40-60% for categories where model is already decent |
| AP-12 | Configurable annotation time limits with warning and auto-skip | P1 | Prevent annotators from spending 10 minutes on a single item |

### 4.3 Quality Engine

| ID | Requirement | Priority | Industry Notes |
|---|---|---|---|
| QE-01 | Inter-annotator agreement: Cohen's kappa (2 annotators), Fleiss' kappa (3+), Krippendorff's alpha (any) | P0 | Different metrics for different annotation types |
| QE-02 | Spatial agreement: IoU for bounding boxes, Dice coefficient for segmentation masks | P0 | AV and healthcare need spatial quality metrics |
| QE-03 | Text agreement: span-level F1 for NER, BLEU/ROUGE for free-text responses | P0 | Clinical NER and RLHF response evaluation |
| QE-04 | Golden set evaluation: insert pre-labeled gold items into task queues without annotator knowledge | P0 | Ongoing calibration without observer effect |
| QE-05 | Per-annotator accuracy tracking with rolling window (last 100 items, last 7 days, lifetime) | P0 | Detect accuracy degradation early |
| QE-06 | Automatic de-qualification: if annotator accuracy drops below threshold for N consecutive golden items, pause their access | P0 | Prevent bad labels from entering pipeline |
| QE-07 | Quality alerts: notify annotation lead when agreement drops below project threshold | P0 | Real-time intervention before bad data accumulates |
| QE-08 | Bias detection: distribution analysis across annotators (does one annotator over-label a specific category?) | P1 | Prevents systematic bias in training data |
| QE-09 | Annotation difficulty scoring: identify items with consistently low agreement across multiple projects | P1 | Hard items may indicate ambiguous guidelines or genuinely hard examples |
| QE-10 | Quality report generation: per-project, per-annotator, per-batch with exportable format | P0 | Compliance reporting and ML team review |
| QE-11 | Consensus resolution: majority vote (configurable quorum), weighted vote (by annotator accuracy), expert tiebreak | P0 | Different resolution strategies per project |
| QE-12 | Re-annotation routing: items that fail quality checks automatically re-enter the queue for fresh annotation | P0 | Self-healing pipeline |

### 4.4 Model Feedback Loop

| ID | Requirement | Priority | Industry Notes |
|---|---|---|---|
| FL-01 | Active learning: uncertainty sampling based on model prediction entropy, margin sampling, or committee disagreement | P0 | Core value prop: label what the model needs, not random examples |
| FL-02 | Error-based curriculum: analyze model errors by category/slice and generate targeted re-annotation batches | P0 | "Model is weak on nighttime scenes" -> prioritize nighttime annotation |
| FL-03 | Drift detection: compare production data distribution against training data using KL divergence, PSI, embedding distance | P0 | Alert when production data no longer looks like training data |
| FL-04 | Model-in-the-loop pre-labeling: run model predictions on new data, display as suggestions to annotators | P1 | Annotator corrects model prediction instead of labeling from scratch |
| FL-05 | Training data provenance: trace every training example back to annotators, reviewers, quality scores, and batch metadata | P0 | Model card documentation requires data lineage |
| FL-06 | Batch-to-model tracking: link annotation batches to model training runs and evaluation metrics | P1 | "Which batch of labels caused the accuracy regression?" |
| FL-07 | Annotation curriculum: automatically adjust the mix of annotation categories based on model performance gaps | P1 | Budget allocation: spend more on categories where model is weakest |
| FL-08 | Export in standard ML formats: JSONL, CSV, TFRecord, HuggingFace datasets, COCO format, Pascal VOC | P0 | ML teams use different training frameworks |

### 4.5 Workforce Management

| ID | Requirement | Priority | Industry Notes |
|---|---|---|---|
| WF-01 | Annotator profiles with skills, domain certifications, accuracy history, and qualification status | P0 | Foundation for skill-based routing |
| WF-02 | Structured qualification: per-domain tests with golden set items. Pass threshold configurable per domain | P0 | Healthcare: radiology certification test. AV: 3D bounding box test |
| WF-03 | Graduated onboarding: new annotators start with easy tasks, complexity increases as accuracy is demonstrated | P0 | Reduces time-to-productive from weeks to days |
| WF-04 | Throughput tracking: items per hour, average annotation time, idle time between tasks | P0 | Workforce planning and bottleneck identification |
| WF-05 | Annotator leaderboard: visible quality and throughput ranking (opt-in, anonymized) | P1 | Motivation without creating unhealthy competition |
| WF-06 | Workload management: maximum items per shift, mandatory breaks for sensitive content, rotation policies | P0 | Content moderation wellness requirements |
| WF-07 | Payment/compensation tracking: per-item rates, quality bonuses, project-based compensation | P1 | Especially important for managed services and crowd workforce |
| WF-08 | Availability scheduling: annotators set availability windows, tasks only assigned during available hours | P1 | Distributed workforce across time zones |

---

## 5. Non-Functional Requirements

### 5.1 Performance

| Requirement | Target | Rationale |
|---|---|---|
| Task assignment latency | < 2 seconds | Annotators should not wait for next task |
| Annotation save latency | < 500ms | Annotation interface must feel instant |
| Quality metric computation | < 5 seconds per batch of 1,000 | Dashboard should update in near real-time |
| Active learning sample selection | < 30 seconds for 10K candidate pool | Should not block annotation pipeline |
| Export generation | < 5 minutes for 100K annotated examples | ML team needs data quickly for training |
| Concurrent annotators | 200+ simultaneous | Enterprise-scale annotation operations |

### 5.2 Reliability

| Requirement | Target | Rationale |
|---|---|---|
| System uptime | 99.9% | Annotation teams work shifts; downtime loses productive hours |
| Zero annotation data loss | RPO = 0 | Every annotation action must be durably stored before acknowledging to annotator |
| Workflow recovery | Resume from last step after crash | Temporal durable execution |

### 5.3 Security and Compliance

| Requirement | Target | Rationale |
|---|---|---|
| PHI de-identification | Before annotation exposure | HIPAA requirement for healthcare data |
| Audit trail | Every action logged with actor, timestamp, resource | HIPAA, SOX, ISO 26262 compliance |
| Role-based access control | Per-project, per-domain permissions | Annotators only see data they're qualified/authorized for |
| Data residency | Configurable per project | Healthcare and financial data may have jurisdiction requirements |
| Encryption | AES-256 at rest, TLS 1.3 in transit | Standard for regulated industries |
| Data retention | Configurable per project (90 days to 7 years) | Regulatory requirements vary by industry |

---

## 6. Technical Constraints

**Annotation schema flexibility.** The platform must support arbitrary annotation schemas without database migrations. A healthcare customer defining a new radiology annotation type should not require engineering work. JSONB with schema validation at the application layer.

**Temporal for workflow orchestration.** Multi-stage annotation workflows are long-running (hours to days), require human-in-the-loop signals (reviewer decisions, expert adjudication), and must survive system failures without losing annotator work. Temporal handles durable execution, signals, and per-step retry natively.

**Quality metrics are computationally intensive.** Krippendorff's alpha on large annotation sets is O(n^2). Pre-compute incrementally as annotations arrive rather than recomputing from scratch. Cache per-annotator accuracy scores and update on rolling windows.

**Active learning requires model inference.** Uncertainty sampling needs model predictions on unlabeled data. The platform integrates with the ML team's model serving infrastructure (via API) rather than hosting models itself. The platform sends candidate items to the model endpoint and receives prediction scores back.

**Multi-modal data handling.** The platform stores pointers to data assets (S3 paths, URLs) rather than the assets themselves. The annotation interface renders assets directly from storage. This avoids duplicating large data volumes (LiDAR frames can be 100MB+ each).

---

## 7. Phased Delivery

### Phase 0: Core Pipeline (Weeks 1-8)

**Goal:** Prove that structured annotation workflows with quality measurement produce better training data than the ad hoc process.

- Task creation with configurable annotation schemas (text classification, NER, bounding box)
- Single-stage annotation workflow with task assignment and completion tracking
- 3-way redundant annotation with inter-annotator agreement calculation
- Golden set insertion and annotator accuracy tracking
- Majority vote consensus resolution
- Annotator profiles with skill tracking
- Export in JSONL format

**Exit Criteria:**
- 5,000 items annotated through the platform with measured quality metrics
- Inter-annotator agreement (kappa) > 0.75 on text classification tasks
- Golden set accuracy > 90% across annotator pool
- Annotation error rate measurably lower than baseline (target: < 5%)

### Phase 1: Quality at Scale (Weeks 9-16)

**Goal:** Multi-stage workflows, advanced quality metrics, and workforce optimization.

- Multi-stage annotation workflow (label -> review -> adjudicate) with Temporal orchestration
- Conditional routing based on agreement (agree = auto-accept, disagree = escalate)
- Full quality metric suite (kappa, alpha, IoU, span F1)
- Automatic de-qualification on sustained low accuracy
- Structured qualification tests per domain
- Graduated onboarding (easy -> medium -> hard task progression)
- Quality alerts and real-time dashboard
- Schema versioning
- Model-assisted pre-labeling (model predictions as suggestions)

**Exit Criteria:**
- Multi-stage workflows running on 3+ projects
- Annotation error rate < 3%
- Inter-annotator agreement > 0.80
- Time-to-productive for new annotators < 3 days
- 200+ concurrent annotators without performance degradation

### Phase 2: Intelligent Operations (Weeks 17-24)

**Goal:** Close the loop between model performance and data collection.

- Active learning: uncertainty sampling from model predictions
- Error-based curriculum: targeted re-annotation from model error analysis
- Drift detection: production vs. training data distribution monitoring
- Batch-to-model tracking: link annotation batches to model evaluation metrics
- Training data provenance for model card documentation
- Export in all standard formats (JSONL, TFRecord, HuggingFace, COCO)
- Cross-project analytics dashboard
- Budget tracking and cost-per-example reporting
- Industry-specific compliance reporting (HIPAA, SOX, ISO 26262)

**Exit Criteria:**
- Active learning demonstrates 2x efficiency over random sampling
- Data-to-model cycle time < 2 weeks
- 2,000+ usable training examples per team-day
- Drift detection triggering re-annotation within 24 hours of distribution shift
- Compliance reports generated on-demand for auditors

### Phase 3: Platform Maturity (Weeks 25+)

- API for programmatic task creation and data export (ML pipeline integration)
- Annotator marketplace: connect to external annotation vendors with quality SLAs
- Multi-modal annotation support expansion (video, audio, 3D point cloud)
- Annotation simulator: estimate cost and timeline before committing to a project
- Custom quality metric plugins (domain-specific agreement measures)
- Federated annotation: distribute tasks across teams with separate quality tracking per team
- Self-serve project creation (ML teams configure and launch projects without ops involvement)

---

## 8. Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|---|---|---|---|
| Annotators game golden sets (memorize gold items) | Quality metrics become unreliable | Medium | Rotating golden set pool. Golden items refreshed monthly. Statistical detection of suspiciously high golden accuracy vs. low peer agreement. |
| Active learning creates annotation bottleneck (only hard items left in queue) | Annotator throughput drops, frustration increases | High | Mix active learning samples with easier items (70/30 ratio). Monitor annotator satisfaction and throughput per session. |
| JSONB schema flexibility leads to inconsistent data | Downstream ML pipelines break on schema mismatches | Medium | Schema validation at write time. Required fields enforced. Schema registry with compatibility checks (backward, forward). |
| Healthcare data contains residual PHI after de-identification | HIPAA violation, fines, reputation damage | Low | Automated PHI detection scan on every item before annotation exposure. Manual review for flagged items. De-identification validation as a CI step. |
| Inter-annotator agreement is naturally low on ambiguous tasks | Quality metrics look bad even when annotations are "correct" | High | Separate genuinely ambiguous items (multi-label or uncertain) from annotator error. Flag items with sustained low agreement for guideline clarification. |
| Model-assisted pre-labeling biases annotators toward model predictions | Annotators rubber-stamp predictions instead of evaluating independently | Medium | A/B test pre-labeling vs. blank annotation to measure anchoring effect. Monitor correction rate. If correction rate < 5% on tasks with known errors, disable pre-labeling for that annotator. |
| Drift detection generates too many false alerts | Alert fatigue, team ignores real drift | Medium | Configurable sensitivity thresholds per project. Require sustained drift (3+ consecutive windows) before alerting. Weekly drift summary instead of real-time alerts for slow-moving distributions. |

---

## Appendices

### A. Annotation Type Reference

| Type | Input | Output Schema | Agreement Metric | Use Cases |
|---|---|---|---|---|
| Text Classification | Text document/passage | `{"label": "category", "confidence": float}` | Cohen's kappa | Sentiment, intent, fraud classification |
| Named Entity Recognition | Text with pre-tokenization | `{"spans": [{"start": int, "end": int, "label": str}]}` | Span-level F1 | Clinical NER, financial entity extraction |
| Bounding Box | Image | `{"boxes": [{"x": int, "y": int, "w": int, "h": int, "label": str}]}` | IoU | Object detection, tumor localization |
| Polygon Segmentation | Image | `{"polygons": [{"points": [[x,y]...], "label": str}]}` | Dice coefficient | Organ segmentation, lane marking |
| 3D Bounding Box | LiDAR point cloud | `{"boxes_3d": [{"center": [x,y,z], "dims": [l,w,h], "rotation": float, "label": str}]}` | 3D IoU | Autonomous vehicle perception |
| Preference Pair | Two text responses | `{"preferred": "A" or "B", "reasoning": str, "categories": [str]}` | Cohen's kappa | RLHF, model evaluation |
| Safety Rating | Text/image content | `{"safe": bool, "categories": [str], "severity": str}` | Fleiss' kappa (3+ raters) | Content moderation, AI safety |
| Free-Text Response | Prompt or context | `{"response": str}` | BLEU/ROUGE (soft), human eval | Instruction tuning, summarization |
| Temporal Tracking | Video/frame sequence | `{"tracks": [{"object_id": str, "frames": [{"frame": int, "box": {...}}]}]}` | MOTA/MOTP | Object tracking, activity recognition |

### B. Quality Metric Reference

| Metric | Range | Use When | Interpretation |
|---|---|---|---|
| Cohen's kappa | -1 to 1 | 2 annotators, categorical labels | > 0.80 = strong, 0.60-0.80 = moderate, < 0.60 = weak |
| Fleiss' kappa | -1 to 1 | 3+ annotators, categorical labels | Same interpretation as Cohen's |
| Krippendorff's alpha | -1 to 1 | Any number of annotators, handles missing data | > 0.80 = reliable, 0.67-0.80 = tentative, < 0.67 = unreliable |
| IoU (Intersection over Union) | 0 to 1 | Bounding boxes, segmentation | > 0.80 = strong, 0.50-0.80 = acceptable, < 0.50 = poor |
| Dice coefficient | 0 to 1 | Segmentation masks | > 0.85 = strong, 0.70-0.85 = acceptable |
| Span-level F1 | 0 to 1 | NER span matching | > 0.90 = strong, 0.80-0.90 = acceptable |
| BLEU | 0 to 1 | Free-text similarity | Context-dependent; used as relative comparison, not absolute threshold |
| MOTA | -inf to 1 | Object tracking accuracy | > 0.50 = acceptable for complex scenes |

### C. Glossary

| Term | Definition |
|---|---|
| **Active Learning** | ML technique that selects the most informative unlabeled examples for human annotation, maximizing model improvement per labeled example. |
| **Adjudication** | Expert review stage where a senior annotator resolves disagreements between initial annotators. |
| **Cohen's Kappa** | Statistical measure of inter-annotator agreement that accounts for agreement occurring by chance. |
| **Consensus Resolution** | Process of producing a single "correct" label from multiple annotators' responses (majority vote, weighted vote, expert override). |
| **Curriculum Learning** | Strategy of ordering training examples from easy to hard, applied here to both annotator onboarding and active learning batch construction. |
| **Drift Detection** | Monitoring for changes in the statistical distribution of production data compared to training data. |
| **Golden Set** | Pre-labeled items with known correct answers inserted into annotation queues to measure annotator accuracy. Annotators do not know which items are golden. |
| **Inter-Annotator Agreement (IAA)** | Measurement of how often multiple annotators assign the same label to the same item. Low IAA indicates ambiguous guidelines, hard examples, or annotator quality issues. |
| **IoU (Intersection over Union)** | Spatial overlap metric for bounding boxes and segmentation masks. Area of overlap divided by area of union. |
| **Krippendorff's Alpha** | Reliability metric that handles any number of annotators, any number of categories, and missing data. More general than Cohen's kappa. |
| **Model-Assisted Pre-labeling** | Using an existing model's predictions as suggested annotations that human annotators verify and correct, reducing annotation time. |
| **PSI (Population Stability Index)** | Metric for measuring how much a distribution has shifted between two time periods. Used in drift detection. |
| **RLHF (Reinforcement Learning from Human Feedback)** | Training technique where human preference judgments guide model behavior. Requires large volumes of preference pair annotations. |
| **Uncertainty Sampling** | Active learning strategy that selects examples where the model is least confident in its predictions. |
