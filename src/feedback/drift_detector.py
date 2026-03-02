"""
Drift Detector: Production data distribution monitoring.

Compares production data distributions against training data to detect
drift that could degrade model performance. Uses three-window
confirmation to eliminate false positives before triggering
re-annotation (DEC-010).

Metrics monitored:
- Feature distribution: KL divergence per feature
- Prediction distribution: Population Stability Index (PSI)
- Embedding drift: cosine distance between centroids

Key design decisions:
- Three-window confirmation eliminates false positives (DEC-010)
- PSI > 0.5 bypasses confirmation for dramatic shifts
- Weekly snapshots balance detection speed and compute cost
- Re-annotation requests auto-generated on confirmed drift

PM context: Single-window alerting generated 12 alerts in the first
month; 9 were transient (weekend traffic patterns, batch artifacts).
The annotation team lost trust in drift alerts within a week. Three-
window confirmation eliminated all 9 false positives while detecting
all 3 genuine shifts with only a 2-week delay. That analysis (DEC-010)
justified the confirmation approach.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import UUID, uuid4


@dataclass
class DistributionSnapshot:
    """Point-in-time capture of a data distribution."""
    snapshot_id: UUID
    project_id: UUID
    window_start: datetime
    window_end: datetime
    feature_distributions: dict[str, dict[str, float]] = field(default_factory=dict)
    prediction_distribution: dict[str, float] = field(default_factory=dict)
    embedding_centroid: Optional[list[float]] = None
    sample_size: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DriftResult:
    """Result of drift analysis for one snapshot window."""
    snapshot_id: UUID
    project_id: UUID
    feature_kl_divergence: dict[str, float] = field(default_factory=dict)
    prediction_psi: float = 0.0
    embedding_centroid_distance: float = 0.0
    drift_detected: bool = False
    severity: str = "none"
    drifted_features: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DriftAlert:
    """Alert generated when sustained drift is confirmed."""
    alert_id: UUID
    project_id: UUID
    severity: str
    consecutive_windows: int
    avg_psi: float
    drifted_features: list[str]
    recommended_reannot_volume: int
    auto_reannot_triggered: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DriftDetector:
    """
    Monitors production data for distribution drift.

    Detection flow:
    1. Weekly: compute snapshot of production data distribution
    2. Compare snapshot to training baseline
    3. If drift detected in single window: log but do not alert
    4. If drift persists for 3 consecutive windows: confirm and alert
    5. Alert triggers re-annotation request for shifted distribution

    Exception: PSI > 0.5 (dramatic shift) bypasses 3-window rule.
    """

    PSI_LOW = 0.10
    PSI_MODERATE = 0.20
    PSI_SEVERE = 0.50
    KL_WARNING = 0.10
    KL_ALERT = 0.25
    CONFIRMATION_WINDOWS = 3
    REANNOT_BASE_SIZE = 500
    REANNOT_SEVERE_MULTIPLIER = 3

    def __init__(self):
        self.baselines: dict[UUID, DistributionSnapshot] = {}
        self.history: dict[UUID, list[DriftResult]] = {}
        self.alerts: list[DriftAlert] = []

    def set_baseline(self, project_id: UUID, snapshot: DistributionSnapshot) -> None:
        """Set the training data distribution as baseline."""
        self.baselines[project_id] = snapshot

    def analyze_snapshot(
        self, production_snapshot: DistributionSnapshot,
    ) -> DriftResult:
        """
        Compare a production snapshot against the training baseline.
        Returns drift analysis with per-feature and aggregate metrics.
        """
        project_id = production_snapshot.project_id
        baseline = self.baselines.get(project_id)

        result = DriftResult(
            snapshot_id=production_snapshot.snapshot_id,
            project_id=project_id,
        )

        if baseline is None:
            return result

        # Feature-level KL divergence
        for feature_name in baseline.feature_distributions:
            if feature_name in production_snapshot.feature_distributions:
                kl = self._kl_divergence(
                    baseline.feature_distributions[feature_name],
                    production_snapshot.feature_distributions[feature_name],
                )
                result.feature_kl_divergence[feature_name] = round(kl, 4)
                if kl > self.KL_ALERT:
                    result.drifted_features.append(feature_name)

        # Prediction distribution PSI
        if baseline.prediction_distribution and production_snapshot.prediction_distribution:
            result.prediction_psi = round(self._psi(
                baseline.prediction_distribution,
                production_snapshot.prediction_distribution,
            ), 4)

        # Embedding centroid distance
        if baseline.embedding_centroid and production_snapshot.embedding_centroid:
            result.embedding_centroid_distance = round(self._cosine_distance(
                baseline.embedding_centroid,
                production_snapshot.embedding_centroid,
            ), 4)

        # Assess severity
        if result.prediction_psi >= self.PSI_SEVERE:
            result.drift_detected = True
            result.severity = "severe"
        elif result.prediction_psi >= self.PSI_MODERATE:
            result.drift_detected = True
            result.severity = "moderate"
        elif result.prediction_psi >= self.PSI_LOW or result.drifted_features:
            result.drift_detected = True
            result.severity = "low"

        if project_id not in self.history:
            self.history[project_id] = []
        self.history[project_id].append(result)

        return result

    def check_sustained_drift(self, project_id: UUID) -> Optional[DriftAlert]:
        """
        Check if drift has been sustained across N consecutive windows.

        DEC-010: Three-window confirmation eliminates false positives.
        Exception: severe drift (PSI > 0.5) triggers immediate alert.
        """
        history = self.history.get(project_id, [])
        if not history:
            return None

        latest = history[-1]

        # Immediate alert for severe drift (bypass confirmation)
        if latest.severity == "severe":
            alert = DriftAlert(
                alert_id=uuid4(), project_id=project_id,
                severity="severe", consecutive_windows=1,
                avg_psi=latest.prediction_psi,
                drifted_features=latest.drifted_features,
                recommended_reannot_volume=self.REANNOT_BASE_SIZE * self.REANNOT_SEVERE_MULTIPLIER,
                auto_reannot_triggered=True,
            )
            self.alerts.append(alert)
            return alert

        # Check consecutive drift windows
        consecutive = 0
        psi_values = []
        for result in reversed(history):
            if result.drift_detected:
                consecutive += 1
                psi_values.append(result.prediction_psi)
            else:
                break

        if consecutive >= self.CONFIRMATION_WINDOWS:
            avg_psi = sum(psi_values) / len(psi_values)
            reannot_volume = self.REANNOT_BASE_SIZE
            if avg_psi >= self.PSI_MODERATE:
                reannot_volume *= 2

            all_drifted = set()
            for r in history[-consecutive:]:
                all_drifted.update(r.drifted_features)

            alert = DriftAlert(
                alert_id=uuid4(), project_id=project_id,
                severity="moderate" if avg_psi >= self.PSI_MODERATE else "low",
                consecutive_windows=consecutive,
                avg_psi=round(avg_psi, 4),
                drifted_features=list(all_drifted),
                recommended_reannot_volume=reannot_volume,
                auto_reannot_triggered=True,
            )
            self.alerts.append(alert)
            return alert

        return None

    def get_drift_summary(self, project_id: UUID) -> dict[str, Any]:
        """Drift monitoring summary for dashboard."""
        history = self.history.get(project_id, [])
        if not history:
            return {"project_id": str(project_id), "snapshots": 0}

        latest = history[-1]
        consecutive = 0
        for result in reversed(history):
            if result.drift_detected:
                consecutive += 1
            else:
                break

        return {
            "project_id": str(project_id),
            "snapshots_analyzed": len(history),
            "latest_psi": latest.prediction_psi,
            "latest_severity": latest.severity,
            "consecutive_drift_windows": consecutive,
            "confirmation_threshold": self.CONFIRMATION_WINDOWS,
            "drifted_features": latest.drifted_features,
            "alerts_generated": len([a for a in self.alerts if a.project_id == project_id]),
        }

    # ------------------------------------------------------------------
    # Statistical methods
    # ------------------------------------------------------------------

    def _kl_divergence(self, baseline: dict[str, float], production: dict[str, float]) -> float:
        """KL divergence between two discrete distributions."""
        all_keys = set(baseline.keys()) | set(production.keys())
        total_b = sum(baseline.values()) or 1
        total_p = sum(production.values()) or 1
        epsilon = 1e-10

        kl = 0.0
        for key in all_keys:
            p = (production.get(key, 0) / total_p) + epsilon
            q = (baseline.get(key, 0) / total_b) + epsilon
            kl += p * math.log(p / q)
        return max(0.0, kl)

    def _psi(self, baseline: dict[str, float], production: dict[str, float]) -> float:
        """Population Stability Index between two distributions."""
        all_keys = set(baseline.keys()) | set(production.keys())
        total_b = sum(baseline.values()) or 1
        total_p = sum(production.values()) or 1
        epsilon = 1e-10

        psi = 0.0
        for key in all_keys:
            p = (production.get(key, 0) / total_p) + epsilon
            q = (baseline.get(key, 0) / total_b) + epsilon
            psi += (p - q) * math.log(p / q)
        return max(0.0, psi)

    def _cosine_distance(self, vec_a: list[float], vec_b: list[float]) -> float:
        """Cosine distance (1 - cosine_similarity)."""
        if len(vec_a) != len(vec_b) or not vec_a:
            return 1.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 1.0
        return max(0.0, 1.0 - dot / (norm_a * norm_b))


if __name__ == "__main__":
    detector = DriftDetector()
    project_id = uuid4()

    print("=== Drift Detector Demo ===\n")

    baseline = DistributionSnapshot(
        snapshot_id=uuid4(), project_id=project_id,
        window_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        window_end=datetime(2024, 6, 1, tzinfo=timezone.utc),
        feature_distributions={
            "transaction_type": {"online": 60, "in_store": 30, "atm": 10},
            "amount_bucket": {"low": 50, "medium": 35, "high": 15},
        },
        prediction_distribution={"fraud": 8, "legitimate": 92},
        embedding_centroid=[0.1, 0.3, -0.2, 0.5],
        sample_size=10000,
    )
    detector.set_baseline(project_id, baseline)
    print("Baseline set: 10,000 samples")

    for week in range(4):
        online_pct = 60 + week * 8
        snapshot = DistributionSnapshot(
            snapshot_id=uuid4(), project_id=project_id,
            window_start=datetime(2024, 7, 1 + week * 7, tzinfo=timezone.utc),
            window_end=datetime(2024, 7, 7 + week * 7, tzinfo=timezone.utc),
            feature_distributions={
                "transaction_type": {"online": online_pct, "in_store": 100 - online_pct - 5, "atm": 5},
                "amount_bucket": {"low": 45, "medium": 35, "high": 20},
            },
            prediction_distribution={"fraud": 8 + week * 2, "legitimate": 92 - week * 2},
            embedding_centroid=[0.1 + week * 0.05, 0.3, -0.2, 0.5 - week * 0.03],
            sample_size=2000,
        )
        result = detector.analyze_snapshot(snapshot)
        print(f"Week {week + 1}: PSI={result.prediction_psi}, severity={result.severity}")

        alert = detector.check_sustained_drift(project_id)
        if alert:
            print(f"  ALERT: {alert.severity} drift after {alert.consecutive_windows} windows")
            print(f"  Recommended re-annotation: {alert.recommended_reannot_volume} items")

    print(f"\nSummary: {detector.get_drift_summary(project_id)}")
