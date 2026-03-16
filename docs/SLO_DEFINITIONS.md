# AI Data Ops Platform - SLO Definitions

## SLO 1: Annotation Throughput (Core Team Productivity)
**Target:** 99% of annotation tasks completed within target SLA (2,340 examples/team-day)
**Error Budget:** 1% of tasks delayed beyond SLA per week
**Burn Rate Alert:** >40% of weekly throughput budget lost in 24 hours

### Rationale
The 11.7x improvement in annotation throughput (200 → 2,340 examples/team-day) is the core product value. This SLO ensures consistent annotator productivity by guaranteeing 99% of tasks are available and responsive within target SLA. A task SLA includes: UI load time (<2s) + task clarity (<1s to understand) + annotation (<3 min per example for complex tasks, <1 min for simple). The 99% target allows for occasional bottlenecks (network lag, task complexity outliers) while maintaining team velocity.

### Measurement
- Count: Tasks completed within SLA vs. total tasks assigned (sample: 100% of production tasks)
- Success: Task loaded, annotated, submitted within target SLA
- Failure: Task takes >2x SLA time (e.g., >6 min for 3-min example)
- Burn rate threshold: If >40% of weekly throughput lost in 24 hours, investigate infrastructure or task distribution

---

## SLO 2: Label Quality (Accuracy for Training Data)
**Target:** 95% of annotations agree with gold standard labels on inter-rater agreement (IRA) sample
**Error Budget:** 5% label disagreement per week
**Burn Rate Alert:** >30% of weekly quality budget consumed in 3 days

### Rationale
Annotations feed ML training pipelines. Low-quality labels (disagreement with gold standard) degrade downstream model accuracy. The 95% IRA target balances speed (lower quality = faster annotation) with training data usability. 5% disagreement is acceptable for subjective tasks (content classification, sentiment) but unacceptable for objective tasks (bounding boxes, entity spans). IRA is measured weekly using 5-10% sampled examples re-annotated by lead annotators.

### Measurement
- Count: Annotation disagreement rate on IRA sample (5-10% of weekly tasks)
- Success: Annotator label matches gold standard label with >95% agreement
- Failure: Annotator label disagrees (different class, wrong span, etc.)
- Burn rate threshold: If >30% of weekly quality budget in 3 days, trigger retraining on problematic tasks

---

## SLO 3: Model Drift Detection (Active Learning Loop Integrity)
**Target:** 99% of model predictions correctly flagged for uncertainty/drift within 24 hours
**Error Budget:** 1% of drift cases missed per week
**Burn rate Alert:** Any undetected model drift triggering model failure = incident

### Rationale
AI Data Ops uses active learning: annotators label uncertain model predictions, which improves the model in a feedback loop. Undetected model drift (where model's confidence is high but accuracy is low) breaks this loop. A 99% detection target ensures the feedback loop stays healthy. The "24-hour" window allows for batch processing (daily model retraining) while catching drift quickly enough to prevent cascading errors. Unlike performance SLOs, drift detection failures are asymmetric: missed drift = poor model quality that compounds over time.

### Measurement
- Count: Model predictions flagged for review vs. those that subsequently fail in production
- Success: High-uncertainty predictions identified before they reach users
- Failure: Low-uncertainty prediction with high actual error (model was overconfident)
- Burn rate threshold: Any significant drift missed = incident; requires immediate model retraining review

---

## SLO 4: Annotation UI Performance (Annotator Experience)
**Target:** 98% of UI interactions respond in <1 second
**Error Budget:** 2% of interactions >1s per day
**Burn Rate Alert:** >50% of daily UI latency budget consumed in 4 hours

### Rationale
Annotators accept/reject/classify examples in rapid succession. UI lag (>1s) breaks flow state and reduces throughput. A 1-second target is tight but achievable with optimized rendering and database queries. This directly impacts the 2,340 examples/team-day throughput target: a 1-second UI lag per example × 2,340 examples = 39 minutes of wasted time/day/team.

### Measurement
- Count: UI interaction latency (button clicks, form submissions, image loads) from client
- Success: Interaction responds in <1 second
- Failure: Interaction takes >1 second (API latency, image render, etc.)
- Burn rate threshold: If >50% of daily budget in 4 hours, page SRE; likely database or image service issue

---

## SLO 5: Data Pipeline Freshness (Training Data Timeliness)
**Target:** 99% of newly-annotated examples available for training within 4 hours
**Error Budget:** 1% of examples delayed >4 hours per week
**Burn Rate Alert:** >40% of weekly freshness budget consumed in 24 hours

### Rationale
Active learning requires fast feedback loops: annotate → train model → show predictions → annotate again. If new annotations take >4 hours to reach training pipeline, the loop stalls. A 4-hour window is tight enough to keep models fresh (daily retraining cycle) while loose enough to batch processing for efficiency. This prevents model staleness where yesterday's feedback isn't incorporated into today's predictions.

### Measurement
- Count: Time from annotation submission to appearance in training dataset
- Success: Annotation available in training data within 4 hours
- Failure: Annotation takes >4 hours (likely stuck in queue or batch job delayed)
- Burn rate threshold: If >40% of weekly budget in 24 hours, check data pipeline jobs (likely backed up)

---

## Error Budget Governance
- **Review Cadence:** Daily check on throughput/UI latency; weekly check on label quality and drift detection
- **Escalation:** If throughput SLO burns >40% budget by day 3, allocate annotation/UI optimization
- **Quality audits:** Weekly IRA measurement; if <95%, flag problematic annotators for retraining
- **Drift monitoring:** Daily model performance checks; if accuracy drops >5% unexpectedly, trigger retraining
- **Feature freeze:** If label quality drops <90%, pause new features; focus on quality recovery

