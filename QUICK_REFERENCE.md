# AI Data Operations Platform - Quick Reference

## File Locations

### 1. Tests (59 test cases)
- `tests/__init__.py` - Test package initialization
- `tests/test_agreement_calculator.py` - 37 tests for all 7 agreement metrics
- `tests/test_consensus_resolver.py` - 22 tests for all resolution strategies

### 2. Docker Configuration
- `Dockerfile` - Multi-stage production build
- `docker-compose.yml` - 7 services (Postgres, Redis, Temporal, FastAPI, pgAdmin, Grafana)
- `.env.example` - Configuration template (copy to `.env`)

### 3. Documentation
- `README.md` - Updated with quick start, embedded diagrams, references
- `DEMO.md` - Complete walkthrough (8 steps, 450+ lines)
- `CONTRIBUTING.md` - Developer guide (600+ lines with examples)
- `IMPLEMENTATION_SUMMARY.md` - This implementation overview

### 4. Demo & Tools
- `demo/run_demo.py` - Executable end-to-end pipeline (335 lines)
- `requirements.txt` - 65 dependencies organized by category
- `Makefile` - 20+ development targets with color output

### 5. Architecture Diagrams (Mermaid format)
- `docs/architecture.mmd` - System architecture (89 lines)
- `docs/workflow_state_machine.mmd` - Annotation lifecycle (57 lines)
- `docs/quality_feedback_loop.mmd` - Model feedback integration (77 lines)

## Quick Commands

```bash
# Explore the code
python demo/run_demo.py

# Run all tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=src --cov-report=html

# Start development environment
make setup
make docker-up

# Run specific test file
pytest tests/test_agreement_calculator.py -v
pytest tests/test_consensus_resolver.py -v

# Check code quality
make lint
make format

# View all make targets
make help

# Stop services
make docker-down
```

## What Each File Does

### Tests
- **test_agreement_calculator.py**: Tests all 7 agreement metrics (kappa, alpha, IoU, BLEU, etc.)
- **test_consensus_resolver.py**: Tests all resolution strategies (majority, weighted, expert)

### Documentation
- **DEMO.md**: Step-by-step walkthrough of fraud detection annotation pipeline
- **CONTRIBUTING.md**: How to add new annotation types and extend metrics
- **README.md**: Project overview with embedded architecture diagrams
- **IMPLEMENTATION_SUMMARY.md**: Details of what was built

### Demo
- **demo/run_demo.py**: Runnable example showing schema definition, annotation, quality scoring, consensus, and reporting

### Infrastructure
- **docker-compose.yml**: Full local development stack (Postgres, Redis, Temporal, FastAPI)
- **Dockerfile**: Production-ready multi-stage build
- **.env.example**: Configuration template for all services

### Development Tools
- **requirements.txt**: All Python dependencies with versions
- **Makefile**: Automation for setup, testing, linting, Docker, cleanup

## Test Coverage

**Agreement Calculator (37 tests)**
- Cohen's Kappa: perfect agreement, complete disagreement, partial overlap, high-base-rate bias
- Fleiss' Kappa: unanimous, mixed agreement, label proportions
- Krippendorff's Alpha: missing data, variable raters, no overlap
- IoU: identical boxes, partial overlap, unmatched boxes
- Span F1: exact/relaxed matching, boundary mismatches, label mismatches
- BLEU: identical text, different text, partial overlap, brevity penalty
- Auto-selection: classification→kappa, bbox→IoU, spans→F1, text→BLEU

**Consensus Resolver (22 tests)**
- Majority Vote: unanimous, clear majorities, 3-way splits
- Weighted Vote: expert vs juniors, margin analysis, annotation selection
- Expert Tiebreak: escalation routing, high-confidence decisions
- Single Annotator: edge case with accuracy as confidence
- Batch Operations: multiple tasks, distribution analysis, resolution rates
- DEC-004 Backtest: weighted vote advantage demonstration

## Key Metrics

- **Tests**: 59 cases across 2 modules
- **Test Code**: 974 lines
- **Demo Script**: 335 lines
- **Documentation**: 1,827 lines
- **Architecture Diagrams**: 3 Mermaid diagrams (223 lines total)
- **Total New Code**: 3,000+ lines
- **Files Created**: 15

## Services

When running `docker-compose up -d`:

| Service | URL | Purpose |
|---------|-----|---------|
| API | http://localhost:8000 | FastAPI with Swagger docs |
| Temporal | http://localhost:8233 | Workflow orchestration |
| Postgres | localhost:5432 | Annotation data, schemas |
| Redis | localhost:6379 | Task queue, caching |
| pgAdmin | http://localhost:5050 | Database management (with --profile dev) |
| Grafana | http://localhost:3000 | Metrics dashboard (with --profile dev) |

## Architecture Components

**Quality Engine**
- Agreement Calculator: 7 metrics for different annotation types
- Consensus Resolver: Majority vote, weighted vote, expert tiebreak
- Annotator Scorer: Per-person accuracy tracking

**Task Management**
- Schema Registry: JSONB-based configurable schemas
- Task Router: Skill-weighted assignment with qualification gates
- Queue Manager: Priority queue with Redis

**Data Storage**
- PostgreSQL 15: Annotations, metadata, audit trail
- pgvector: Embedding-based search
- S3: Raw assets (images, audio, documents)

**Feedback Loop**
- Active Learner: Uncertainty sampling
- Drift Detector: Distribution monitoring
- Model Evaluator: Per-slice analysis

## Reading Order

1. **DEMO.md** - Understand the full pipeline with code examples
2. **README.md** - Overview with architecture diagrams
3. **CONTRIBUTING.md** - How to extend and develop
4. **Test files** - See detailed usage examples
5. **Source code** - Reference implementation in src/

## Development Workflow

```bash
# Setup
make setup

# Make changes to code

# Test locally
make test
make lint

# Run demo
make demo

# Start full stack if needed
make docker-up

# Run tests in Docker
make docker-test

# Clean up
make docker-down
make clean
```

---

All files are in: `/sessions/youthful-eager-lamport/mnt/Portfolio/ai-data-ops-platform/`
