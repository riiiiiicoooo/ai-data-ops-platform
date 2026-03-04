/**
 * Active Learning Job
 *
 * Trigger.dev job for identifying uncertain samples and creating annotation tasks.
 *
 * Flow:
 * 1. Fetch model predictions with entropy scores
 * 2. Rank by uncertainty + curriculum (error patterns)
 * 3. Create annotation tasks for top-N samples
 * 4. Assign to annotators based on skill and capacity
 * 5. Send notifications via Resend + Slack
 * 6. Track budget and annotator workload
 */

import { task } from "@trigger.dev/sdk/v3";
import { createClient } from "@supabase/supabase-js";

// Types
interface ModelPrediction {
  id: string;
  data_item_id: string;
  predicted_label: Record<string, any>;
  confidence: number;
  entropy: number;
  embedding: number[];
  created_at: string;
}

interface UncertainSample {
  prediction_id: string;
  data_item_id: string;
  entropy: number;
  model_confidence: number;
  curriculum_priority: number;
  error_pattern: string;
}

interface AnnotatorCapacity {
  annotator_id: string;
  name: string;
  email: string;
  current_load: number;
  max_capacity: number;
  skill_level: string;
  available_capacity: number;
}

interface TaskAssignment {
  annotator_id: string;
  data_item_id: string;
  priority: "high" | "medium" | "low";
}

/**
 * Identify uncertain samples from model predictions
 * Uses entropy-based uncertainty with error pattern weighting
 */
async function selectUncertainSamples(
  projectId: string,
  budget: number = 50,
  entropyThreshold: number = 0.5
): Promise<UncertainSample[]> {
  const supabase = createClient(
    process.env.SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_KEY!
  );

  // Fetch high-entropy predictions (uncertain samples)
  const { data: predictions, error } = await supabase
    .from("model_predictions")
    .select("*")
    .eq("project_id", projectId)
    .gte("entropy", entropyThreshold)
    .order("entropy", { ascending: false })
    .limit(budget * 2); // Over-fetch to allow filtering

  if (error) throw new Error(`Failed to fetch predictions: ${error.message}`);

  if (!predictions || predictions.length === 0) {
    console.log(`No uncertain samples found (entropy > ${entropyThreshold})`);
    return [];
  }

  // Convert to uncertain samples with curriculum priority
  const samples: UncertainSample[] = predictions.map((pred) => {
    // Curriculum priority combines entropy + error pattern importance
    const errorPatternWeight = getErrorPatternWeight(pred);
    const curriculumPriority = pred.entropy * 0.7 + errorPatternWeight * 0.3;

    return {
      prediction_id: pred.id,
      data_item_id: pred.data_item_id,
      entropy: pred.entropy,
      model_confidence: pred.confidence,
      curriculum_priority: curriculumPriority,
      error_pattern: getErrorPattern(pred.model_version),
    };
  });

  // Sort by curriculum priority
  samples.sort((a, b) => b.curriculum_priority - a.curriculum_priority);

  // Return top budget samples
  return samples.slice(0, budget);
}

/**
 * Determine error pattern from model version/performance
 */
function getErrorPattern(modelVersion: string): string {
  // Simplified: in production, would query per-slice analysis
  const patterns = [
    "medical_abbreviations",
    "edge_cases",
    "class_imbalance",
    "domain_shift",
    "ambiguous_examples",
  ];

  // Hash model version to pattern for reproducibility
  const hash = modelVersion.split("").reduce((a, b) => {
    a = (a << 5) - a + b.charCodeAt(0);
    return a & a; // Convert to 32-bit integer
  }, 0);

  return patterns[Math.abs(hash) % patterns.length];
}

/**
 * Get error pattern weight (0-1) for curriculum ranking
 */
function getErrorPatternWeight(prediction: ModelPrediction): number {
  // In production: would come from per-slice error analysis
  // Critical patterns (medical_abbreviations): 0.9
  // Important patterns: 0.7
  // Standard: 0.5

  if (!prediction.predicted_label) return 0.5;

  // Example: if prediction contains medical terminology, boost weight
  const label = JSON.stringify(prediction.predicted_label).toLowerCase();
  if (
    label.includes("medical") ||
    label.includes("abbreviation") ||
    label.includes("rare")
  ) {
    return 0.9;
  }

  return 0.5;
}

/**
 * Get available annotators sorted by capacity and skill match
 */
async function getAvailableAnnotators(
  projectId: string
): Promise<AnnotatorCapacity[]> {
  const supabase = createClient(
    process.env.SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_KEY!
  );

  // Fetch active annotators
  const { data: annotators, error: annotError } = await supabase
    .from("annotators")
    .select("id, name, email, skill_level, total_annotations, annotations_per_hour")
    .eq("status", "active")
    .gte("accuracy_score", 0.75); // Minimum accuracy threshold

  if (annotError) throw new Error(`Failed to fetch annotators: ${annotError.message}`);

  if (!annotators || annotators.length === 0) {
    console.log("No available annotators found");
    return [];
  }

  // Fetch current task assignments to calculate capacity
  const { data: assignments, error: assignError } = await supabase
    .from("annotation_tasks")
    .select("assigned_to")
    .eq("status", "assigned");

  if (assignError) {
    throw new Error(`Failed to fetch task assignments: ${assignError.message}`);
  }

  // Count tasks per annotator
  const taskCounts: Record<string, number> = {};
  assignments?.forEach((task) => {
    task.assigned_to?.forEach((annoId: string) => {
      taskCounts[annoId] = (taskCounts[annoId] || 0) + 1;
    });
  });

  // Calculate capacity: assume max 20 tasks per annotator before overload
  const maxTasks = 20;
  const capacities: AnnotatorCapacity[] = annotators.map((ann) => {
    const currentLoad = taskCounts[ann.id] || 0;
    const availableCapacity = Math.max(0, maxTasks - currentLoad);

    return {
      annotator_id: ann.id,
      name: ann.name,
      email: ann.email,
      current_load: currentLoad,
      max_capacity: maxTasks,
      skill_level: ann.skill_level,
      available_capacity: availableCapacity,
    };
  });

  // Sort by: skill_level DESC (experts first), then available_capacity DESC
  capacities.sort((a, b) => {
    const skillOrder = { expert: 3, senior: 2, junior: 1 };
    const skillDiff =
      (skillOrder[b.skill_level as keyof typeof skillOrder] || 0) -
      (skillOrder[a.skill_level as keyof typeof skillOrder] || 0);
    if (skillDiff !== 0) return skillDiff;
    return b.available_capacity - a.available_capacity;
  });

  return capacities.filter((cap) => cap.available_capacity > 0);
}

/**
 * Assign samples to annotators using round-robin with capacity awareness
 */
async function assignSamplesToAnnotators(
  samples: UncertainSample[],
  annotators: AnnotatorCapacity[]
): Promise<TaskAssignment[]> {
  if (!annotators || annotators.length === 0) {
    console.log("No annotators available for assignment");
    return [];
  }

  const assignments: TaskAssignment[] = [];
  let annotatorIndex = 0;

  samples.forEach((sample) => {
    if (annotators.length === 0) return;

    // Find annotator with available capacity
    let attempts = 0;
    while (attempts < annotators.length) {
      const annotator = annotators[annotatorIndex];
      annotatorIndex = (annotatorIndex + 1) % annotators.length;

      if (annotator.available_capacity > 0) {
        assignments.push({
          annotator_id: annotator.annotator_id,
          data_item_id: sample.data_item_id,
          priority: "high", // Active learning samples are always high priority
        });

        annotator.available_capacity -= 1;
        break;
      }

      attempts += 1;
    }
  });

  return assignments;
}

/**
 * Create annotation tasks in Supabase
 */
async function createAnnotationTasks(
  projectId: string,
  samples: UncertainSample[],
  schemaType: string
): Promise<string[]> {
  const supabase = createClient(
    process.env.SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_KEY!
  );

  // Fetch schema ID for project
  const { data: schema, error: schemaError } = await supabase
    .from("annotation_schemas")
    .select("id")
    .eq("project_id", projectId)
    .eq("is_active", true)
    .single();

  if (schemaError) {
    throw new Error(`Failed to fetch schema: ${schemaError.message}`);
  }

  // Batch insert tasks
  const batchId = `active_learning_${Date.now()}`;
  const tasksToInsert = samples.map((sample, index) => ({
    project_id: projectId,
    schema_id: schema.id,
    data_item_id: sample.data_item_id,
    data: { prediction_id: sample.prediction_id },
    priority: "high",
    status: "created",
    batch_id: batchId,
    batch_sequence: index,
  }));

  const { data: createdTasks, error: insertError } = await supabase
    .from("annotation_tasks")
    .insert(tasksToInsert)
    .select("id");

  if (insertError) {
    throw new Error(`Failed to create tasks: ${insertError.message}`);
  }

  console.log(`Created ${createdTasks?.length || 0} annotation tasks`);
  return createdTasks?.map((t) => t.id) || [];
}

/**
 * Assign tasks to annotators in Supabase
 */
async function assignTasksToAnnotators(
  taskAssignments: TaskAssignment[]
): Promise<number> {
  const supabase = createClient(
    process.env.SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_KEY!
  );

  // Group by task (data_item_id) and annotator
  const assignmentsByTask: Record<string, string[]> = {};

  taskAssignments.forEach((assignment) => {
    if (!assignmentsByTask[assignment.data_item_id]) {
      assignmentsByTask[assignment.data_item_id] = [];
    }
    assignmentsByTask[assignment.data_item_id].push(assignment.annotator_id);
  });

  // Update tasks with assigned_to array
  let updateCount = 0;
  for (const [dataItemId, annotatorIds] of Object.entries(assignmentsByTask)) {
    const { error } = await supabase
      .from("annotation_tasks")
      .update({
        assigned_to: annotatorIds,
        status: "assigned",
      })
      .eq("data_item_id", dataItemId);

    if (error) {
      console.error(
        `Failed to assign task for ${dataItemId}: ${error.message}`
      );
    } else {
      updateCount += 1;
    }
  }

  return updateCount;
}

/**
 * Send assignment notifications via Resend
 */
async function sendAssignmentNotifications(
  taskAssignments: TaskAssignment[],
  annotators: Map<string, { name: string; email: string }>
): Promise<number> {
  // Group assignments by annotator
  const byAnnotator: Record<string, number> = {};
  taskAssignments.forEach((assignment) => {
    byAnnotator[assignment.annotator_id] =
      (byAnnotator[assignment.annotator_id] || 0) + 1;
  });

  // Send email to each annotator
  let sentCount = 0;
  for (const [annotatorId, count] of Object.entries(byAnnotator)) {
    const annotator = annotators.get(annotatorId);
    if (!annotator) continue;

    try {
      const response = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from: "assignments@aidata.example.com",
          to: annotator.email,
          subject: `New Active Learning Tasks - ${count} items`,
          html: `
            <h1>You have new annotation tasks</h1>
            <p>Hi ${annotator.name},</p>
            <p>We've selected ${count} uncertain samples from our model that need your expertise.</p>
            <p><strong>Priority:</strong> HIGH</p>
            <p>These are high-value samples that will directly improve our model.</p>
            <p><a href="${process.env.APP_URL}/tasks">View Tasks</a></p>
          `,
        }),
      });

      if (response.ok) {
        sentCount += 1;
      }
    } catch (error) {
      console.error(`Failed to send email to ${annotator.email}:`, error);
    }
  }

  return sentCount;
}

/**
 * Main job: Run active learning sample selection
 */
export const activeLearning = task({
  id: "active-learning",
  run: async (payload: {
    projectId: string;
    budget?: number;
    entropyThreshold?: number;
    schemaType?: string;
  }) => {
    const budget = payload.budget || 50;
    const entropyThreshold = payload.entropyThreshold || 0.5;
    const schemaType = payload.schemaType || "classification";

    console.log(
      `Starting active learning for project ${payload.projectId}, budget: ${budget}`
    );

    try {
      // Step 1: Select uncertain samples
      const samples = await selectUncertainSamples(
        payload.projectId,
        budget,
        entropyThreshold
      );

      console.log(
        `Checkpoint 1: Selected ${samples.length} uncertain samples`
      );

      if (samples.length === 0) {
        return {
          status: "no_samples",
          message: "No uncertain samples found",
          timestamp: new Date().toISOString(),
        };
      }

      // Step 2: Get available annotators
      const annotators = await getAvailableAnnotators(payload.projectId);

      console.log(`Checkpoint 2: Found ${annotators.length} available annotators`);

      if (annotators.length === 0) {
        return {
          status: "no_annotators",
          message: "No available annotators",
          samples_found: samples.length,
          timestamp: new Date().toISOString(),
        };
      }

      // Step 3: Assign samples to annotators
      const taskAssignments = await assignSamplesToAnnotators(
        samples,
        annotators
      );

      console.log(`Checkpoint 3: Created ${taskAssignments.length} assignments`);

      // Step 4: Create annotation tasks
      const taskIds = await createAnnotationTasks(
        payload.projectId,
        samples,
        schemaType
      );

      console.log(`Checkpoint 4: Created ${taskIds.length} tasks in Supabase`);

      // Step 5: Assign tasks to annotators
      const assignedCount = await assignTasksToAnnotators(taskAssignments);

      console.log(`Checkpoint 5: Assigned ${assignedCount} tasks to annotators`);

      // Step 6: Create annotator map for notifications
      const annotatorMap = new Map<string, { name: string; email: string }>();
      annotators.forEach((ann) => {
        annotatorMap.set(ann.annotator_id, {
          name: ann.name,
          email: ann.email,
        });
      });

      // Step 7: Send notifications
      const emailsSent = await sendAssignmentNotifications(
        taskAssignments,
        annotatorMap
      );

      console.log(`Checkpoint 6: Sent ${emailsSent} notification emails`);

      // Step 8: Return summary
      const summary = {
        status: "complete",
        samples_identified: samples.length,
        tasks_created: taskIds.length,
        assignments_made: taskAssignments.length,
        annotators_notified: emailsSent,
        budget_used: samples.length,
        budget_available: budget,
        top_error_patterns: [...new Set(samples.map((s) => s.error_pattern))],
        avg_entropy: samples.length > 0 ? samples.reduce((a, s) => a + s.entropy, 0) / samples.length : 0,
        timestamp: new Date().toISOString(),
      };

      console.log("Active learning job complete");
      return summary;
    } catch (error) {
      console.error("Active learning job failed:", error);
      throw error;
    }
  },
});

export default activeLearning;
