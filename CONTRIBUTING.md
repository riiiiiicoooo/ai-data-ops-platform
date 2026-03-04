# Contributing to AI Data Operations Platform

This guide covers how to:
1. Set up your development environment
2. Add a new annotation type
3. Extend quality metrics
4. Follow code style conventions
5. Write and run tests
6. Submit pull requests

## Development Environment Setup

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL client tools (psql)
- Git

### Quick Start

```bash
# Clone the repository
git clone <repo-url>
cd ai-data-ops-platform

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install pre-commit hooks
pre-commit install

# Start infrastructure
docker-compose up -d

# Run tests
make test

# Run the demo
make demo
```

### Using Docker Compose

The `docker-compose.yml` provides:
- PostgreSQL 15 with pgvector (for embeddings)
- Redis 7 (for task queue)
- Temporal server (for workflow orchestration)
- FastAPI app service
- Optional: pgAdmin and Grafana for development

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f app

# Run tests in container
docker-compose exec app python -m pytest tests/

# Stop services
docker-compose down
```

### Environment Configuration

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
# Edit .env with your configuration
```

Key settings:
- `ENVIRONMENT`: development, staging, or production
- `LOG_LEVEL`: debug, info, warning, error
- `DB_*`: PostgreSQL connection parameters
- `REDIS_*`: Redis connection parameters
- `TEMPORAL_*`: Temporal server settings

## Adding a New Annotation Type

### Scenario: Add "Semantic Similarity" Metric for Text Pairs

This walkthrough shows how to extend the platform with a new annotation type.

### Step 1: Define the Annotation Schema

```python
# src/task_engine/schema_registry.py

# In INDUSTRY_PRESETS, add:
"semantic_similarity": {
    "input_type": InputType.TEXT_PAIR,
    "input_schema": {
        "text_a": {"type": "text", "display": "left_panel"},
        "text_b": {"type": "text", "display": "right_panel"},
    },
    "output_fields": [
        OutputField(
            name="similarity_score",
            field_type=OutputFieldType.INTEGER,
            values=[],  # Allow any integer
            min_value=1,
            max_value=5,
            required=True,
        ),
        OutputField(
            name="explanation",
            field_type=OutputFieldType.TEXT,
            max_length=200,
            required=False,
        ),
    ],
    "validation_rules": [
        ValidationRule(
            rule_id="similarity_bounds",
            condition="similarity_score >= 1 and similarity_score <= 5",
            requirement="true",
            error_message="Similarity must be 1-5",
        ),
    ],
    "ui_config": {
        "layout": "side_by_side",
        "enable_copy": True,
    },
}
```

### Step 2: Implement the Agreement Metric

```python
# src/quality/agreement_calculator.py

def semantic_similarity_correlation(
    self,
    scores_a: list[int],
    scores_b: list[int],
) -> AgreementScore:
    """
    Spearman correlation for semantic similarity scores.

    Scores are ordinal (1-5) rather than categorical,
    so correlation is appropriate.
    """
    if len(scores_a) != len(scores_b) or len(scores_a) < 2:
        return AgreementScore("correlation", 0.0, "poor", 2, len(scores_a), {})

    # Compute Spearman rank correlation
    from scipy.stats import spearmanr
    correlation, pvalue = spearmanr(scores_a, scores_b)

    # Clamp to 0-1 range
    correlation = max(0, correlation)

    return AgreementScore(
        metric="spearman_correlation",
        score=round(correlation, 4),
        interpretation=self.interpret(correlation),
        n_annotators=2,
        n_items=len(scores_a),
        details={
            "pvalue": round(pvalue, 4),
            "significant": pvalue < 0.05,
        },
    )

# Add to OUTPUT_TYPE_TO_METRIC mapping:
OUTPUT_TYPE_TO_METRIC = {
    ...
    # Integer scores use ordinal correlation
    OutputFieldType.INTEGER: AgreementMetric.SPEARMAN_CORRELATION,
}
```

### Step 3: Add Tests

```python
# tests/test_agreement_calculator.py

class TestSemanticSimilarity:
    """Semantic similarity agreement tests."""

    def test_perfect_correlation(self):
        """Identical scores yield perfect correlation."""
        calc = AgreementCalculator()
        scores_a = [1, 2, 3, 4, 5]
        scores_b = [1, 2, 3, 4, 5]

        result = calc.semantic_similarity_correlation(scores_a, scores_b)

        assert result.score == 1.0
        assert result.interpretation == "strong"

    def test_inverse_correlation(self):
        """Reverse order yields negative correlation."""
        calc = AgreementCalculator()
        scores_a = [1, 2, 3, 4, 5]
        scores_b = [5, 4, 3, 2, 1]

        result = calc.semantic_similarity_correlation(scores_a, scores_b)

        assert result.score <= 0.0
```

### Step 4: Auto-select for New Type

```python
# Update compute_agreement() method:
def compute_agreement(
    self,
    annotation_type: str,
    annotations: list[Any],
) -> AgreementScore:
    ...
    elif annotation_type in ("semantic_similarity", "ordinal_scores"):
        if len(annotations) >= 2:
            return self.semantic_similarity_correlation(
                annotations[0],
                annotations[1]
            )
    ...
```

### Step 5: Use in Task Routing

```python
# Annotators can now create tasks with this schema:
registry = SchemaRegistry()
schema = registry.create_from_preset(
    org_id,
    "semantic_similarity",
    user_id
)

# Agreement metric is auto-selected
assert schema.primary_metric == AgreementMetric.SPEARMAN_CORRELATION
```

### Checklist for New Annotation Types

- [ ] Schema defined in `SchemaRegistry.INDUSTRY_PRESETS`
- [ ] Agreement metric implemented in `AgreementCalculator`
- [ ] Metric added to `OUTPUT_TYPE_TO_METRIC` mapping
- [ ] `compute_agreement()` updated with new type handling
- [ ] Comprehensive tests in `test_agreement_calculator.py`
- [ ] Example in docstring or demo
- [ ] Updated CONTRIBUTING.md with walkthrough

## Extending Quality Metrics

### Adding a New Agreement Metric

Example: Adding Gwet's AC2 (alternative to kappa for skewed distributions)

```python
# src/quality/agreement_calculator.py

def gwets_ac2(
    self,
    annotations_a: list[str],
    annotations_b: list[str],
) -> AgreementScore:
    """
    Gwet's AC2 coefficient.

    More robust than kappa when category distributions
    are highly skewed (e.g., 95% negative, 5% positive).

    AC2 = (observed_agreement - expected_agreement) / (1 - expected_agreement)
    where expected_agreement is computed differently than kappa.
    """
    if len(annotations_a) != len(annotations_b):
        raise ValueError("Annotations must be equal length")

    n = len(annotations_a)
    if n == 0:
        return AgreementScore("gwets_ac2", 0.0, "poor", 2, 0, {})

    # Observed agreement
    agree_count = sum(1 for a, b in zip(annotations_a, annotations_b) if a == b)
    observed = agree_count / n

    # Expected agreement (Gwet's method)
    all_labels = set(annotations_a) | set(annotations_b)
    expected = 0.0
    for label in all_labels:
        # Proportion of annotation 1 in category + annotation 2 in category / 2
        pa = sum(1 for x in annotations_a if x == label) / n
        pb = sum(1 for x in annotations_b if x == label) / n
        p = (pa + pb) / 2
        expected += p * (1 - p)
    expected = expected * 2 / (n - 1) if n > 1 else 0

    # AC2
    if expected == 1.0:
        ac2 = 1.0
    else:
        ac2 = (observed - expected) / (1 - expected)

    ac2 = max(-1.0, min(1.0, ac2))

    return AgreementScore(
        metric="gwets_ac2",
        score=round(ac2, 4),
        interpretation=self.interpret(ac2),
        n_annotators=2,
        n_items=n,
        details={
            "observed_agreement": round(observed, 4),
            "expected_agreement": round(expected, 4),
        },
    )
```

### Updating Consensus Strategies

Add a new consensus resolution method:

```python
# src/annotation/consensus_resolver.py

class ConsensusMethod(Enum):
    MAJORITY_VOTE = "majority_vote"
    WEIGHTED_VOTE = "weighted_vote"
    EXPERT_TIEBREAK = "expert_tiebreak"
    CONFIDENCE_WEIGHTED = "confidence_weighted"  # NEW

def _confidence_weighted_vote(
    self,
    votes: list[AnnotatorVote],
    label_field: str,
    min_agreement: float,
) -> ConsensusResult:
    """
    Votes weighted by annotator confidence rather than accuracy.

    Useful when accuracy baseline isn't established yet,
    but annotators report their own confidence.
    """
    labels = self._extract_labels(votes, label_field)

    if not labels:
        return self._no_consensus_result(votes, "no_extractable_labels")

    # Weight by confidence scores from annotation data
    label_weights: dict[str, float] = {}
    for i, label in enumerate(labels):
        confidence = votes[i].annotation_data.get("confidence_score", 0.5)
        if label not in label_weights:
            label_weights[label] = 0.0
        label_weights[label] += confidence

    # Rest of implementation...
    ...
```

### Testing New Metrics

```python
# tests/test_agreement_calculator.py

def test_gwets_ac2_robustness(self):
    """Gwet's AC2 should be more robust for skewed distributions."""
    calc = AgreementCalculator()

    # 95% negative, 5% positive
    ann_a = ["negative"] * 95 + ["positive"] * 5
    ann_b = ["negative"] * 93 + ["positive"] * 7  # 2 disagreements

    kappa_result = calc.cohens_kappa(ann_a, ann_b)
    ac2_result = calc.gwets_ac2(ann_a, ann_b)

    # AC2 should be higher (more robust to skew)
    assert ac2_result.score > kappa_result.score
```

## Code Style and Conventions

### Python Style

- Follow PEP 8
- Use type hints throughout
- Max line length: 100 characters
- Use dataclasses for domain objects

```python
# Good
from dataclasses import dataclass
from typing import Optional

@dataclass
class AnnotatorVote:
    annotator_id: UUID
    annotation_data: dict[str, Any]
    accuracy_score: float = 0.5

# Bad
class AnnotatorVote:
    def __init__(self, annotator_id, annotation_data, accuracy_score=0.5):
        self.annotator_id = annotator_id
        ...
```

### Naming Conventions

- Classes: `PascalCase` (e.g., `AgreementCalculator`)
- Functions/methods: `snake_case` (e.g., `compute_agreement`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `MIN_AGREEMENT_QUALITY`)
- Private methods: prefix with `_` (e.g., `_extract_labels`)

### Documentation

```python
def compute_agreement(
    self,
    annotation_type: str,
    annotations: list[Any],
) -> AgreementScore:
    """
    Auto-select and compute agreement metric.

    Args:
        annotation_type: Type of annotation (classification, ner, bbox, etc.)
        annotations: List of annotation sets from annotators

    Returns:
        AgreementScore with metric, score, and interpretation

    Raises:
        ValueError: If annotation_type is unsupported

    Example:
        >>> calc = AgreementCalculator()
        >>> result = calc.compute_agreement(
        ...     "classification",
        ...     [["fraud", "legit"], ["fraud", "fraud"]]
        ... )
        >>> print(result.score)
        0.5
    """
```

## Testing Requirements

### Test Coverage

- All new code must have tests
- Target: > 85% code coverage
- Use pytest framework

### Running Tests

```bash
# Run all tests
make test

# Run specific test file
pytest tests/test_agreement_calculator.py -v

# Run with coverage
pytest --cov=src tests/

# Run tests in Docker
docker-compose exec app pytest tests/ -v
```

### Test Naming

```python
class TestAgreementCalculator:  # Test class per module
    def test_perfect_agreement(self):  # Descriptive test names
        """Test docstring explains scenario."""
        ...

    def test_edge_case_empty_input(self):  # Edge cases explicit
        ...
```

### Example Test Pattern

```python
def test_weighted_vote_accuracy_advantage(self):
    """Expert's vote should outweigh two lower-accuracy annotators."""
    resolver = ConsensusResolver()

    # ARRANGE: Set up test data
    votes = [
        AnnotatorVote(uuid4(), {"label": "fraud"}, accuracy_score=0.97),
        AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.78),
        AnnotatorVote(uuid4(), {"label": "legit"}, accuracy_score=0.75),
    ]

    # ACT: Execute test
    result = resolver.resolve(votes, ConsensusMethod.WEIGHTED_VOTE)

    # ASSERT: Verify expectations
    assert result.passed_quality
    assert result.resolved_annotation["label"] == "fraud"
```

## Pull Request Process

### Before Submitting

1. **Code changes**
   ```bash
   # Format code
   make lint

   # Run tests
   make test

   # Check coverage
   pytest --cov=src --cov-report=term-missing tests/
   ```

2. **Documentation**
   - Update docstrings for changed functions
   - Update README.md if user-facing changes
   - Add example in CONTRIBUTING.md if extending functionality

3. **Commits**
   ```bash
   # Use semantic commit messages
   git commit -m "feat: add semantic similarity metric"
   git commit -m "fix: handle missing data in Krippendorff's alpha"
   git commit -m "test: add coverage for consensus resolution"
   git commit -m "docs: update schema registry example"
   ```

### Submission Template

```markdown
## Description
Brief summary of changes

## Type of Change
- [ ] New feature
- [ ] Bug fix
- [ ] Improvement
- [ ] Breaking change

## Changes
- List specific changes
- One per line

## Testing
- [ ] Tests pass: `make test`
- [ ] Coverage > 85%: `pytest --cov=src`
- [ ] Demo runs: `make demo`

## Related Issues
Fixes #<issue-number>

## Notes
Any additional context
```

## Common Tasks

### Make Targets

```bash
make help          # Show all targets
make setup         # Install dependencies
make test          # Run test suite
make lint          # Format and check code
make demo          # Run demo pipeline
make docker-up     # Start Docker services
make docker-down   # Stop Docker services
make clean         # Remove build artifacts
```

### Database Management

```bash
# Connect to database
psql -h localhost -U dataops -d annotation_db

# Run migrations (once implemented)
alembic upgrade head

# Check schema
\dt  # Show tables
\d annotations  # Describe table
```

### Debugging

```python
# Add debug output
import logging
logger = logging.getLogger(__name__)
logger.debug(f"Agreement score: {result.score}")

# Enable debug logging
export LOG_LEVEL=debug
python your_script.py

# Use pdb debugger
import pdb; pdb.set_trace()
```

## Getting Help

- **Questions**: Open a GitHub discussion
- **Bugs**: Create an issue with reproduction steps
- **Features**: Start a discussion before implementing
- **Code review**: Tag maintainers in your PR

## Standards and References

- **Agreement Metrics**:
  - Landis & Koch interpretation scale
  - Krippendorff, K. (2011). *Computing Krippendorff's Alpha*

- **Quality Frameworks**:
  - ISO 19115 metadata quality
  - NIST framework for evaluation

- **Consensus Resolution**:
  - DEC-004: Weighted vote backtest (91% vs 86%)

- **Python**:
  - PEP 8 style guide
  - Type hints (PEP 484)
  - Dataclasses (PEP 557)

---

Thank you for contributing! Your improvements make the platform better for everyone.
