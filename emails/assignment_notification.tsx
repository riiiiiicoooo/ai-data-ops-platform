/**
 * Assignment Notification Email Template
 *
 * Sends notification when an annotator receives new task assignments.
 * Includes task count, priority level, deadline, and quick action link.
 * Uses Resend React Email components.
 *
 * Usage:
 * const html = render(<AssignmentNotification {...data} />);
 * await resend.emails.send({
 *   from: "assignments@aidata.example.com",
 *   to: annotator.email,
 *   subject: `New Tasks: ${taskCount} items assigned`,
 *   html,
 * });
 */

import {
  Html,
  Head,
  Body,
  Container,
  Section,
  Row,
  Column,
  Text,
  Button,
  Hr,
  Link,
} from "@react-email/components";
import * as React from "react";

interface TaskAssignment {
  id: string;
  title: string;
  priority: "high" | "medium" | "low";
  deadline?: string;
  estimatedTime?: number; // in minutes
}

interface AssignmentNotificationProps {
  annotatorName: string;
  taskCount: number;
  tasks?: TaskAssignment[];
  overallPriority: "high" | "medium" | "low";
  deadline?: string;
  projectName?: string;
  projectId?: string;
  batchId?: string;
  isActiveLearning?: boolean;
  annotationInterfaceUrl?: string;
  message?: string;
}

const baseStyles = {
  container: {
    fontFamily: "'Segoe UI', Roboto, 'Helvetica Neue', sans-serif",
    backgroundColor: "#f9fafb",
    padding: "20px 0",
  },
  main: {
    backgroundColor: "#ffffff",
    borderRadius: "8px",
    padding: "32px",
    marginBottom: "16px",
    boxShadow: "0 1px 3px rgba(0, 0, 0, 0.1)",
  },
  header: {
    backgroundColor: "#0f172a",
    color: "#ffffff",
    padding: "24px 32px",
    borderRadius: "8px 8px 0 0",
    marginBottom: "24px",
  },
  title: {
    fontSize: "24px",
    fontWeight: "700",
    margin: "0 0 8px 0",
    color: "#ffffff",
  },
  subtitle: {
    fontSize: "14px",
    color: "#cbd5e1",
    margin: "0",
  },
  section: {
    marginBottom: "24px",
  },
  sectionTitle: {
    fontSize: "16px",
    fontWeight: "600",
    color: "#0f172a",
    marginBottom: "12px",
  },
  greeting: {
    fontSize: "16px",
    color: "#1e293b",
    marginBottom: "16px",
    lineHeight: "1.6",
  },
  taskCard: {
    backgroundColor: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: "6px",
    padding: "16px",
    marginBottom: "12px",
  },
  taskTitle: {
    fontSize: "14px",
    fontWeight: "600",
    color: "#0f172a",
    margin: "0 0 8px 0",
  },
  taskMeta: {
    fontSize: "12px",
    color: "#64748b",
    margin: "0",
  },
  priorityHighBadge: {
    display: "inline-block",
    backgroundColor: "#fecaca",
    color: "#991b1b",
    padding: "4px 8px",
    borderRadius: "4px",
    fontSize: "11px",
    fontWeight: "600",
    marginRight: "8px",
  },
  priorityMediumBadge: {
    display: "inline-block",
    backgroundColor: "#fef08a",
    color: "#92400e",
    padding: "4px 8px",
    borderRadius: "4px",
    fontSize: "11px",
    fontWeight: "600",
    marginRight: "8px",
  },
  priorityLowBadge: {
    display: "inline-block",
    backgroundColor: "#bbf7d0",
    color: "#166534",
    padding: "4px 8px",
    borderRadius: "4px",
    fontSize: "11px",
    fontWeight: "600",
    marginRight: "8px",
  },
  statBox: {
    backgroundColor: "#f1f5f9",
    padding: "16px",
    borderRadius: "6px",
    textAlign: "center" as const,
  },
  statNumber: {
    fontSize: "32px",
    fontWeight: "700",
    color: "#0f172a",
    margin: "0",
  },
  statLabel: {
    fontSize: "12px",
    color: "#64748b",
    margin: "4px 0 0 0",
  },
  incentive: {
    backgroundColor: "#ecfdf5",
    borderLeft: "4px solid #10b981",
    padding: "16px",
    borderRadius: "4px",
  },
  incentiveText: {
    fontSize: "13px",
    color: "#047857",
    margin: "0",
    lineHeight: "1.5",
  },
  button: {
    backgroundColor: "#0f172a",
    color: "#ffffff",
    padding: "12px 32px",
    borderRadius: "6px",
    textDecoration: "none",
    fontSize: "14px",
    fontWeight: "600",
    display: "inline-block",
  },
  secondaryButton: {
    backgroundColor: "#f1f5f9",
    color: "#0f172a",
    padding: "12px 32px",
    borderRadius: "6px",
    textDecoration: "none",
    fontSize: "14px",
    fontWeight: "600",
    display: "inline-block",
    border: "1px solid #e2e8f0",
  },
  footer: {
    textAlign: "center" as const,
    fontSize: "12px",
    color: "#64748b",
    marginTop: "24px",
    borderTop: "1px solid #e2e8f0",
    paddingTop: "16px",
  },
};

const getPriorityBadge = (priority: string) => {
  switch (priority) {
    case "high":
      return baseStyles.priorityHighBadge;
    case "medium":
      return baseStyles.priorityMediumBadge;
    default:
      return baseStyles.priorityLowBadge;
  }
};

export function AssignmentNotification({
  annotatorName,
  taskCount,
  tasks = [],
  overallPriority,
  deadline,
  projectName = "AI Data Ops",
  projectId,
  batchId,
  isActiveLearning = false,
  annotationInterfaceUrl = "https://aidata.example.com/tasks",
  message,
}: AssignmentNotificationProps) {
  const displayTasks = tasks.slice(0, 3); // Show first 3 tasks
  const hasMoreTasks = tasks.length > 3;

  return (
    <Html>
      <Head>
        <title>New Task Assignment</title>
      </Head>
      <Body style={baseStyles.container}>
        <Container style={{ maxWidth: "600px", margin: "0 auto" }}>
          {/* Header */}
          <Section style={baseStyles.header}>
            <Text style={baseStyles.title}>
              New Tasks Assigned {isActiveLearning ? "🎯" : "✓"}
            </Text>
            <Text style={baseStyles.subtitle}>
              {taskCount} item{taskCount !== 1 ? "s" : ""} ready for annotation
            </Text>
          </Section>

          {/* Main Content */}
          <Section style={baseStyles.main}>
            {/* Greeting */}
            <Text style={baseStyles.greeting}>
              Hi {annotatorName},
            </Text>

            {isActiveLearning && (
              <div style={baseStyles.incentive}>
                <Text style={baseStyles.incentiveText}>
                  <strong>🎯 Active Learning:</strong> These are high-value uncertain samples
                  from our model. Your annotations will directly improve model performance!
                </Text>
              </div>
            )}

            {message && (
              <Text
                style={{
                  ...baseStyles.greeting,
                  marginTop: "16px",
                  backgroundColor: "#f0fdf4",
                  padding: "12px",
                  borderRadius: "6px",
                  borderLeft: "4px solid #22c55e",
                }}
              >
                {message}
              </Text>
            )}

            <Hr style={{ margin: "24px 0", borderColor: "#e2e8f0" }} />

            {/* Task Summary Stats */}
            <Section style={baseStyles.section}>
              <Row>
                <Column width="50%">
                  <div style={baseStyles.statBox}>
                    <Text style={baseStyles.statNumber}>{taskCount}</Text>
                    <Text style={baseStyles.statLabel}>
                      Task{taskCount !== 1 ? "s" : ""} Assigned
                    </Text>
                  </div>
                </Column>
                <Column width="50%">
                  <div style={baseStyles.statBox}>
                    <Text style={baseStyles.statNumber}>
                      <span style={getPriorityBadge(overallPriority) as any}>
                        {overallPriority.toUpperCase()}
                      </span>
                    </Text>
                    <Text style={baseStyles.statLabel}>Priority Level</Text>
                  </div>
                </Column>
              </Row>
            </Section>

            {/* Deadline Info */}
            {deadline && (
              <Section style={baseStyles.section}>
                <Text style={baseStyles.sectionTitle}>Deadline</Text>
                <div
                  style={{
                    backgroundColor: "#fef3c7",
                    borderLeft: "4px solid #f59e0b",
                    padding: "12px 16px",
                    borderRadius: "4px",
                  }}
                >
                  <Text style={{ margin: "0", color: "#92400e", fontSize: "14px" }}>
                    📅 Complete by <strong>{deadline}</strong>
                  </Text>
                </div>
              </Section>
            )}

            {/* Task List */}
            {displayTasks.length > 0 && (
              <Section style={baseStyles.section}>
                <Text style={baseStyles.sectionTitle}>
                  {displayTasks.length === 1 ? "Your Task" : "Your Tasks"}
                </Text>
                {displayTasks.map((task, index) => (
                  <div key={index} style={baseStyles.taskCard}>
                    <Text style={baseStyles.taskTitle}>{task.title}</Text>
                    <Text style={baseStyles.taskMeta}>
                      <span style={getPriorityBadge(task.priority)}>
                        {task.priority.toUpperCase()}
                      </span>
                      {task.estimatedTime && (
                        <span style={{ marginLeft: "8px" }}>
                          ⏱️ ~{task.estimatedTime} min
                        </span>
                      )}
                    </Text>
                  </div>
                ))}
                {hasMoreTasks && (
                  <Text
                    style={{
                      ...baseStyles.taskMeta,
                      marginTop: "12px",
                      fontStyle: "italic",
                    }}
                  >
                    ... and {tasks.length - 3} more task{tasks.length - 3 !== 1 ? "s" : ""}
                  </Text>
                )}
              </Section>
            )}

            <Hr style={{ margin: "24px 0", borderColor: "#e2e8f0" }} />

            {/* Quick Stats */}
            <Section style={baseStyles.section}>
              <Text style={baseStyles.sectionTitle}>Quick Info</Text>
              <Row>
                <Column width="50%">
                  <Text style={{ ...baseStyles.taskMeta, margin: "8px 0" }}>
                    <strong>Project:</strong> {projectName}
                  </Text>
                </Column>
                <Column width="50%">
                  {batchId && (
                    <Text style={{ ...baseStyles.taskMeta, margin: "8px 0" }}>
                      <strong>Batch:</strong> {batchId}
                    </Text>
                  )}
                </Column>
              </Row>
            </Section>

            {/* CTA Buttons */}
            <Row style={{ textAlign: "center", marginTop: "24px" }}>
              <Column>
                <Button href={annotationInterfaceUrl} style={baseStyles.button}>
                  Start Annotating
                </Button>
              </Column>
            </Row>

            <Row style={{ textAlign: "center", marginTop: "12px" }}>
              <Column>
                <Link
                  href={annotationInterfaceUrl}
                  style={{
                    ...baseStyles.secondaryButton,
                    textDecoration: "none",
                  }}
                >
                  View All Tasks
                </Link>
              </Column>
            </Row>

            {/* Help Section */}
            <Section
              style={{
                ...baseStyles.section,
                backgroundColor: "#f8fafc",
                padding: "16px",
                borderRadius: "6px",
                marginTop: "24px",
              }}
            >
              <Text style={{ ...baseStyles.sectionTitle, marginBottom: "8px" }}>
                Need Help?
              </Text>
              <Text style={{ ...baseStyles.taskMeta, lineHeight: "1.6" }}>
                Check our{" "}
                <Link
                  href="https://aidata.example.com/docs/annotation-guide"
                  style={{ color: "#0f172a", fontWeight: "600" }}
                >
                  annotation guide
                </Link>{" "}
                or reach out to{" "}
                <Link
                  href="mailto:support@aidata.example.com"
                  style={{ color: "#0f172a", fontWeight: "600" }}
                >
                  support@aidata.example.com
                </Link>
              </Text>
            </Section>
          </Section>

          {/* Footer */}
          <Section style={baseStyles.footer}>
            <Text>
              You're receiving this because you have active assignments in{" "}
              <strong>{projectName}</strong>
            </Text>
            <Text style={{ margin: "8px 0 0 0" }}>
              Questions? Check the{" "}
              <Link
                href="https://aidata.example.com/faq"
                style={{ color: "#0f172a" }}
              >
                FAQ
              </Link>{" "}
              or email{" "}
              <Link
                href="mailto:support@aidata.example.com"
                style={{ color: "#0f172a" }}
              >
                support
              </Link>
            </Text>
          </Section>
        </Container>
      </Body>
    </Html>
  );
}

export default AssignmentNotification;
