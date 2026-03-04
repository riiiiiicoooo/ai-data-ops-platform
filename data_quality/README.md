# AI Data Ops Platform - Great Expectations Data Quality

Data quality validation framework for annotation pipelines and ML training data. Ensures data meets quality standards before ingestion into production models.

## Overview

This Great Expectations project validates:
- **Annotation Data**: Annotator submissions, confidence scores, agreement levels
- **Training Data**: Feature vectors, labels, class balance, data splits

## Files

- **great_expectations.yml**: Project configuration (Snowflake datasource)
- **expectations/annotation_quality_suite.json**: Annotation data quality rules
- **expectations/model_training_data_suite.json**: Training data quality rules
- **checkpoints/daily_quality_check.yml**: Scheduled validation checkpoint

## Setup

### 1. Initialize Great Expectations Project

```bash
cd /path/to/ai-data-ops-platform/data_quality
great_expectations init
```

### 2. Configure Snowflake Connection

Update `great_expectations.yml` with Snowflake credentials:

```bash
export SNOWFLAKE_USER="data_user"
export SNOWFLAKE_PASSWORD="secure_password"
export SNOWFLAKE_ACCOUNT="xy12345.us-east-1"
export SNOWFLAKE_WAREHOUSE="COMPUTE_WH"
```

### 3. Run Manual Validation

```bash
# Validate annotation data
great_expectations checkpoint run daily_quality_check --datasource snowflake_datasource

# View results
great_expectations data-docs build
open uncommitted/data_docs/local_site/index.html
```

## Expectation Suites

### Annotation Quality Suite

Validates annotation task data with checks for:
- **Required Columns**: task_id, annotator_id, annotation_value, confidence_score, etc.
- **Non-null Constraints**: Critical fields must always have values
- **Value Ranges**: confidence_score (0-1), agreement_score (0-1)
- **Status Validation**: annotation_status in [pending, completed, reviewed, rejected]
- **Time Ordering**: completed_at > created_at
- **Quality Metrics**: Mean inter-annotator agreement >= 60%
- **Format Validation**: task_id format (TASK-XXXXXX)

#### Key Metrics

- **confidence_score**: Annotator confidence in submission (0=no confidence, 1=100% confident)
  - Alert if mean < 0.6 (indicates low confidence in annotations)
- **agreement_score**: Inter-annotator agreement on same task
  - Alert if mean < 0.6 (indicates inconsistent task or poor training)
- **annotation_status**: Workflow state (pending → completed → reviewed → [accepted/rejected])

### Model Training Data Suite

Validates training dataset with checks for:
- **Required Columns**: sample_id, feature_vector, label, split, quality_score
- **Schema Validation**: Expected feature columns present
- **Uniqueness**: No duplicate sample_id values
- **Label Validation**: No null labels, values in expected set
- **Class Balance**: Label distribution appropriate for task
- **Data Quality**: Quality scores between 0-1, mean >= 70%
- **Split Distribution**: Samples properly partitioned (train/validation/test)

#### Key Metrics

- **label**: Target variable (classification categories)
  - Alert if all unique (not class imbalance issue)
  - Alert if < 1% unique (too few classes)
- **data_quality_score**: Overall sample quality
  - Alert if mean < 0.7 (70% threshold)
- **split**: Train/validation/test partition
  - Ensures proper separation for unbiased model evaluation

## Running Validations

### Manual Validation

```bash
# Validate single suite
great_expectations checkpoint run daily_quality_check

# Validate with custom batch request
great_expectations validation --suite annotation_quality_suite \
  --datasource snowflake_datasource \
  --data_asset annotation_tasks

# View validation results
great_expectations docs build
```

### Automated Scheduling

The checkpoint includes cron scheduling (2 AM UTC daily):

```bash
# Run via airflow, cron, or task scheduler:
great_expectations checkpoint run daily_quality_check
```

### Python API

```python
from great_expectations import load_context

context = load_context(context_root_dir="/path/to/data_quality")

# Run checkpoint programmatically
checkpoint_run_result = context.run_checkpoint(checkpoint_name="daily_quality_check")

# Check results
for validation_result in checkpoint_run_result["validation_results"]:
    if not validation_result.success:
        print(f"Validation failed: {validation_result}")
        # Alert or trigger remediation
```

## Integration with Data Pipeline

### Before Model Training

```python
from great_expectations import load_context

def validate_before_training():
    context = load_context(context_root_dir="./data_quality")
    result = context.run_checkpoint(checkpoint_name="daily_quality_check")
    
    if not result["success"]:
        raise ValueError("Data quality validation failed - cannot proceed with training")
    
    return result

# In training pipeline:
if validate_before_training():
    model.fit(training_data)
```

### Real-time Validation

```python
# Validate new annotation submissions
def validate_annotation_submission(task_id: str, annotation: dict):
    context = load_context()
    
    # Run specific expectation
    batch_request = {
        "datasource_name": "snowflake_datasource",
        "data_connector_name": "annotation_tasks_connector",
        "data_asset_name": "annotation_tasks",
        "batch_filter_parameters": {"task_id": task_id},
    }
    
    result = context.validate(
        expectation_suite_name="annotation_quality_suite",
        batch_request=batch_request,
    )
    
    return result.success
```

## Monitoring & Alerts

### Slack Notifications

Failed validations trigger Slack alerts (via Slack webhook):
- Channel: #data-quality-alerts
- Content: Validation results, failed expectations, remediation suggestions

### Data Docs

Auto-generated documentation:
- Index of all expectations and data assets
- Validation history and trends
- Data quality scorecards per asset

View at: `uncommitted/data_docs/local_site/index.html`

## Troubleshooting

### Connection Issues

```bash
# Test Snowflake connection
great_expectations datasource list
great_expectations datasource test --datasource snowflake_datasource
```

### Expectation Failures

1. View detailed failure info: `great_expectations validation --suite annotation_quality_suite`
2. Check data in Snowflake: `SELECT * FROM annotation_tasks LIMIT 100`
3. Adjust expectations if data legitimately changed

### Performance

For large tables, add time-based filtering to checkpoint:

```yaml
batch_request:
  batch_filter_parameters:
    timestamp_column: created_at
    lookback_days: 1  # Only validate yesterday's data
```

## References

- [Great Expectations Documentation](https://docs.greatexpectations.io/)
- [Expectation Gallery](https://greatexpectations.io/expectations/)
- [Snowflake Integration](https://docs.greatexpectations.io/docs/guides/setup_a_datasource/configure_a_datasource/)
