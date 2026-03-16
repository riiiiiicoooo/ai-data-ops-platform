# AI Data Ops Platform - Incident Runbooks

---

## Incident 1: Annotator Throughput Collapse (UI Latency Spike)

### Context
On March 15 at 10:30 AM, annotators report the annotation UI is slow—taking 3-5 seconds per task instead of <1 second. Throughput drops from 2,340 examples/team-day to 1,200 examples/team-day. Annotators switch to manual work, abandoning platform. Three teams (36 annotators) are blocked.

### Detection
- **Alert:** Annotation task completion latency p95 >2s sustained for >5 minutes OR daily throughput <95% of target
- **Symptoms:**
  - Annotators report "UI is slow; I'm working on paper"
  - CloudWatch shows database query latency spike to 5-10 seconds
  - Redis cache hit rate drops to 30% (from 90%)

### Diagnosis (10 minutes)

**Step 1: Identify bottleneck**
```bash
# Check database performance
SHOW SLOW_LOG;

# Recent slow queries (>1 second)
SELECT query, exec_time_ms, timestamp
FROM query_logs
WHERE exec_time_ms > 1000
  AND timestamp > NOW() - INTERVAL 15 MINUTES
ORDER BY exec_time_ms DESC
LIMIT 10;

# Likely culprit: Active learning query
SELECT * FROM annotations
WHERE model_version = 'latest'
  AND confidence_score < 0.6
ORDER BY confidence_score ASC
LIMIT 100;
```

**Step 2: Check resource utilization**
```bash
# Database CPU
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=ai-data-ops-db \
  --start-time $(date -u -d '15 min ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 --statistics Average

# Result: CPU 95%+ (database is bottleneck)
```

**Step 3: Check cache effectiveness**
```bash
# Redis cache hit rate
redis-cli INFO stats

# Expected: 90%+ hit rate
# Actual: 30% hit rate → cache miss storm!
```

### Remediation

**Immediate (0-5 min): Shed load & bypass slow queries**
```bash
# Disable active learning queries temporarily (don't suggest uncertain examples)
kubectl set env deployment/annotation-api \
  DISABLE_ACTIVE_LEARNING=true

# Force restart UI servers to clear any stuck connections
kubectl rollout restart deployment/annotation-ui-server

# Increase Redis cache TTL (cache results longer)
redis-cli CONFIG SET maxmemory-policy allkeys-lru
redis-cli CONFIG SET timeout 300
```

**Short-term (5-30 min): Scale database**
```bash
# Add read replica for active learning queries
aws rds create-db-instance-read-replica \
  --db-instance-identifier ai-data-ops-db-read-1 \
  --source-db-instance-identifier ai-data-ops-db

# Route active learning queries to read replica
UPDATE app_config SET active_learning_db_host = 'ai-data-ops-db-read-1.xxx.rds.amazonaws.com'
```

**Root cause investigation (30 min - 1 hour):**

**If cause is active learning query (likely):**
```sql
-- Add index to speed up uncertain prediction query
CREATE INDEX idx_annotations_confidence ON annotations (model_version, confidence_score);

-- Verify index is used
EXPLAIN ANALYZE
SELECT * FROM annotations
WHERE model_version = 'latest'
  AND confidence_score < 0.6
ORDER BY confidence_score ASC
LIMIT 100;
-- Expected: Index Scan (not Sequential Scan)
```

**If cause is full table scan:**
```
-- Current query: Scans all 2.5M annotations
SELECT * FROM annotations
WHERE model_version = 'latest' AND confidence_score < 0.6

-- Optimized: Partition by model version
CREATE TABLE annotations_by_model PARTITION BY LIST (model_version) (
  PARTITION current VALUES IN ('v2.5', 'v2.6'),
  PARTITION archive VALUES IN (default)
);
-- Expected: Query only touches current partition (~50K rows, not 2.5M)
```

**If cause is cache miss storm:**
```python
# Implement cache warming
def warm_cache():
    # Pre-populate cache with active learning results on schedule
    uncertain_examples = query_uncertain_examples()
    for example in uncertain_examples:
        cache.set(f"uncertain:{example.id}", example, ttl=3600)

# Schedule cache warming every hour
schedule.every().hour.do(warm_cache)
```

**Re-enable active learning:**
```bash
kubectl set env deployment/annotation-api \
  DISABLE_ACTIVE_LEARNING=false
```

**Validate recovery:**
```bash
# Check UI latency returned to <1s
SHOW SLOW_LOG;  # Should be empty

# Check annotator productivity returned
SELECT COUNT(*) as completed_tasks
FROM annotations
WHERE created_at > NOW() - INTERVAL 30 MINUTES;
# Expected: 30K tasks (back to normal throughput)
```

### Communication Template

**Internal (Slack #incidents)**
```
AI DATA OPS INCIDENT: Annotation UI Latency Spike
Severity: P2 (Throughput Collapse - 36 annotators blocked)
Duration: 10:30-11:45 UTC (1 hour 15 min)

Root Cause: Active learning query (finding uncertain predictions) missing database index; full table scan on 2.5M annotations, 5-10s latency.

Actions:
1. Disabled active learning queries (shed load)
2. Added database index on (model_version, confidence_score)
3. Created read replica for uncertain prediction queries
4. Restarted annotation UI servers

Resolution: Annotation UI latency returned to <1s by 11:45 UTC; throughput restored to 2,340/team-day.

ETA: Fully stable by 12:00 UTC (validation)
Assigned to: [DB_DBA], [BACKEND_ENGINEER]
```

**Team Notification (Slack to annotators)**
```
@annotators

Annotation UI latency issue has been resolved! The system is back to normal speed. You may have experienced some slowness between 10:30-11:45 UTC.

Please close and reopen the app to ensure you're on the latest version.

Thanks for your patience!
```

### Postmortem Questions
1. Why wasn't the active learning query indexed?
2. Can we automate index recommendations based on slow query log?
3. Should we implement query performance testing in CI/CD?

---

## Incident 2: Label Quality Collapse (Low Inter-Rater Agreement)

### Context
During weekly IRA (Inter-Rater Agreement) measurement, quality auditor discovers that labels from Team C have dropped to 78% agreement with gold standard (target 95%). 350 annotations from Team C reviewed; 77 are wrong/inconsistent. Team C's annotator performance degraded over the past week.

### Detection
- **Alert:** Weekly IRA measurement shows <95% agreement OR >30% of weekly quality budget consumed in <3 days
- **Symptoms:**
  - IRA audit finds 78% agreement (expected 95%+)
  - Team C has 23% error rate (expected <5%)
  - One annotator (Sarah) has 40% error rate (clearly struggling)

### Diagnosis (20 minutes)

**Step 1: Audit affected annotations**
```sql
-- Compare Team C annotations to gold standard
SELECT
  annotator_id,
  COUNT(*) as total_annotations,
  SUM(CASE WHEN matches_gold_standard THEN 1 ELSE 0 END) as correct,
  ROUND(100.0 * SUM(CASE WHEN matches_gold_standard THEN 1 ELSE 0 END) / COUNT(*), 2) as agreement_pct
FROM ira_audit
WHERE team_id = 'team_c'
  AND audit_date = TODAY()
GROUP BY annotator_id
ORDER BY agreement_pct ASC;

-- Result:
-- annotator_id | total | correct | agreement_pct
-- sarah_a      | 50    | 30      | 60% (FAILING)
-- john_b       | 50    | 48      | 96% (NORMAL)
-- maria_c      | 50    | 47      | 94% (NORMAL)
```

**Step 2: Investigate root cause (Sarah specific)**
```
Review Sarah's errors:
- 15 errors: Wrong class label (chose "sentiment:negative" instead of "sentiment:positive")
- 5 errors: Incomplete entity spans (marked partial entity instead of full)
- 10 errors: Concentration issues (errors clustered at end of work session)

Hypothesis: Sarah is fatigued, rushed, or misunderstands task definition
```

**Step 3: Check task difficulty**
```sql
-- Did task complexity increase?
SELECT
  task_type,
  COUNT(*) as total_tasks,
  AVG(avg_annotation_time_sec) as avg_time,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY avg_annotation_time_sec) as p95_time
FROM annotation_tasks
WHERE assigned_to = 'sarah_a'
  AND created_at > NOW() - INTERVAL 7 DAYS
GROUP BY task_type;

-- Are tasks harder than usual?
```

### Remediation

**Immediate (0-10 min): Stop Sarah's work**
```python
# Pause Sarah's task queue
update_annotator_status(annotator_id='sarah_a', status='paused', reason='Quality review')

# Redistribute her pending tasks to John and Maria
reassign_tasks(from_annotator='sarah_a', to_pool=['john_b', 'maria_c'])

# Notify her manager
notify_manager("Sarah's annotations are below quality threshold; pausing work pending review")
```

**Short-term (10-30 min): Root cause investigation & retraining**
```bash
# 1. Interview Sarah about errors
Interviewer: "Looking at your recent work, I see some patterns. Can we discuss?"
Sarah: "I was rushed; I had a family emergency yesterday and wasn't focused."

# 2. Review task instructions
- Task definition seems clear (show examples)
- Sarah may have misunderstood "complete entity spans" requirement

# 3. Retrain on problematic tasks
- Show 10 examples of correct entity spans vs. incorrect
- Sarah re-annotates 5 examples with feedback
- Validate she can achieve 95%+ before returning to work
```

**Root cause remediation (30 min - 2 hours):**

1. **Improve task clarity:**
   ```
   Task Definition (Before):
   "Mark entity spans for all person names in the text"

   Task Definition (After):
   "Mark entity spans for all person FULL NAMES (first + last).
    Example: 'John Smith' → mark entire span
    Counter-example: 'John' alone → don't mark (incomplete)"
   ```

2. **Add annotator fatigue detection:**
   ```python
   def detect_annotator_fatigue(annotator_id, last_n_tasks=50):
       recent_tasks = get_recent_tasks(annotator_id, last_n_tasks)

       # Check for error clustering at end of day
       first_half_errors = sum(is_error(t) for t in recent_tasks[:25])
       second_half_errors = sum(is_error(t) for t in recent_tasks[25:])

       if second_half_errors > first_half_errors * 1.5:
           alert.warn(f"Annotator fatigue detected for {annotator_id}")
           recommend_break()
   ```

3. **Implement per-annotator quality dashboards:**
   ```python
   # Show each annotator their IRA score + feedback
   dashboard.annotator_quality[annotator_id] = {
       'ira_score': 0.96,
       'recent_errors': 2,
       'trend': 'improving',
       'feedback': 'Keep up the good work! Your spans are accurate.'
   }
   ```

4. **Automated quality alerts:**
   ```python
   def continuous_quality_monitoring():
       # Every 50 annotations, spot-check against gold standard
       recent_50 = get_recent_annotations(annotator_id, 50)
       sample_10 = random.sample(recent_50, 10)

       ira = calculate_ira(sample_10)
       if ira < 0.90:  # Below acceptable threshold
           alert.warn(f"Annotator {annotator_id} quality dipped to {ira}")
           notify_team_lead_for_feedback()
   ```

**Bring Sarah back online:**
```bash
# After retraining, validate she can hit 95%+
validation_tasks = select_random_examples(10)
sarah_annotations = sarah.annotate(validation_tasks)
validation_ira = calculate_ira(sarah_annotations)

if validation_ira >= 0.95:
    update_annotator_status(annotator_id='sarah_a', status='active')
    notify_sarah("You're back! Keep that great quality going.")
else:
    notify_manager("Sarah needs additional training; not yet ready to resume.")
```

### Communication Template

**Internal (Slack #incidents)**
```
AI DATA OPS INCIDENT: Label Quality Collapse
Severity: P2 (Training Data Quality Impact)
Duration: Week of Mar 10-16; detected in QA audit on Mar 16
Affected: Team C, specifically 1 annotator (Sarah), 77 incorrect labels

Root Cause: Annotator fatigue + task definition ambiguity on entity spans.

Actions:
- Paused Sarah's task queue pending retraining
- Clarified entity span task definition
- Implemented continuous quality monitoring (spot-checks every 50 annotations)
- Retrained Sarah on problematic annotation patterns

Resolution: Sarah validated on 10 test examples, back to work by 14:00 UTC.

ETA: Team C returns to 95%+ agreement by end of week (after all retraining)
Assigned to: [QA_LEAD], [TEAM_LEAD_C]
```

**Team Lead (Private message to Sarah)**
```
Hi Sarah,

We noticed a dip in your annotation quality this week (78% vs. 95% target). No worries—this happens! Let's work through it.

I'm pausing your work queue so you can focus on retraining. I'll send you 10 examples showing correct/incorrect entity spans.

Once you hit 95% on those examples, you're back to normal work. Estimated time: 30 min.

Let me know if you have questions about the task definition. Sometimes it's just a clarity issue.

You've been doing great overall—let's get back on track!
```

### Postmortem Questions
1. Why wasn't fatigue detected earlier (at 80% IRA, not 78%)?
2. Can we implement real-time quality feedback (not just weekly audits)?
3. Should we auto-pause annotators if quality drops mid-week?

---

## Incident 3: Model Drift / Active Learning Loop Failure

### Context
On March 14, the model retraining job runs as scheduled. New model v2.6 is trained and deployed. However, the model's prediction accuracy actually drops (from 91% to 87%). The active learning loop is suggesting uncertain predictions from the new model, but the model is systematically wrong on certain classes. Annotators are labeling bad predictions, which further degrades model quality in a negative feedback loop.

### Detection
- **Alert:** Model accuracy drops >2% after retraining OR confidence distribution changes significantly
- **Symptoms:**
  - Baseline validation accuracy: 91% → 87% (4% drop)
  - Confusion matrix shows new model has high false positive rate on "negative" class
  - Active learning is flagging low-confidence predictions, but many are actually high-confidence wrong predictions

### Diagnosis (30 minutes)

**Step 1: Validate the drop**
```python
# Compare model versions on same test set
test_set = load_test_set()

v2_5_predictions = model_v2_5.predict(test_set)
v2_6_predictions = model_v2_6.predict(test_set)

accuracy_v2_5 = calculate_accuracy(v2_5_predictions, test_set.labels)  # 91%
accuracy_v2_6 = calculate_accuracy(v2_6_predictions, test_set.labels)  # 87%

# Analyze where v2.6 fails
print(confusion_matrix(test_set.labels, v2_6_predictions))
# Result: v2.6 is overfitting to "positive" class; many "negative" mislabeled as "positive"
```

**Step 2: Identify training data change**
```sql
-- Did training data distribution change?
SELECT
  class_label,
  COUNT(*) as count_this_week,
  LAG(COUNT(*)) OVER (PARTITION BY class_label ORDER BY week) as count_last_week
FROM annotations
WHERE created_at >= NOW() - INTERVAL 2 WEEKS
GROUP BY week, class_label;

-- Result:
-- "positive": 3,000 this week, 2,000 last week (50% increase)
-- "negative": 1,800 this week, 2,000 last week (10% decrease)
-- class distribution shifted! Model overtrained on "positive"
```

**Step 3: Check for label quality issues**
```sql
-- Are recent "positive" labels low quality?
SELECT
  class_label,
  AVG(ira_score) as avg_ira,
  COUNT(*) as total_annotations
FROM annotations
WHERE created_at >= NOW() - INTERVAL 7 DAYS
GROUP BY class_label;

-- Result:
-- "positive": 0.88 IRA (LOW - labels disagree with gold standard)
-- "negative": 0.96 IRA (NORMAL)
-- Recent "positive" labels are lower quality!
```

### Remediation

**Immediate (0-10 min): Rollback to previous model**
```bash
# Rollback v2.6 → v2.5 (known good version)
kubectl set image deployment/model-inference \
  model-inference=model-inference:v2.5 \
  --record

# Verify accuracy returned
python -c "
import model_inference
acc = model_inference.test_accuracy()
print(f'Accuracy after rollback: {acc}')  # Should be 91%
"

# Expected: 91% accuracy restored within 30 seconds
```

**Short-term (10-30 min): Investigate class imbalance**
```python
# Identify why "positive" class distribution changed
recent_annotations = get_annotations(since=7_days_ago)
positive_annotations = [a for a in recent_annotations if a.label == 'positive']

print(f"Positive annotations this week: {len(positive_annotations)}")
print(f"Average IRA for positive: {mean([a.ira_score for a in positive_annotations])}")

# Check if one annotator introduced low-quality labels
by_annotator = group_by_annotator(positive_annotations)
for annotator, annotations in by_annotator.items():
    ira = mean([a.ira_score for a in annotations])
    if ira < 0.9:
        print(f"⚠️  {annotator}: Low IRA on positive ({ira})")
```

**Root cause remediation (1-2 hours):**

1. **Implement rebalancing in training data:**
   ```python
   # Don't train on raw annotation distribution
   # Ensure balanced classes
   training_data = load_annotations(since=30_days_ago)

   # Resample to balanced distribution
   positive = [a for a in training_data if a.label == 'positive']
   negative = [a for a in training_data if a.label == 'negative']

   min_count = min(len(positive), len(negative))
   balanced_data = positive[:min_count] + negative[:min_count]

   model = train(balanced_data)
   ```

2. **Add model quality gates before deployment:**
   ```python
   def can_deploy_model(new_model, baseline_model, test_set):
       new_accuracy = new_model.evaluate(test_set)
       baseline_accuracy = baseline_model.evaluate(test_set)

       # Don't deploy if accuracy drops >1%
       if new_accuracy < baseline_accuracy - 0.01:
           return False, f"Accuracy dropped {baseline_accuracy} → {new_accuracy}"

       # Check per-class accuracy too
       for class_label in test_set.classes:
           class_test = test_set[test_set.label == class_label]
           new_class_acc = new_model.evaluate(class_test)
           baseline_class_acc = baseline_model.evaluate(class_test)
           if new_class_acc < baseline_class_acc - 0.02:
               return False, f"{class_label} accuracy dropped"

       return True, "All gates passed"
   ```

3. **Validate recently-trained-on "positive" labels:**
   ```python
   # Flag low-quality positive labels for re-review
   low_quality = [a for a in recent_positive_annotations if a.ira_score < 0.9]

   # Send to QA for manual review
   for annotation in low_quality:
       flag_for_review(annotation, reason="Low IRA; needs validation")

   # Remove low-quality labels from training set
   training_data = remove_annotations(training_data, low_quality)
   ```

4. **Retrain with quality filtering:**
   ```bash
   # Retrain v2.7 with balanced, high-quality data only
   python -m model.train \
     --data training_data_balanced_ira_gt_0.92.csv \
     --output model_v2.7 \
     --test_on test_set.csv \
     --require_accuracy_improvement 0.005  # Must improve by at least 0.5%

   # Validate v2.7 meets gates before deploying
   ```

5. **Monitor for future drift:**
   ```python
   def continuous_model_validation():
       # Every day, check if baseline accuracy is maintained
       new_test_sample = sample_recent_predictions(yesterday)
       current_accuracy = model.evaluate(new_test_sample)
       baseline = 0.91

       if current_accuracy < baseline - 0.02:
           alert.error(f"Model drift detected: {current_accuracy}")
           recommend_retraining()
   ```

### Communication Template

**Internal (Slack #incidents)**
```
AI DATA OPS INCIDENT: Model Drift / Training Data Quality
Severity: P2 (Model Quality Degradation)
Duration: Model v2.6 deployed Mar 14 09:00; detected/rolled back Mar 14 14:30
Affected: Model inference accuracy dropped 91% → 87%

Root Cause: Recent "positive" class labels have low agreement with gold standard (88% vs. 96% for "negative"). Class imbalance in training data (50% more positive labels this week) caused model to overfit to low-quality positive class.

Actions:
1. Rolled back to v2.5 (91% accuracy restored)
2. Identified low-IRA positive labels; flagged for re-review
3. Implemented balanced class sampling in training
4. Added model quality gates (accuracy + per-class validation)
5. Retraining v2.7 with filtered, balanced data

Resolution: v2.7 deployed by 16:00 UTC with accuracy validation.

ETA: Fully resolved by 16:30 UTC
Assigned to: [ML_ENGINEER], [QA_LEAD]
```

**Team Notification**
```
Model Update Rollback

We detected that today's model update (v2.6) degraded accuracy. We've rolled back to the previous version (v2.5) while investigating.

We found that recent training data had an imbalance in class distribution and some labels with lower quality. We're retraining with better data and will deploy v2.7 with additional quality checks.

Thank you for alerting us to any accuracy issues you notice!
```

### Postmortem Questions
1. Why wasn't model quality validated before deployment?
2. Can we detect class imbalance automatically before training?
3. Should we require human review of model changes before deployment?

---

## General Escalation Path
1. **P3 (UI/UX issue, <5 annotators):** Assign to engineer; investigate
2. **P2 (Quality or throughput impact, >10 annotators):** Escalate to ops manager + engineering lead within 15 min
3. **P1 (Model drift, widespread quality collapse):** Page ML lead + product within 5 min
4. **All quality-related incidents:** Require postmortem + preventive control (automated gates, monitoring)

