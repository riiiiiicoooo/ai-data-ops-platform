"""
Database connection pooling and persistence layer for AI data ops platform.

Provides SQLAlchemy with QueuePool connection management and ORM models
for persisting task assignments and annotator state (skill tracking,
workload, accuracy metrics).

Design:
- QueuePool for efficient connection management (pool_size=10, max_overflow=20)
- SQLAlchemy ORM for type-safe queries and transactions
- Immutable task assignment audit trail
- Annotator skill and accuracy metrics for routing decisions

Models:
- AnnotatorProfile: annotator credentials, skills, qualifications, accuracy metrics
- TaskAssignment: persisted task-to-annotator assignments with scoring breakdown
- TaskQueue: task waiting for assignment with priority and requirements
"""

import os
from datetime import datetime
from typing import Optional
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    Float,
    DateTime,
    JSON,
    Boolean,
    Index,
    Enum as SQLEnum,
    event,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ai_data_ops"
)

# Connection pool configuration
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # 1 hour
POOL_PRE_PING = True  # Verify connections are alive before using

# Create engine with QueuePool
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_recycle=POOL_RECYCLE,
    pool_pre_ping=POOL_PRE_PING,
    echo=False,
)

# Create session factory
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# Declarative base for ORM models
Base = declarative_base()


# ============================================================================
# Enums
# ============================================================================


class AnnotatorSkillLevel(str, Enum):
    """Derived from rolling accuracy scores."""
    JUNIOR = "junior"  # < 85% accuracy
    SENIOR = "senior"  # 85-95% accuracy
    EXPERT = "expert"  # > 95% accuracy


class TaskPriority(str, Enum):
    """Task priority levels. Higher value = more urgent."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskSource(str, Enum):
    """Where the task originated. Affects routing priority."""
    BACKFILL = "backfill"
    STANDARD = "standard"
    ACTIVE_LEARNING = "active_learning"
    DRIFT_REANNOT = "drift_reannot"
    ERROR_CURRICULUM = "error_curriculum"


class TaskStatus(str, Enum):
    """Task lifecycle status."""
    QUEUED = "queued"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXPIRED = "expired"
    REJECTED = "rejected"


# ============================================================================
# ORM Models
# ============================================================================


class AnnotatorProfile(Base):
    """
    Annotator state and credentials for task routing.

    Tracks:
    - Skill levels and qualifications (domain expertise)
    - Accuracy metrics per task type (for weighted routing)
    - Current workload (active tasks, items completed today)
    - Status and availability

    This is the persistent source of truth for annotator state.
    Updated by accuracy feedback loop and skill assessment.
    """

    __tablename__ = "annotator_profiles"

    # Primary key
    id = Column(Integer, primary_key=True)
    annotator_id = Column(PG_UUID(as_uuid=True), nullable=False, unique=True, index=True)

    # Status
    status = Column(String(50), default="active")  # active, inactive, on_leave
    skill_level = Column(SQLEnum(AnnotatorSkillLevel), default=AnnotatorSkillLevel.JUNIOR)

    # Qualifications: domain -> qualified (JSON)
    # Example: {"radiology": true, "pathology": false, "rlhf": true}
    qualifications = Column(JSON, default=dict)

    # Accuracy metrics per task type (rolling last 100 golden items)
    # Example: {"radiology_xray": 0.94, "radiology_ct": 0.92, "rlhf_ranking": 0.87}
    accuracy_by_type = Column(JSON, default=dict)

    # Current workload
    active_tasks = Column(Integer, default=0)
    max_concurrent = Column(Integer, default=5)
    items_completed_today = Column(Integer, default=0)
    max_items_per_shift = Column(Integer, default=200)

    # Assignment tracking
    last_assigned_at = Column(DateTime)
    current_task_group = Column(String(255))  # for task grouping consistency

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_annotator_profile_status", "status"),
        Index("ix_annotator_profile_skill_level", "skill_level"),
    )

    def __repr__(self) -> str:
        return (
            f"<AnnotatorProfile(annotator_id={self.annotator_id}, "
            f"skill_level={self.skill_level}, active_tasks={self.active_tasks})>"
        )


class TaskQueue(Base):
    """
    Tasks waiting for assignment with routing requirements.

    Once a task is assigned, a TaskAssignment record is created.
    TaskQueue record is updated with status and assignment reference.

    Enables:
    - Queue management: prioritization and routing
    - SLA tracking: task age vs deadline
    - Performance analysis: task assignment latency
    """

    __tablename__ = "task_queue"

    # Primary key
    id = Column(Integer, primary_key=True)
    task_id = Column(PG_UUID(as_uuid=True), nullable=False, unique=True, index=True)
    project_id = Column(PG_UUID(as_uuid=True), nullable=False)
    batch_id = Column(PG_UUID(as_uuid=True), nullable=False)

    # Routing requirements
    required_qualifications = Column(JSON, default=list)  # e.g., ["radiology", "senior_analyst"]
    min_accuracy = Column(Float, default=0.0)
    task_type = Column(String(100), nullable=False)

    # Priority and source
    priority = Column(SQLEnum(TaskPriority), default=TaskPriority.NORMAL)
    source = Column(SQLEnum(TaskSource), default=TaskSource.STANDARD)
    task_group = Column(String(255))  # for grouping related items for consistency

    # Timing and SLA
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    deadline = Column(DateTime)
    reservation_timeout_minutes = Column(Integer, default=30)

    # Active learning metadata (optional)
    uncertainty_score = Column(Float)  # model uncertainty (for priority routing)

    # State and assignment
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.QUEUED)
    assigned_to = Column(PG_UUID(as_uuid=True))  # FK to annotator_id
    assigned_at = Column(DateTime)
    assignment_id = Column(Integer)  # FK to TaskAssignment.id

    __table_args__ = (
        Index("ix_task_queue_status", "status"),
        Index("ix_task_queue_priority", "priority"),
        Index("ix_task_queue_assigned_to", "assigned_to"),
        Index("ix_task_queue_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<TaskQueue(task_id={self.task_id}, "
            f"priority={self.priority}, status={self.status})>"
        )


class TaskAssignment(Base):
    """
    Immutable record of task-to-annotator assignment with scoring breakdown.

    Created once per task, never modified (audit trail requirement).
    Includes complete score breakdown for analysis and algorithm tuning.

    Enables:
    - Assignment quality evaluation: compare scores vs actual outcomes
    - Routing algorithm debugging: understand why assignment was made
    - Performance analysis: which routing features matter most
    - Audit trail: who was assigned what and when
    """

    __tablename__ = "task_assignments"

    # Primary key
    id = Column(Integer, primary_key=True)
    assignment_id = Column(String(255), nullable=False, unique=True, index=True)

    # Task and annotator
    task_id = Column(PG_UUID(as_uuid=True), nullable=False)
    annotator_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Routing decision
    assignment_score = Column(Float, nullable=False)  # 0-1 composite score

    # Score breakdown (JSON) for analysis and debugging
    # Example: {
    #   "qualification_match": 1.0,
    #   "accuracy_weight": 0.92,
    #   "workload_factor": 0.7,
    #   "consistency_bonus": 1.0,
    #   "priority_factor": 0.5
    # }
    score_breakdown = Column(JSON, default=dict)

    # Annotator state at assignment time (for reproducibility)
    annotator_skill_level = Column(SQLEnum(AnnotatorSkillLevel))
    annotator_active_tasks = Column(Integer)
    annotator_accuracy = Column(Float)

    # Timing
    assigned_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_task_assignment_task_id", "task_id"),
        Index("ix_task_assignment_annotator_id", "annotator_id"),
        Index("ix_task_assignment_assigned_at", "assigned_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<TaskAssignment(task_id={self.task_id}, "
            f"annotator_id={self.annotator_id}, score={self.assignment_score:.3f})>"
        )


class AnnotatorAccuracy(Base):
    """
    Rolling accuracy metrics per annotator and task type.

    Updated after each task is completed and reviewed.
    Used for skill level calculation and routing weight distribution.

    Enables:
    - Skill tracking: which annotators improve vs decline over time
    - Task type affinity: which annotators are best at which task types
    - Routing decisions: weight by observed accuracy
    """

    __tablename__ = "annotator_accuracy"

    # Primary key
    id = Column(Integer, primary_key=True)
    annotator_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    task_type = Column(String(100), nullable=False)

    # Accuracy metrics (rolling window, usually last 100 items)
    accuracy = Column(Float, nullable=False)  # 0.0 - 1.0
    num_evaluated = Column(Integer, default=0)

    # Trend (optional: accuracy improvement/decline)
    trend = Column(Float, default=0.0)  # positive = improving, negative = declining

    # Timestamps
    measured_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_annotator_accuracy_annotator_task", "annotator_id", "task_type"),
        Index("ix_annotator_accuracy_measured_at", "measured_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<AnnotatorAccuracy(annotator_id={self.annotator_id}, "
            f"task_type={self.task_type}, accuracy={self.accuracy:.2%})>"
        )


# ============================================================================
# Database Utilities
# ============================================================================


def init_db() -> None:
    """Initialize database schema. Call once on startup."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Get a database session. Use as context manager or with cleanup."""
    return SessionLocal()


def close_db() -> None:
    """Close all connections in the pool. Call on shutdown."""
    engine.dispose()


def save_annotator_profile(
    annotator_id: UUID,
    status: str = "active",
    skill_level: str = "junior",
    qualifications: Optional[dict] = None,
    accuracy_by_type: Optional[dict] = None,
    active_tasks: int = 0,
    max_concurrent: int = 5,
) -> AnnotatorProfile:
    """
    Persist or update an annotator profile.

    Args:
        annotator_id: Unique annotator identifier
        status: "active", "inactive", "on_leave"
        skill_level: "junior", "senior", "expert"
        qualifications: Dict of domain -> bool
        accuracy_by_type: Dict of task_type -> accuracy float
        active_tasks: Current active task count
        max_concurrent: Max concurrent tasks allowed

    Returns:
        Persisted AnnotatorProfile record
    """
    session = get_session()
    try:
        # Try to find existing profile
        profile = (
            session.query(AnnotatorProfile)
            .filter(AnnotatorProfile.annotator_id == annotator_id)
            .first()
        )

        if profile:
            # Update existing
            profile.status = status
            profile.skill_level = AnnotatorSkillLevel(skill_level)
            profile.qualifications = qualifications or profile.qualifications
            profile.accuracy_by_type = accuracy_by_type or profile.accuracy_by_type
            profile.active_tasks = active_tasks
            profile.max_concurrent = max_concurrent
            profile.updated_at = datetime.utcnow()
        else:
            # Create new
            profile = AnnotatorProfile(
                annotator_id=annotator_id,
                status=status,
                skill_level=AnnotatorSkillLevel(skill_level),
                qualifications=qualifications or {},
                accuracy_by_type=accuracy_by_type or {},
                active_tasks=active_tasks,
                max_concurrent=max_concurrent,
            )
            session.add(profile)

        session.commit()
        return profile
    finally:
        session.close()


def save_task_assignment(
    assignment_id: str,
    task_id: UUID,
    annotator_id: UUID,
    assignment_score: float,
    score_breakdown: Optional[dict] = None,
    annotator_skill_level: Optional[str] = None,
    annotator_active_tasks: Optional[int] = None,
    annotator_accuracy: Optional[float] = None,
) -> TaskAssignment:
    """
    Persist a task assignment decision.

    Args:
        assignment_id: Unique assignment identifier
        task_id: Task being assigned
        annotator_id: Annotator receiving the task
        assignment_score: Composite routing score (0-1)
        score_breakdown: Breakdown by routing algorithm component
        annotator_skill_level: Annotator's skill level at assignment time
        annotator_active_tasks: Annotator's active task count at assignment time
        annotator_accuracy: Annotator's accuracy at assignment time

    Returns:
        Persisted TaskAssignment record
    """
    session = get_session()
    try:
        record = TaskAssignment(
            assignment_id=assignment_id,
            task_id=task_id,
            annotator_id=annotator_id,
            assignment_score=assignment_score,
            score_breakdown=score_breakdown or {},
            annotator_skill_level=(
                AnnotatorSkillLevel(annotator_skill_level)
                if annotator_skill_level
                else None
            ),
            annotator_active_tasks=annotator_active_tasks,
            annotator_accuracy=annotator_accuracy,
        )
        session.add(record)
        session.commit()
        return record
    finally:
        session.close()


def get_annotator_profile(annotator_id: UUID) -> Optional[AnnotatorProfile]:
    """Retrieve an annotator's profile."""
    session = get_session()
    try:
        return (
            session.query(AnnotatorProfile)
            .filter(AnnotatorProfile.annotator_id == annotator_id)
            .first()
        )
    finally:
        session.close()


def get_task_assignment(task_id: UUID) -> Optional[TaskAssignment]:
    """Retrieve the assignment for a specific task."""
    session = get_session()
    try:
        return (
            session.query(TaskAssignment)
            .filter(TaskAssignment.task_id == task_id)
            .first()
        )
    finally:
        session.close()


def get_annotator_accuracy(annotator_id: UUID, task_type: str) -> Optional[AnnotatorAccuracy]:
    """Retrieve accuracy metrics for annotator on task type."""
    session = get_session()
    try:
        return (
            session.query(AnnotatorAccuracy)
            .filter(
                AnnotatorAccuracy.annotator_id == annotator_id,
                AnnotatorAccuracy.task_type == task_type,
            )
            .order_by(AnnotatorAccuracy.measured_at.desc())
            .first()
        )
    finally:
        session.close()


def save_annotator_accuracy(
    annotator_id: UUID,
    task_type: str,
    accuracy: float,
    num_evaluated: int = 0,
    trend: float = 0.0,
) -> AnnotatorAccuracy:
    """
    Persist or update annotator accuracy metrics.

    Args:
        annotator_id: Annotator identifier
        task_type: Type of task (e.g., "radiology_xray")
        accuracy: Current accuracy (0.0 - 1.0)
        num_evaluated: Number of items evaluated
        trend: Accuracy trend (positive = improving)

    Returns:
        Persisted AnnotatorAccuracy record
    """
    session = get_session()
    try:
        # Find existing or create new
        record = (
            session.query(AnnotatorAccuracy)
            .filter(
                AnnotatorAccuracy.annotator_id == annotator_id,
                AnnotatorAccuracy.task_type == task_type,
            )
            .order_by(AnnotatorAccuracy.measured_at.desc())
            .first()
        )

        if record:
            record.accuracy = accuracy
            record.num_evaluated = num_evaluated
            record.trend = trend
            record.updated_at = datetime.utcnow()
        else:
            record = AnnotatorAccuracy(
                annotator_id=annotator_id,
                task_type=task_type,
                accuracy=accuracy,
                num_evaluated=num_evaluated,
                trend=trend,
            )
            session.add(record)

        session.commit()
        return record
    finally:
        session.close()


if __name__ == "__main__":
    # Example: initialize database and create tables
    init_db()
    print("Database initialized successfully")
