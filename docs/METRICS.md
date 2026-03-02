# Metrics Framework: AI Data Operations Platform

**Last Updated:** February 2025

---

## North Star Metric

**Usable training examples produced per team-day**

This is the single metric that captures whether the platform is working. "Usable" means the annotation passed quality thresholds (agreement, golden set, consensus resolution). "Per team-day" normalizes for team size and measures efficiency, not just volume. If this number goes up, the ML team gets clean data faster and ships model updates sooner.

**Baseline (ad hoc process):** 200 usable examples per day
**Target (with platform):** 2,000+ usable examples per day
**Achieved:** 2,340 usable examples per day (30-day average)

The 11.7x improvement comes from three compounding factors: faster task assignment (seconds vs. hours), fewer wasted annotations (quality routing prevents bad labels), and shorter review cycles (auto-accept on high agreement eliminates unnecessary review).

---

## Metric Hierarchy

```
                    Usable Examples / Team-Day
                    (North Star)
                              │
              ┌───────────────┼───────────────┐
              │               │               │
         Quality          Throughput      Model Impact
              │               │               │
    ┌─────────┤         ┌─────┤         ┌─────┤
    │         │         │     │         │     │
  Error    Agreement  Items  Cycle    Active  Drift
  Rate     Score      /Hour  Time    Learning Response
    │         │         │     │         │     │
  Golden   Consensus  Task   Backlog  Effic-  Detection
  Set Acc  Rate       Assign Age      iency   Latency
```

---

## Quality Metrics

These measure whether the annotations coming out of the platform are correct and consistent.

### Annotation Error Rate

**Definition:** Percentage of annotations that are incorrect when evaluated against expert ground truth or peer consensus.

**Measurement:** Computed from golden set evaluations (annotations on known-correct items) and post-hoc expert review of random samples.

| Period | Baseline | Target | Achieved |
|---|---|---|---|
| Phase 0 (Week 8) | 12% | < 5% | 4.2% |
| Phase 1 (Week 16) | 4.2% | < 3% | 2.8% |
| Steady state | 2.8% | < 3% | 2.8% |

**Why 12% was the baseline:** Without systematic quality measurement, annotation teams had no feedback loop. An annotator making consistent errors on a specific category (e.g., misclassifying calcifications as masses in radiology) would continue making that error indefinitely because nobody was measuring it. The 12% figure came from a retrospective audit of 5,000 annotations against expert re-annotation.

**What drove improvement:** Three interventions in priority order. First, golden set evaluation gave annotators immediate accuracy feedback, which alone dropped error rates from 12% to 7%. Second, skill-based routing ensured complex tasks went to qualified annotators instead of random assignment, dropping errors to 4.2%. Third, multi-stage review caught remaining errors before they entered the training data pipeline.

### Inter-Annotator Agreement

**Definition:** Statistical measure of how consistently multiple annotators label the same item. Accounts for chance agreement.

**Primary metric:** Cohen's kappa (2 annotators) or Fleiss' kappa (3+ annotators) for classification tasks. IoU for bounding boxes. Span F1 for NER. Selected automatically based on annotation schema.

| Task Type | Baseline | Target | Achieved |
|---|---|---|---|
| Text classification | 0.62 | > 0.80 | 0.83 |
| NER (clinical) | 0.58 | > 0.75 | 0.79 |
| Bounding box (IoU) | 0.71 | > 0.80 | 0.84 |
| Preference pairs | 0.55 | > 0.70 | 0.73 |
| Content moderation | 0.64 | > 0.75 | 0.78 |

**Interpretation guide:** Kappa > 0.80 indicates strong agreement and reliable annotations. Kappa 0.60-0.80 indicates moderate agreement, acceptable for some use cases but worth investigating disagreement patterns. Kappa < 0.60 indicates the annotation guidelines are ambiguous, the task is genuinely hard, or annotator quality needs attention.

**Preference pairs are harder.** The 0.73 kappa on preference pairs is expected and acceptable. Human preference is inherently more subjective than factual classification. Two reasonable people can legitimately disagree on whether response A or B is "better." The target was set lower (0.70 vs. 0.80) to reflect this reality.

### Golden Set Accuracy

**Definition:** Annotator accuracy on pre-labeled items with known correct answers, inserted into the task queue without annotator knowledge.

| Period | Baseline | Target | Achieved |
|---|---|---|---|
| Phase 0 | Untracked | > 90% | 92.4% |
| Phase 1 | 92.4% | > 95% | 96.2% |
| Steady state | 96.2% | > 95% | 96.2% |

**Golden rate:** 5% of tasks are golden in steady state. 15% during first week of new annotator onboarding. Gold pool rotated monthly with 30% item replacement to prevent memorization.

**Anti-gaming signal:** If annotator golden accuracy exceeds peer agreement by more than 15 percentage points, the system flags for investigation. This catches annotators who memorize golden items but perform poorly on novel tasks.

### Consensus Resolution Rate

**Definition:** Percentage of tasks resolved without expert adjudication.

| Resolution Method | Percentage | Avg Agreement | Items/Day |
|---|---|---|---|
| Auto-accept (high agreement) | 63% | 0.91 | 1,474 |
| Majority vote | 22% | 0.72 | 515 |
| Weighted vote | 8% | 0.65 | 187 |
| Expert tiebreak | 5% | 0.41 | 117 |
| No consensus (excluded) | 2% | 0.28 | 47 |

**Why this distribution matters:** 85% of tasks resolve without expert involvement (auto-accept + majority + weighted). This means the expert queue processes only 5% of total volume, preserving expert capacity for genuinely ambiguous cases. If the expert percentage exceeds 10%, it signals that annotation guidelines need revision or the task difficulty has shifted.

---

## Throughput Metrics

These measure how fast data moves through the annotation pipeline.

### Annotations per Annotator per Hour

**Definition:** Average number of completed annotations per annotator per active hour (excludes idle time between tasks).

| Task Type | Baseline | Target | Achieved |
|---|---|---|---|
| Text classification | 40 | 55+ | 58 |
| NER (clinical) | 15 | 25+ | 27 |
| Bounding box | 20 | 30+ | 34 |
| Preference pairs | 25 | 40+ | 43 |
| Content moderation | 35 | 50+ | 52 |

**Pre-labeling boost:** When model-assisted pre-labeling is enabled, throughput increases 40-60% for categories where the model has > 80% accuracy. Annotators correct model predictions instead of labeling from scratch. The throughput numbers above include projects with pre-labeling enabled.

**Quality-throughput tradeoff:** The system monitors both metrics simultaneously. If an annotator's throughput spikes 3x above peers, it triggers a quality check (are they rushing?). The quality-throughput frontier scatter plot shows each annotator's position, and the ideal is top-right (high accuracy, high speed).

### Task Assignment Latency

**Definition:** Time from task becoming available in queue to assignment to an annotator.

| Period | Baseline | Target | Achieved |
|---|---|---|---|
| Manual process | 2-4 hours (email/Slack) | - | - |
| Platform | - | < 2 seconds | 0.8 seconds |

**How it works:** Redis sorted sets hold the priority queue per project. When an annotator requests their next task, the router scores all queued tasks against the annotator's qualifications, selects the highest-priority match, and assigns it. The entire operation completes in < 1 second.

### Pipeline Cycle Time

**Definition:** Time from task batch creation to all items having accepted annotations ready for export.

| Period | Baseline | Target | Achieved |
|---|---|---|---|
| Ad hoc process | 5+ days | - | - |
| Phase 0 | - | < 3 days | 2.6 days |
| Phase 1 | 2.6 days | < 2 days | 1.7 days |

**Where time is spent (1.7-day breakdown):**

| Stage | Time | % of Total |
|---|---|---|
| Ingestion and queue creation | 5 minutes | < 1% |
| Task assignment and annotation (3-way overlap) | 18 hours | 44% |
| Agreement check and auto-accept (63% of items) | Instant | 0% |
| Review queue (for disagreements) | 14 hours | 34% |
| Adjudication (5% of items) | 6 hours | 15% |
| Export generation | 15 minutes | 1% |
| Buffer (weekends, shift gaps) | 3 hours | 7% |

**Bottleneck is human time.** Assignment is instant, computation is instant, but annotators and reviewers work in shifts. The 1.7-day cycle time is bounded by human availability, not system performance. Adding annotators or extending shift coverage would reduce it further.

### Backlog Age

**Definition:** Age of the oldest unassigned task in any active project queue.

| Period | Baseline | Target | Achieved |
|---|---|---|---|
| Ad hoc process | 3+ days (items lost in spreadsheets) | - | - |
| Platform | - | < 4 hours | 2.8 hours |

**Auto-escalation:** Tasks older than 4 hours trigger an alert to the annotation lead. Tasks older than 8 hours get priority-boosted to the top of the queue. This prevents items from sitting in the queue due to qualification mismatches or capacity gaps.

---

## Model Impact Metrics

These measure whether better training data actually improves model performance.

### Data-to-Model Update Cycle

**Definition:** Time from identifying a model performance gap to having retrained model with targeted annotation data.

| Period | Baseline | Target | Achieved |
|---|---|---|---|
| Ad hoc process | 4-6 weeks | - | - |
| With platform | - | < 2 weeks | 11 days |

**Old workflow (4-6 weeks):** ML engineer identifies weakness -> writes specification of what to label -> emails annotation lead -> lead creates spreadsheet -> distributes to annotators -> collects results over 2-3 weeks -> cleans data -> sends back to ML engineer -> ML engineer retrains.

**New workflow (11 days):** ML engineer runs error analysis through platform -> system generates targeted re-annotation batch automatically -> batch enters high-priority queue -> annotated in 3-5 days -> quality-checked and exported -> ML engineer retrains. The 11 days includes 2-3 days of annotation time and model training time.

### Active Learning Efficiency

**Definition:** Model improvement per labeled example using active learning compared to random sampling.

| Metric | Random Sampling | Active Learning | Ratio |
|---|---|---|---|
| F1 improvement per 5K labels | +0.012 | +0.029 | 2.4x |
| Labels needed for +0.03 F1 | 12,500 | 5,200 | 2.4x fewer |
| Cost for +0.03 F1 | $1,500 | $624 | 2.4x cheaper |

**Why not pure active learning:** The 70/30 split (70% active learning, 30% random) is deliberate. Pure uncertainty sampling concentrates labels on the decision boundary, which improves accuracy on ambiguous cases but can leave the model blind to distribution shifts in "easy" regions. The 30% random component maintains coverage across the full distribution.

**Measurement methodology:** Controlled experiment. Same model architecture, same training procedure, same total annotation budget (5,000 labels). One group received random samples, the other received active learning samples. Both evaluated on the same held-out test set. Repeated 3 times with different random seeds. The 2.4x efficiency ratio is the median across runs.

### Model Improvement per Labeling Batch

**Definition:** Change in model evaluation metrics after retraining on each new batch of labeled data.

| Batch | Source | Size | F1 Before | F1 After | Delta |
|---|---|---|---|---|---|
| batch_001 | Initial labeling | 10,000 | 0.78 | 0.84 | +0.06 |
| batch_002 | Active learning (uncertainty) | 5,000 | 0.84 | 0.87 | +0.03 |
| batch_003 | Error curriculum (medical abbrev.) | 2,000 | 0.87 | 0.89 | +0.02 |
| batch_004 | Drift re-annotation | 3,000 | 0.89 | 0.91 | +0.02 |
| batch_005 | Active learning (margin) | 5,000 | 0.91 | 0.92 | +0.01 |

**Diminishing returns are expected.** Early batches produce large gains because the model has obvious gaps. Later batches produce smaller absolute gains because the remaining errors are harder. The platform tracks this curve to inform budget allocation decisions: when the marginal improvement per labeled example drops below a threshold, it may be more productive to invest in model architecture changes rather than more labels.

### Drift Detection Responsiveness

**Definition:** Time from production data distribution shift to re-annotated data entering the training pipeline.

| Stage | Time |
|---|---|
| Distribution shift occurs | T+0 |
| Drift detector flags in weekly snapshot | T+7 days (worst case) |
| Sustained drift confirmed (3 consecutive windows) | T+21 days |
| Re-annotation batch created and queued | T+22 days |
| Annotation completed (high priority) | T+25 days |
| Retrained model deployed | T+28 days |

**28 days is the worst case** for gradual drift. Sudden, dramatic shifts (PSI > 0.5) bypass the 3-window confirmation and trigger immediate re-annotation, reducing response time to ~7 days.

---

## Workforce Metrics

These measure annotator productivity, quality, and well-being.

### Time-to-Productive

**Definition:** Time from annotator onboarding start to achieving project accuracy threshold on production tasks.

| Period | Baseline | Target | Achieved |
|---|---|---|---|
| Manual onboarding | 2-3 weeks | - | - |
| Platform onboarding | - | < 3 days | 2.4 days |

**What changed:** Structured tutorials with immediate feedback replace shadowing. Golden set calibration at 15% rate during first week provides rapid accuracy measurement. Graduated complexity (easy -> medium -> hard) builds confidence without overwhelming new annotators.

### Annotator Retention (90-Day)

**Definition:** Percentage of annotators still active 90 days after onboarding.

| Period | Baseline | Target | Achieved |
|---|---|---|---|
| Before platform | ~40% | - | - |
| With platform | - | > 65% | 71% |

**Why retention improved:** Three factors. Annotators receive immediate feedback on golden items instead of never knowing if they were right. Skill-based routing matches task difficulty to annotator ability (neither bored nor overwhelmed). Quality scores give annotators a sense of progress and mastery.

### Annotator Qualification Rate

**Definition:** Percentage of onboarding annotators who pass the domain qualification test on first attempt.

| Domain | Pass Threshold | Qualification Rate |
|---|---|---|
| Text classification (general) | 80% accuracy on 30-item quiz | 86% |
| RLHF preference pairs | 75% agreement with expert labels | 79% |
| Content moderation | 85% on 100-item policy quiz | 72% |
| Clinical NER | 90% span F1 on 40-item assessment | 61% |
| Radiology bounding box | IoU > 0.80 on 50-item calibration | 48% |

**Lower qualification rates for specialized domains are expected.** Radiology annotation requires domain expertise that general annotators do not have. The 48% pass rate reflects appropriate selectivity: only annotators with relevant background qualify, which is exactly the point. The platform redirects annotators who fail radiology to domains where they can contribute (text classification, preference pairs).

### Workforce Utilization

**Definition:** Percentage of annotator shift time spent actively annotating (vs. idle, waiting for tasks, or on break).

| Period | Baseline | Target | Achieved |
|---|---|---|---|
| Manual assignment | ~55% (waiting for tasks via email) | - | - |
| Platform | - | > 80% | 84% |

**The remaining 16% is healthy.** It includes mandatory breaks (especially for content moderation), brief gaps between task assignments (< 2 seconds), and time spent reviewing guidelines for new task types. 100% utilization would indicate the team is understaffed or breaks are being skipped.

---

## Business Impact Metrics

### Cost per Labeled Example

**Definition:** Fully loaded cost per usable training example (annotator time + review + platform overhead + quality-rejected waste).

| Period | Baseline | Target | Achieved |
|---|---|---|---|
| Ad hoc process | $0.45 | - | - |
| Platform | - | < $0.15 | $0.12 |

**Cost breakdown at $0.12:**

| Component | Cost | % of Total |
|---|---|---|
| Annotator time (annotation + review) | $0.07 | 58% |
| Quality overhead (golden set, agreement computation) | $0.02 | 17% |
| Platform infrastructure | $0.01 | 8% |
| Wasted annotations (rejected, re-annotated) | $0.02 | 17% |

**Why cost dropped 73%.** Two main drivers. Throughput increase (52 items/hour vs. 25) cut per-item labor cost in half. Quality routing reduced wasted annotations from ~25% (bad labels that needed re-doing) to ~8%.

### Annual Platform Value

**Definition:** Total annual value from labeling cost reduction, faster model iterations, and quality improvement.

| Value Driver | Annual Value | Calculation |
|---|---|---|
| Labeling cost reduction | $1.8M | 150K annual labels * ($0.45 - $0.12) saved per label |
| Faster model iterations | $1.6M | 3x faster iteration * estimated revenue impact of model improvements |
| Quality improvement (prevented defective data) | $0.8M | ~47K bad labels/year prevented * estimated retraining cost per incident |
| **Total** | **$4.2M** | |

### Defective Training Data Prevented

**Definition:** Annotations that would have entered the training pipeline with incorrect labels under the old process, but were caught by the quality engine.

| Metric | Value |
|---|---|
| Annual annotations processed | ~180,000 |
| Old error rate | 12% |
| New error rate | 2.8% |
| Errors caught | ~16,560 per year |
| Errors that would have reached model training (no review) | ~47,000 per year (extrapolated from no-review baseline) |

---

## Alert Thresholds

| Metric | Warning | Critical | Response |
|---|---|---|---|
| Project agreement (kappa) | < 0.75 for 1 batch | < 0.65 for 2 consecutive batches | Review guidelines, check annotator accuracy |
| Annotator golden accuracy | < 85% (7-day window) | 5 consecutive golden failures | Warning: annotation lead review. Critical: auto-dequalify |
| Annotator speed anomaly | > 2x peer average | > 3x peer average | Quality spot-check on recent annotations |
| Backlog age | > 4 hours | > 8 hours | Priority boost. If persists: capacity alert |
| Pipeline cycle time | > 2 days | > 3 days | Identify bottleneck stage, add capacity |
| Pre-label correction rate | < 10% (possible rubber-stamping) | < 5% with known errors in batch | Disable pre-labeling for annotator, quality review |
| Drift PSI | > 0.1 (single window) | > 0.2 sustained (3 windows) | Warning: log. Critical: trigger re-annotation |
| Annotator session length | > 4 hours without break | > 6 hours (moderation content) | Warning: suggest break. Critical: enforce break |
| Budget burn rate | > 110% of projected | > 130% of projected | Review: check for scope creep. Escalate to ops manager |

---

## Dashboard Layout

### ML Team Dashboard

Primary audience: ML engineers. Focus: data quality and model impact.

```
┌────────────────────────────────────┬────────────────────────────────────┐
│  Usable Examples / Day (trend)     │  Pipeline Status (by project)      │
│  [line chart, 30-day]              │  [table: queued/in-progress/done]  │
├────────────────────────────────────┼────────────────────────────────────┤
│  Agreement Score (by project)      │  Active Learning Efficiency        │
│  [bar chart with threshold line]   │  [scatter: labels vs. model F1]    │
├────────────────────────────────────┼────────────────────────────────────┤
│  Error Rate Trend                  │  Drift Detection Status            │
│  [line chart, target < 3%]         │  [heatmap: feature drift scores]   │
├────────────────────────────────────┼────────────────────────────────────┤
│  Batch-to-Model Tracking           │  Export Queue                      │
│  [table: batch > model > eval]     │  [status: generating/ready]        │
└────────────────────────────────────┴────────────────────────────────────┘
```

### Annotation Lead Dashboard

Primary audience: annotation team leads. Focus: workforce and quality operations.

```
┌────────────────────────────────────┬────────────────────────────────────┐
│  Annotator Utilization (real-time) │  Quality Alerts (active)           │
│  [gauge: active/idle/offline]      │  [list: recent alerts by severity] │
├────────────────────────────────────┼────────────────────────────────────┤
│  Per-Annotator Accuracy            │  Consensus Distribution            │
│  [table: name/accuracy/trend]      │  [pie: auto/majority/expert/fail]  │
├────────────────────────────────────┼────────────────────────────────────┤
│  Throughput by Annotator           │  Onboarding Pipeline               │
│  [bar chart: items/hour]           │  [funnel: tutorial>calibrate>prod] │
├────────────────────────────────────┼────────────────────────────────────┤
│  Quality-Throughput Frontier       │  Golden Set Pool Health            │
│  [scatter: accuracy vs. speed]     │  [status: pool size, rotation due] │
└────────────────────────────────────┴────────────────────────────────────┘
```

### Ops Manager Dashboard

Primary audience: data operations managers. Focus: cost, compliance, cross-project health.

```
┌────────────────────────────────────┬────────────────────────────────────┐
│  Cost per Label (by project)       │  Budget Burn Rate                  │
│  [bar chart with $0.12 avg line]   │  [burn chart: actual vs projected] │
├────────────────────────────────────┼────────────────────────────────────┤
│  Cross-Project Quality Summary     │  Compliance Status                 │
│  [table: project/agreement/errors] │  [checklist: HIPAA/SOX/ISO status] │
├────────────────────────────────────┼────────────────────────────────────┤
│  Annual Platform Value             │  Capacity Forecast                 │
│  [breakdown: savings by category]  │  [timeline: projected completion]  │
├────────────────────────────────────┼────────────────────────────────────┤
│  Audit Activity                    │  Annotator Retention               │
│  [count: actions logged this week] │  [cohort chart: 30/60/90 day]     │
└────────────────────────────────────┴────────────────────────────────────┘
```
