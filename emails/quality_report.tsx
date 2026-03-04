/**
 * Quality Report Email Template
 *
 * Renders a professional quality score report for a completed batch.
 * Uses Resend React Email components for responsive design.
 *
 * Usage:
 * const html = render(<QualityReport {...data} />);
 * await resend.emails.send({
 *   from: "reports@aidata.example.com",
 *   to: user.email,
 *   subject: "Batch Quality Report",
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

interface AnnotatorPerformance {
  name: string;
  accuracy: number;
  annotations_count: number;
  f1_score?: number;
  skill_level: string;
}

interface QualityReportProps {
  projectName: string;
  batchId: string;
  batchSize: number;
  qualityScore: number;
  qualityStatus: "passed" | "failed";
  agreementMetric: string;
  goldenSetAccuracy: number;
  consensusResolutionRate: number;
  annotatorPerformance: AnnotatorPerformance[];
  reportDate: string;
  actionItems?: string[];
  dashboardUrl?: string;
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
    fontSize: "28px",
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
  metric: {
    backgroundColor: "#f1f5f9",
    padding: "12px",
    borderRadius: "6px",
    marginBottom: "8px",
  },
  metricLabel: {
    fontSize: "12px",
    color: "#64748b",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
    margin: "0 0 4px 0",
  },
  metricValue: {
    fontSize: "24px",
    fontWeight: "700",
    color: "#0f172a",
    margin: "0",
  },
  statusPassed: {
    backgroundColor: "#dcfce7",
    color: "#166534",
  },
  statusFailed: {
    backgroundColor: "#fee2e2",
    color: "#991b1b",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse" as const,
    marginTop: "12px",
  },
  tableHeader: {
    backgroundColor: "#f1f5f9",
    borderBottom: "2px solid #e2e8f0",
    padding: "12px",
    textAlign: "left" as const,
    fontSize: "12px",
    fontWeight: "600",
    color: "#475569",
  },
  tableRow: {
    borderBottom: "1px solid #e2e8f0",
  },
  tableCell: {
    padding: "12px",
    fontSize: "13px",
    color: "#1e293b",
  },
  badge: {
    display: "inline-block",
    padding: "4px 8px",
    borderRadius: "4px",
    fontSize: "11px",
    fontWeight: "600",
    textTransform: "uppercase" as const,
  },
  expertBadge: {
    backgroundColor: "#fef3c7",
    color: "#92400e",
  },
  seniorBadge: {
    backgroundColor: "#dbeafe",
    color: "#0c4a6e",
  },
  juniorBadge: {
    backgroundColor: "#f0fdf4",
    color: "#166534",
  },
  actionItem: {
    backgroundColor: "#f0fdf4",
    borderLeft: "4px solid #22c55e",
    padding: "12px",
    marginBottom: "8px",
  },
  actionText: {
    margin: "0",
    fontSize: "13px",
    color: "#166534",
  },
  button: {
    backgroundColor: "#0f172a",
    color: "#ffffff",
    padding: "12px 24px",
    borderRadius: "6px",
    textDecoration: "none",
    fontSize: "14px",
    fontWeight: "600",
    display: "inline-block",
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

export function QualityReport({
  projectName,
  batchId,
  batchSize,
  qualityScore,
  qualityStatus,
  agreementMetric,
  goldenSetAccuracy,
  consensusResolutionRate,
  annotatorPerformance,
  reportDate,
  actionItems = [],
  dashboardUrl = "https://aidata.example.com/dashboard",
}: QualityReportProps) {
  const qualityScorePercent = Math.round(qualityScore * 100);
  const goldenAccuracyPercent = Math.round(goldenSetAccuracy * 100);
  const consensusRatePercent = Math.round(consensusResolutionRate * 100);

  const getSkillBadgeStyle = (skillLevel: string) => {
    switch (skillLevel) {
      case "expert":
        return baseStyles.expertBadge;
      case "senior":
        return baseStyles.seniorBadge;
      default:
        return baseStyles.juniorBadge;
    }
  };

  return (
    <Html>
      <Head>
        <title>Batch Quality Report</title>
      </Head>
      <Body style={baseStyles.container}>
        <Container style={{ maxWidth: "600px", margin: "0 auto" }}>
          {/* Header */}
          <Section style={baseStyles.header}>
            <Text style={baseStyles.title}>
              Quality Report {qualityStatus === "passed" ? "✓" : "⚠️"}
            </Text>
            <Text style={baseStyles.subtitle}>
              Batch {batchId} • {reportDate}
            </Text>
          </Section>

          {/* Main Content */}
          <Section style={baseStyles.main}>
            {/* Status Badge */}
            <Row>
              <Column>
                <div
                  style={{
                    ...baseStyles.metric,
                    ...(qualityStatus === "passed"
                      ? baseStyles.statusPassed
                      : baseStyles.statusFailed),
                    padding: "16px",
                  }}
                >
                  <Text
                    style={{
                      ...baseStyles.metricLabel,
                      color: "inherit",
                    }}
                  >
                    Overall Status
                  </Text>
                  <Text
                    style={{
                      ...baseStyles.metricValue,
                      color: "inherit",
                    }}
                  >
                    {qualityStatus === "passed" ? "PASSED" : "NEEDS REVIEW"}
                  </Text>
                </div>
              </Column>
            </Row>

            {/* Key Metrics Grid */}
            <Section style={baseStyles.section}>
              <Text style={baseStyles.sectionTitle}>Key Metrics</Text>

              <Row>
                <Column width="50%">
                  <div style={baseStyles.metric}>
                    <Text style={baseStyles.metricLabel}>Quality Score</Text>
                    <Text style={baseStyles.metricValue}>
                      {qualityScorePercent}%
                    </Text>
                    <Text
                      style={{
                        fontSize: "12px",
                        color: "#64748b",
                        margin: "4px 0 0 0",
                      }}
                    >
                      {agreementMetric}
                    </Text>
                  </div>
                </Column>
                <Column width="50%">
                  <div style={baseStyles.metric}>
                    <Text style={baseStyles.metricLabel}>Golden Set</Text>
                    <Text style={baseStyles.metricValue}>
                      {goldenAccuracyPercent}%
                    </Text>
                    <Text
                      style={{
                        fontSize: "12px",
                        color: "#64748b",
                        margin: "4px 0 0 0",
                      }}
                    >
                      Accuracy
                    </Text>
                  </div>
                </Column>
              </Row>

              <Row>
                <Column width="50%">
                  <div style={baseStyles.metric}>
                    <Text style={baseStyles.metricLabel}>Items Labeled</Text>
                    <Text style={baseStyles.metricValue}>{batchSize}</Text>
                    <Text
                      style={{
                        fontSize: "12px",
                        color: "#64748b",
                        margin: "4px 0 0 0",
                      }}
                    >
                      Total annotations
                    </Text>
                  </div>
                </Column>
                <Column width="50%">
                  <div style={baseStyles.metric}>
                    <Text style={baseStyles.metricLabel}>
                      Auto-Resolution
                    </Text>
                    <Text style={baseStyles.metricValue}>
                      {consensusRatePercent}%
                    </Text>
                    <Text
                      style={{
                        fontSize: "12px",
                        color: "#64748b",
                        margin: "4px 0 0 0",
                      }}
                    >
                      No escalation
                    </Text>
                  </div>
                </Column>
              </Row>
            </Section>

            <Hr style={{ margin: "24px 0", borderColor: "#e2e8f0" }} />

            {/* Annotator Performance */}
            <Section style={baseStyles.section}>
              <Text style={baseStyles.sectionTitle}>Annotator Performance</Text>

              <table style={baseStyles.table}>
                <thead>
                  <tr style={baseStyles.tableRow}>
                    <th style={baseStyles.tableHeader}>Annotator</th>
                    <th style={baseStyles.tableHeader}>Accuracy</th>
                    <th style={baseStyles.tableHeader}>Count</th>
                    <th style={baseStyles.tableHeader}>Level</th>
                  </tr>
                </thead>
                <tbody>
                  {annotatorPerformance.map((perf, index) => (
                    <tr key={index} style={baseStyles.tableRow}>
                      <td style={baseStyles.tableCell}>{perf.name}</td>
                      <td style={baseStyles.tableCell}>
                        {Math.round(perf.accuracy * 100)}%
                      </td>
                      <td style={baseStyles.tableCell}>
                        {perf.annotations_count}
                      </td>
                      <td style={baseStyles.tableCell}>
                        <span
                          style={{
                            ...baseStyles.badge,
                            ...getSkillBadgeStyle(perf.skill_level),
                          }}
                        >
                          {perf.skill_level}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>

            {/* Action Items */}
            {actionItems.length > 0 && (
              <>
                <Hr style={{ margin: "24px 0", borderColor: "#e2e8f0" }} />
                <Section style={baseStyles.section}>
                  <Text style={baseStyles.sectionTitle}>Recommended Actions</Text>
                  {actionItems.map((item, index) => (
                    <div key={index} style={baseStyles.actionItem}>
                      <Text style={baseStyles.actionText}>• {item}</Text>
                    </div>
                  ))}
                </Section>
              </>
            )}

            {/* CTA Button */}
            <Row>
              <Column align="center">
                <Button
                  href={dashboardUrl}
                  style={{
                    ...baseStyles.button,
                    marginTop: "24px",
                  }}
                >
                  View Full Report
                </Button>
              </Column>
            </Row>
          </Section>

          {/* Footer */}
          <Section style={baseStyles.footer}>
            <Text>
              Project: <strong>{projectName}</strong>
            </Text>
            <Text style={{ margin: "8px 0 0 0" }}>
              This is an automated report from the AI Data Operations Platform.{" "}
              <Link href={dashboardUrl} style={{ color: "#0f172a" }}>
                Visit Dashboard
              </Link>
            </Text>
          </Section>
        </Container>
      </Body>
    </Html>
  );
}

export default QualityReport;
