-- AI Data Ops Platform - Initial Schema Migration
-- Supabase PostgreSQL with pgvector extension and RLS policies

-- Enable pgvector extension for embedding-based search
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS uuid-ossp;

-- ============================================================================
-- CORE TABLES
-- ============================================================================

-- Projects: Organizational container for annotation tasks
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    organization_id UUID NOT NULL,
    industry TEXT,  -- "healthcare", "ai-ml", "automotive", "finance", etc.
    status TEXT DEFAULT 'active',  -- active, archived, paused

    -- Configuration
    quality_threshold FLOAT DEFAULT 0.80,  -- min agreement score
    review_rate FLOAT DEFAULT 0.20,  -- spot-check percentage
    stages INTEGER DEFAULT 2,  -- number of workflow stages
    consensus_strategy TEXT DEFAULT 'majority_vote',  -- majority_vote, weighted_vote, expert_only

    -- Tracking
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,

    CONSTRAINT valid_quality_threshold CHECK (quality_threshold >= 0 AND quality_threshold <= 1),
    CONSTRAINT valid_review_rate CHECK (review_rate >= 0 AND review_rate <= 1),
    CONSTRAINT valid_stages CHECK (stages >= 1 AND stages <= 3)
);

-- Annotators: Workforce profiles with skill tracking
CREATE TABLE annotators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE,  -- Links to auth.users
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,

    -- Skill tracking
    skill_level TEXT DEFAULT 'junior',  -- junior, senior, expert
    domain_expertise TEXT[],  -- e.g., ["radiology", "nlp"]
    accuracy_score FLOAT DEFAULT 0.0,  -- rolling average (0-1)
    total_annotations INTEGER DEFAULT 0,

    -- Qualification
    qualifications JSONB DEFAULT '{}'::jsonb,  -- {project_id: {passed: true, score: 0.95, date: "..."}}
    is_qualified BOOLEAN DEFAULT FALSE,

    -- Throughput
    annotations_per_hour FLOAT DEFAULT 0.0,
    last_active_at TIMESTAMP WITH TIME ZONE,

    -- Status
    status TEXT DEFAULT 'active',  -- active, inactive, suspended
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Annotation Schemas: JSONB-based configurable task definitions
CREATE TABLE annotation_schemas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    description TEXT,

    -- Schema definition
    schema_type TEXT NOT NULL,  -- "classification", "ner", "bounding_box", "preference", "free_text"
    definition JSONB NOT NULL,  -- Flexible schema definition per type

    -- Version tracking
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,

    -- Quality settings
    required_agreement_metric TEXT,  -- "kappa", "alpha", "iou", "dice", "span_f1", "bleu"
    min_agreement_threshold FLOAT DEFAULT 0.80,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,

    CONSTRAINT unique_project_schema_active UNIQUE (project_id, name) WHERE is_active = TRUE
);

-- Annotation Tasks: Items to be labeled
CREATE TABLE annotation_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    schema_id UUID NOT NULL REFERENCES annotation_schemas(id),

    -- Task content
    data_item_id TEXT NOT NULL,  -- External reference to raw data
    data JSONB NOT NULL,  -- Raw item to annotate

    -- Metadata
    priority TEXT DEFAULT 'normal',  -- high, normal, low
    deadline TIMESTAMP WITH TIME ZONE,
    assigned_to UUID[] DEFAULT ARRAY[]::uuid[],  -- Array of annotator IDs

    -- Status tracking
    status TEXT DEFAULT 'created',  -- created, assigned, in_progress, submitted, review, completed, escalated
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    assigned_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Batch tracking
    batch_id TEXT,
    batch_sequence INTEGER,

    CONSTRAINT unique_task_item UNIQUE (project_id, data_item_id)
);

-- Annotations: Individual annotator submissions
CREATE TABLE annotations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES annotation_tasks(id),
    annotator_id UUID NOT NULL REFERENCES annotators(id),
    project_id UUID NOT NULL REFERENCES projects(id),

    -- Submission
    output JSONB NOT NULL,  -- The annotation data (flexible per schema)
    confidence FLOAT,  -- Annotator's confidence (0-1) if applicable
    time_spent_seconds INTEGER,

    -- Workflow stage
    stage INTEGER DEFAULT 1,  -- 1=label, 2=review, 3=adjudicate
    stage_status TEXT DEFAULT 'submitted',  -- submitted, approved, rejected, escalated
    stage_feedback TEXT,  -- If rejected, why

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT valid_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

-- Consensus Results: Final agreed-upon labels
CREATE TABLE consensus_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES annotation_tasks(id) UNIQUE,
    project_id UUID NOT NULL REFERENCES projects(id),

    -- Consensus label
    final_label JSONB NOT NULL,
    resolution_strategy TEXT NOT NULL,  -- "majority_vote", "weighted_vote", "expert_decision"

    -- Quality metrics
    agreement_score FLOAT NOT NULL,  -- Final agreement metric (kappa, alpha, etc.)
    agreement_metric TEXT NOT NULL,  -- Which metric was used
    n_annotators INTEGER NOT NULL,

    -- Decision process
    needed_escalation BOOLEAN DEFAULT FALSE,
    expert_id UUID REFERENCES annotators(id),

    -- Tracking
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    usable BOOLEAN DEFAULT TRUE  -- Did it pass quality check?
);

-- Quality Scores: Per-batch quality metrics
CREATE TABLE quality_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    batch_id TEXT NOT NULL,

    -- Batch metadata
    batch_size INTEGER,
    completed_count INTEGER,

    -- Quality metrics
    avg_agreement_score FLOAT,
    agreement_metric TEXT,
    golden_set_accuracy FLOAT,  -- Against known correct answers
    consensus_resolution_rate FLOAT,  -- % resolved without expert

    -- Annotator performance
    top_performer_id UUID REFERENCES annotators(id),
    annotator_performance JSONB,  -- {annotator_id: {accuracy: 0.95, count: 100}}

    -- Status
    passed_quality_check BOOLEAN,
    status TEXT DEFAULT 'completed',  -- pending, in_progress, completed, failed

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Active Learning Queue: Uncertain samples for targeted annotation
CREATE TABLE active_learning_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),

    -- Source
    model_prediction_id TEXT NOT NULL,  -- Link to model output
    data_item_id TEXT NOT NULL,

    -- Uncertainty metrics
    prediction_entropy FLOAT NOT NULL,  -- Uncertainty score
    model_confidence FLOAT,
    uncertainty_ranking INTEGER,  -- Rank by informativeness

    -- Curriculum
    curriculum_priority FLOAT,  -- Weighted by error patterns + entropy
    error_pattern_tag TEXT,  -- e.g., "medical_abbreviations", "low_light"

    -- Status
    status TEXT DEFAULT 'queued',  -- queued, assigned, completed
    assigned_to UUID REFERENCES annotators(id),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    assigned_at TIMESTAMP WITH TIME ZONE
);

-- Annotator Accuracy Tracking: Rolling performance metrics
CREATE TABLE annotator_accuracy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    annotator_id UUID NOT NULL REFERENCES annotators(id),
    project_id UUID NOT NULL REFERENCES projects(id),

    -- Window-based accuracy
    window_start_date DATE,
    window_size_days INTEGER DEFAULT 7,

    -- Metrics
    accuracy FLOAT NOT NULL,  -- Correct answers vs. golden set
    precision FLOAT,
    recall FLOAT,
    f1_score FLOAT,

    -- Sample count
    n_evaluated INTEGER,
    n_correct INTEGER,

    -- Trend
    trend TEXT,  -- "improving", "stable", "declining"

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT unique_annotator_window UNIQUE (annotator_id, project_id, window_start_date)
);

-- Model Predictions: For active learning and drift detection
CREATE TABLE model_predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    model_version TEXT NOT NULL,

    -- Input
    data_item_id TEXT NOT NULL,
    data JSONB,

    -- Prediction
    predicted_label JSONB NOT NULL,
    confidence FLOAT,
    entropy FLOAT,  -- For uncertainty sampling

    -- Embedding for similarity search
    embedding vector(768),  -- OpenAI/sentence-transformers dimension

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Task querying
CREATE INDEX idx_annotation_tasks_project_status ON annotation_tasks(project_id, status);
CREATE INDEX idx_annotation_tasks_priority_deadline ON annotation_tasks(project_id, priority, deadline);
CREATE INDEX idx_annotation_tasks_assigned_to ON annotation_tasks USING GIN(assigned_to);
CREATE INDEX idx_annotation_tasks_batch ON annotation_tasks(project_id, batch_id);

-- Annotation retrieval
CREATE INDEX idx_annotations_task_annotator ON annotations(task_id, annotator_id);
CREATE INDEX idx_annotations_project_created ON annotations(project_id, created_at);
CREATE INDEX idx_annotations_stage ON annotations(project_id, stage, stage_status);

-- Consensus
CREATE INDEX idx_consensus_results_project ON consensus_results(project_id, created_at);
CREATE INDEX idx_consensus_results_quality ON consensus_results(project_id, usable);

-- Quality tracking
CREATE INDEX idx_quality_scores_project_batch ON quality_scores(project_id, batch_id);
CREATE INDEX idx_quality_scores_time ON quality_scores(project_id, created_at);

-- Active learning
CREATE INDEX idx_active_learning_queue_project_status ON active_learning_queue(project_id, status);
CREATE INDEX idx_active_learning_queue_entropy ON active_learning_queue(project_id, prediction_entropy DESC);
CREATE INDEX idx_active_learning_queue_curriculum ON active_learning_queue(project_id, curriculum_priority DESC);

-- Annotator queries
CREATE INDEX idx_annotators_organization ON annotators(id) WHERE status = 'active';
CREATE INDEX idx_annotator_accuracy_project_date ON annotator_accuracy(project_id, window_start_date);

-- Embedding similarity search
CREATE INDEX idx_model_predictions_embedding ON model_predictions USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ============================================================================
-- ROW-LEVEL SECURITY (RLS) POLICIES
-- ============================================================================

-- Enable RLS on all tables
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotators ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotation_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE consensus_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE quality_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE active_learning_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotator_accuracy ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotation_schemas ENABLE ROW LEVEL SECURITY;

-- Projects: Organization members can view/manage their projects
CREATE POLICY "Users can view projects in their organization"
    ON projects FOR SELECT
    USING (organization_id IN (
        SELECT organization_id FROM annotators
        WHERE user_id = auth.uid()
    ) OR created_by = auth.uid());

-- Annotators: Can only view themselves
CREATE POLICY "Annotators can view their own profile"
    ON annotators FOR SELECT
    USING (user_id = auth.uid() OR id IN (
        SELECT id FROM annotators WHERE id = auth.uid()
    ));

CREATE POLICY "Annotators can update their own profile"
    ON annotators FOR UPDATE
    USING (user_id = auth.uid());

-- Annotation Tasks: Assigned annotators see their tasks, reviewers see all
CREATE POLICY "Annotators see their assigned tasks"
    ON annotation_tasks FOR SELECT
    USING (
        assigned_to @> ARRAY[(
            SELECT id FROM annotators WHERE user_id = auth.uid()
        )]
        OR
        -- Reviewers/admins see all tasks in their projects
        project_id IN (
            SELECT project_id FROM annotators
            WHERE user_id = auth.uid() AND skill_level IN ('senior', 'expert')
        )
    );

CREATE POLICY "Annotators can create annotations on assigned tasks"
    ON annotations FOR INSERT
    WITH CHECK (
        task_id IN (
            SELECT id FROM annotation_tasks
            WHERE assigned_to @> ARRAY[(
                SELECT id FROM annotators WHERE user_id = auth.uid()
            )]
        )
    );

-- Annotations: Annotators see their own submissions; reviewers see all
CREATE POLICY "Annotators see their own annotations"
    ON annotations FOR SELECT
    USING (
        annotator_id = (
            SELECT id FROM annotators WHERE user_id = auth.uid()
        )
        OR
        -- Reviewers see all
        (
            SELECT skill_level FROM annotators WHERE user_id = auth.uid()
        ) IN ('senior', 'expert')
    );

-- Consensus Results: Visible to reviewers and admins
CREATE POLICY "Reviewers can view consensus results"
    ON consensus_results FOR SELECT
    USING (
        (SELECT skill_level FROM annotators WHERE user_id = auth.uid())
        IN ('senior', 'expert')
    );

-- Quality Scores: Visible to project managers and above
CREATE POLICY "Project managers can view quality scores"
    ON quality_scores FOR SELECT
    USING (
        project_id IN (
            SELECT project_id FROM annotators
            WHERE user_id = auth.uid() AND skill_level = 'expert'
        )
    );

-- Active Learning: Only admins can manage
CREATE POLICY "Admins can manage active learning queue"
    ON active_learning_queue FOR ALL
    USING (
        (SELECT skill_level FROM annotators WHERE user_id = auth.uid()) = 'expert'
    );

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- Task assignment view: Counts tasks per annotator per status
CREATE VIEW task_assignment_summary AS
SELECT
    a.id as annotator_id,
    a.name,
    p.id as project_id,
    COUNT(CASE WHEN t.status = 'assigned' THEN 1 END) as assigned_count,
    COUNT(CASE WHEN t.status = 'in_progress' THEN 1 END) as in_progress_count,
    COUNT(CASE WHEN t.status = 'completed' THEN 1 END) as completed_count,
    COUNT(*) as total_assigned
FROM annotators a
JOIN annotation_tasks t ON t.assigned_to @> ARRAY[a.id]
JOIN projects p ON p.id = t.project_id
WHERE a.status = 'active'
GROUP BY a.id, a.name, p.id;

-- Quality summary view: Aggregated metrics per project/batch
CREATE VIEW quality_summary AS
SELECT
    qs.project_id,
    qs.batch_id,
    qs.batch_size,
    qs.completed_count,
    ROUND(qs.avg_agreement_score::numeric, 3) as avg_agreement,
    ROUND(qs.golden_set_accuracy::numeric, 3) as golden_accuracy,
    ROUND(qs.consensus_resolution_rate::numeric, 3) as resolution_rate,
    qs.passed_quality_check,
    qs.created_at
FROM quality_scores qs
ORDER BY qs.created_at DESC;

-- Annotator performance view: Skills and recent accuracy
CREATE VIEW annotator_performance AS
SELECT
    a.id,
    a.name,
    a.email,
    a.skill_level,
    a.accuracy_score,
    a.total_annotations,
    a.annotations_per_hour,
    aa.accuracy as recent_accuracy,
    aa.window_start_date as accuracy_as_of
FROM annotators a
LEFT JOIN LATERAL (
    SELECT accuracy, window_start_date
    FROM annotator_accuracy
    WHERE annotator_id = a.id
    ORDER BY window_start_date DESC
    LIMIT 1
) aa ON TRUE
WHERE a.status = 'active';

-- ============================================================================
-- FUNCTIONS FOR COMMON OPERATIONS
-- ============================================================================

-- Function: Update task status and timestamps
CREATE OR REPLACE FUNCTION update_task_status(
    p_task_id UUID,
    p_status TEXT,
    p_annotator_id UUID DEFAULT NULL
)
RETURNS annotation_tasks AS $$
DECLARE
    v_task annotation_tasks;
BEGIN
    UPDATE annotation_tasks
    SET
        status = p_status,
        updated_at = NOW(),
        assigned_at = CASE WHEN p_status = 'assigned' AND assigned_at IS NULL THEN NOW() ELSE assigned_at END,
        completed_at = CASE WHEN p_status = 'completed' THEN NOW() ELSE completed_at END
    WHERE id = p_task_id
    RETURNING * INTO v_task;
    RETURN v_task;
END;
$$ LANGUAGE plpgsql;

-- Function: Record consensus and mark task complete
CREATE OR REPLACE FUNCTION record_consensus(
    p_task_id UUID,
    p_final_label JSONB,
    p_agreement_score FLOAT,
    p_metric TEXT,
    p_strategy TEXT,
    p_expert_id UUID DEFAULT NULL
)
RETURNS consensus_results AS $$
DECLARE
    v_task annotation_tasks;
    v_consensus consensus_results;
    v_project_id UUID;
BEGIN
    SELECT * INTO v_task FROM annotation_tasks WHERE id = p_task_id;
    v_project_id := v_task.project_id;

    INSERT INTO consensus_results (
        task_id,
        project_id,
        final_label,
        agreement_score,
        agreement_metric,
        resolution_strategy,
        n_annotators,
        expert_id,
        needed_escalation,
        usable
    )
    SELECT
        p_task_id,
        v_project_id,
        p_final_label,
        p_agreement_score,
        p_metric,
        p_strategy,
        COUNT(*),
        p_expert_id,
        p_expert_id IS NOT NULL,
        p_agreement_score >= (SELECT quality_threshold FROM projects WHERE id = v_project_id)
    FROM annotations
    WHERE task_id = p_task_id
    RETURNING * INTO v_consensus;

    -- Update task status
    PERFORM update_task_status(p_task_id, 'completed', NULL);

    RETURN v_consensus;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- SAMPLE DATA (optional, for testing)
-- ============================================================================

-- Insert a sample organization and project (comment out if not needed)
-- INSERT INTO projects (name, description, organization_id, industry)
-- VALUES (
--     'Medical Imaging Classification',
--     'Radiology image labeling for tumor detection',
--     gen_random_uuid(),
--     'healthcare'
-- );
