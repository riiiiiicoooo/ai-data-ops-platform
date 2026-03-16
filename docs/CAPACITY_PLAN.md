# AI Data Ops Platform - Capacity Plan

## Executive Summary
AI Data Ops Platform is a annotation system with active learning feedback. This plan quantifies infrastructure, annotation team, and computing resources for current state, 2x growth, and 10x growth scenarios.

---

## Current State (Q1 2026)

### Usage Metrics
- **Active Annotators:** 12 FTE (3 teams)
- **Daily Annotations:** 2,340 examples/team/day × 3 teams = 7,020 examples/day
- **Examples/Month:** ~210,600 (for 5-day weeks)
- **Model Retraining Frequency:** Daily
- **Inter-Rater Agreement Sample:** 5% of daily work (~350 examples/week)

### Annotation Team & Cost
| Role | Count | Cost/Month |
|------|-------|-----------|
| **Senior Annotators** (QA) | 2 | $8,000 |
| **Annotators** | 8 | $24,000 |
| **Team Leads** | 2 | $8,000 |
| **Annotation Mgmt Tools** | - | $2,000 |
| **Total Monthly** | | **$42,000** |

### Infrastructure
| Component | Current | Monthly Cost |
|-----------|---------|--------------|
| **Annotation UI Servers** | 2 × t3.large (application) | $288 |
| **Database (PostgreSQL)** | db.r5.xlarge (4 vCPU, 32 GB) | $2,800 |
| **Model Training (GPU)** | 2 × p3.2xlarge (daily retraining) | $5,600 |
| **Object Storage (examples)** | 500 GB | $11.50 |
| **Cache (active learning queue)** | 3 GB Redis | $270 |
| **Monitoring/Logging** | CloudWatch + DataDog | $400 |
| **Total Infrastructure** | | **$9,370** |
| **Total Team + Infrastructure** | | **$51,370/month** |

### Workflow Capacity
- **Per-Annotator Daily Capacity:** 780 examples/day (260 work hours/year ÷ 12 annotators × 21 working days/month)
- **Per-Team Capacity:** 2,340 examples/day (3 annotators × 780)
- **Annual Capacity:** ~7.56M examples (3 teams × 252 working days)

### Database Sizing
- **Annotation Records:** 210K examples/month × 12 months = 2.52M rows
- **Metadata (features, labels, confidence):** 500 MB/month
- **Daily Ingestion:** 7,020 examples × 10 KB metadata = 70 MB
- **Storage Retention:** 2-year history (rolling 24-month window)

---

## 2x Growth Scenario (12 months forward)
**Assumption:** 24 annotators (6 teams), 14,040 examples/day, daily model retraining

### What Breaks First
1. **Annotation Team Scaling:** Managing 6 teams requires coordination overhead; requires annotation operations manager
2. **Database Query Latency:** Active learning queries (find uncertain predictions) become slow with 4.2M examples
3. **Model Training Throughput:** 14K examples/day exceeds daily retraining window (requires parallel GPU training)
4. **UI Responsiveness:** Database hits per annotation task increase; UI latency creeps above 1s SLA

### Required Infrastructure Changes
| Component | Current → 2x | Incremental Cost |
|-----------|--------------|-----------------|
| **Annotation UI Servers** | 2 × t3.large → 4 × t3.xlarge + ASG | +$576/month |
| **Database** | r5.xlarge → r6i.2xlarge + 1 read replica | +$3,200/month |
| **Model Training** | 2 × p3.2xlarge → 4 × p3.2xlarge (parallel jobs) | +$5,600/month |
| **Active Learning Cache** | 3 GB Redis → 10 GB Redis Cluster | +$450/month |
| **Object Storage** | 500 GB → 1 TB | +$11.50/month |
| **Monitoring** | DataDog scaling | +$200/month |
| **Total Infrastructure @ 2x** | | **$19,638/month** (+110%) |

### Annotation Team Scaling
| Role | Current → 2x | Cost |
|------|---|---|
| **Annotation Operations Manager** | 0 → 1 FTE | +$6,000/month |
| **Senior Annotators (QA)** | 2 → 4 | +$8,000/month |
| **Annotators** | 8 → 16 | +$24,000/month |
| **Team Leads** | 2 → 4 | +$8,000/month |
| **Total @ 2x** | | **$46,000/month additional** |

**Total Cost @ 2x Scale:** $51.4K infrastructure + $88K annotation team = **$139,400/month** (+171% from current)

### Bottleneck Resolution @ 2x

**Database Query Optimization:**
- Current: Query all 2.5M examples to find uncertain predictions (takes 30s)
- Solution: Add index on (model_version, confidence_score); batch query to top 10K uncertain examples
- Expected: Query latency from 30s → 500ms

**Model Training Parallelization:**
- Current: Single GPU trains on 7K examples/day (takes 2 hours, blocks next day's retraining)
- Solution: Parallel GPU training; split examples into 4 GPUs (1 example per GPU, asynchronous)
- Expected: Training time from 2 hours → 30 minutes; enables continuous retraining

---

## 10x Growth Scenario (24 months forward)
**Assumption:** 120 annotators (25 teams), 70K examples/day, continuous model retraining

### What Breaks First
1. **Annotation Team Management:** 120 annotators require distributed teams; need regional annotation centers
2. **Model Training Infrastructure:** 70K examples/day requires 24/7 training; single-model approach inadequate
3. **Data Warehouse:** Ad-hoc annotation queries are expensive; need data warehouse for analytics
4. **Quality Control:** Manual IRA sampling (5%) = 3,500 examples/week to audit; labor-intensive
5. **Active Learning Loop Latency:** End-to-end loop (annotate → train → predict → flag uncertain) >24 hours

### Required Infrastructure Changes
| Component | Current → 10x | Incremental Cost |
|-----------|--------------|-----------------|
| **Annotation UI** | 2 × t3.large → 20 × t3.xlarge + multi-region | +$2,880/month |
| **Database** | r5.xlarge → r6i.4xlarge + 8 read replicas + sharding (2 shards) | +$12,000/month |
| **Model Training** | 2 × p3.2xlarge → 20 × p3.8xlarge (continuous training) | +$33,600/month |
| **Data Warehouse** | 0 → BigQuery/Snowflake for annotation analytics | +$2,000/month |
| **Uncertainty Sampling** | Manual → Automated active learning pipeline (Kafka) | +$1,500/month |
| **Quality Assurance** | Manual sampling → Automated quality gates | +$1,000/month |
| **Object Storage** | 500 GB → 5 TB (10x examples + history) | +$100/month |
| **Monitoring** | DataDog Enterprise | +$1,500/month |
| **Total Infrastructure @ 10x** | | **$54,580/month** (+482%) |

### Annotation Team Scaling @ 10x
| Role | Current → 10x | Notes |
|---|---|---|
| **Head of Annotation Ops** | 0 → 1 FTE | Director-level; oversee 3 regional teams |
| **Regional Annotation Managers** | 0 → 3 FTE | Lead regional centers (US, EU, APAC) |
| **Team Leads** | 2 → 20 | 1 lead per 5-6 annotators |
| **Senior Annotators (QA)** | 2 → 15 | Quality control for each region |
| **Annotators** | 8 → 100 | Distributed across regions |
| **Data Labeling Ops** | 0 → 3 | Monitor quality, manage task distribution |
| **Total @ 10x** | | **~140 people** (Annotators + 15 Ops/Management) |
| **Total Cost** | | **$420K/month** (annotators + management) |

**Total Cost @ 10x Scale:** $54.6K infrastructure + $420K team = **$474,600/month** (+824% from current)

### Architectural Changes @ 10x

**Continuous Model Retraining:**
```
Current (Daily):
  14:00 - Batch collect 7K examples
  14:30 - Train model (2 hours)
  16:30 - Deploy new model

At 10x (Continuous):
  Examples stream in throughout day
  Mini-batch retraining every 30 minutes (1K examples per batch)
  Model versioning: v1 (batch 1), v2 (batch 2), etc.
  Deploy best-performing version daily
```

**Regional Annotation Distribution:**
```
Current (Centralized, US):
  1 annotation center
  12 annotators
  Simple queue system

At 10x (Distributed):
  US Center: 40 annotators (8 teams)
  EU Center: 35 annotators (7 teams)
  APAC Center: 25 annotators (5 teams)

  Shared uncertainty queue (Kafka)
  Examples routed by timezone for 24/7 annotation
  Regional quality auditing
```

**Automated Quality Gates:**
```
Current (Manual):
  5% of examples → Senior annotators re-annotate
  Weekly IRA metric computed

At 10x (Automated):
  Every annotation → Immediate quality check
  IRA model predicts if annotation quality is low
  Low-quality annotations sent to QA review
  Automatic feedback to annotators (gamification)
```

### Team Organization @ 10x
```
Director of Data Annotation
├── Manager, US Annotation Center
│   ├── 4 Team Leads (10 annotators each)
│   └── 2 QA Leads
├── Manager, EU Annotation Center
│   ├── 3-4 Team Leads
│   └── 2 QA Leads
├── Manager, APAC Annotation Center
│   ├── 2-3 Team Leads
│   └── 1-2 QA Leads
├── Head of Annotation Ops
│   ├── Data Analyst (quality metrics)
│   ├── Task Distribution Manager
│   └── Tool/Process Manager
└── ML Ops Engineer (active learning loop)
```

---

## Cost Optimization Timeline

### Phase 1: Current → 2x (Months 0-6)
1. **Database Indexing:** Add (model_version, confidence) index; reduces query latency by 50% (no cost)
2. **Batch Model Training:** Switch from single-job to 2-parallel-jobs; reduces training time by 40% ($0 initial, saves GPU hours)
3. **Annotation Tool UX:** Simplify UI to reduce per-example time from 3 min → 2.5 min (+5% throughput, no cost)

### Phase 2: 2x → 5x (Months 6-12)
1. **Automated Quality Sampling:** Replace manual 5% sampling with ML-based prediction (~50% reduction in QA effort)
2. **Active Learning Optimization:** Smart task assignment (send easy tasks to junior annotators, hard tasks to seniors) (+10% throughput)
3. **Reserved GPU Capacity:** Move to reserved instances for training (saves 30% GPU cost)

### Phase 3: 5x → 10x (Months 12-24)
1. **Regional Annotation Centers:** Distribute to US/EU/APAC for 24/7 coverage (enables continuous training)
2. **Continuous Retraining:** Move from daily batch → continuous mini-batch training (faster feedback loop, better models)
3. **Automated Quality Gates:** Implement ML-based quality prediction; redirect low-quality annotations to QA in real-time (enables scaling without proportional QA cost)

---

## Monitoring & Decision Gates

### Weekly Metrics
- Annotation throughput: Alert if <95% of 2,340/team-day
- Label quality IRA: Alert if <95% agreement
- UI latency p95: Alert if >1.5s
- Model training time: Alert if >3 hours per day

### Monthly Decision Gates
| Metric | Threshold | Action |
|--------|-----------|--------|
| Throughput | <95% capacity × 2 weeks | Investigate bottleneck; increase team or automate |
| Quality IRA | <93% × 2 weeks | Retrain problematic annotators; simplify task |
| Database latency | >2s for active learning query | Add index or read replica |
| Model drift | Accuracy drops >5% unexpectedly | Retrain or adjust model hyperparameters |
| Team utilization | >85% × 2 weeks | Hire additional annotators or reduce scope |

