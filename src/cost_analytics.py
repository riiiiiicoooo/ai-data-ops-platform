"""
Annotation Cost Analytics — Economic visibility for data labeling operations.

In annotation platforms, cost-per-label can vary 5-10x based on workflow design:
- Simple single-annotator classification: $0.10 per label
- Expert multi-stage consensus: $2.50 per label (quality overhead)
- Active learning + single-pass: $0.05 per label (efficiency gain)

This module surfaces the economic impact of quality choices and recommends
optimal configurations for cost-sensitive, quality-aware operations.

Design principles:
- Cost-per-label is the north star metric (total cost / total labels)
- Active learning saves money: fewer labels, same quality
- Consensus has a cost: 2-stage review is 2.4x expensive vs single-stage
- Golden sets have diminishing returns: 10% golden rate may be overkill
- Drift detection frequency should match data stability (not all projects need weekly checks)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from datetime import datetime, timedelta
from collections import defaultdict
import math


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AnnotatorTier(Enum):
    """Annotator experience and accuracy levels."""
    JUNIOR = "junior"      # 0-6 months, 85-90% accuracy
    MID = "mid"            # 6-18 months, 90-95% accuracy
    SENIOR = "senior"      # 18+ months, 95%+ accuracy


class ProjectType(Enum):
    """Classification of annotation project by complexity."""
    SIMPLE = "simple"              # Single label, clear categories (5-10s per item)
    MODERATE = "moderate"          # Multi-field, some ambiguity (20-60s per item)
    COMPLEX = "complex"            # Multi-stage, high ambiguity, expert (2-5min per item)


class DriftDetectionFrequency(Enum):
    """How often drift checks should run."""
    WEEKLY = "weekly"              # High volatility data
    BIWEEKLY = "biweekly"         # Moderate change
    MONTHLY = "monthly"           # Stable data
    QUARTERLY = "quarterly"       # Very stable data


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class AnnotatorProfile:
    """Profile of an annotator including cost and accuracy metrics."""
    annotator_id: str
    tier: AnnotatorTier
    hourly_rate: float  # USD per hour
    accuracy_rate: float  # 0.0-1.0, measured on golden set
    items_per_hour: int  # Typical throughput
    total_annotations: int = 0
    golden_set_accuracy: Optional[float] = None
    months_experience: int = 0


@dataclass
class LabelingCost:
    """Cost breakdown for a single labeled item."""
    annotator_time_cost: float
    consensus_overhead_cost: float = 0.0
    golden_set_review_cost: float = 0.0
    quality_assurance_cost: float = 0.0
    total_cost: float = 0.0


@dataclass
class ActiveLearningMetrics:
    """Metrics tracking the efficiency gains from active learning."""
    project_id: str
    total_labels_needed_naive: int  # If annotating randomly
    total_labels_with_al: int  # Actual labels with active learning
    labels_saved: int
    cost_per_label_without_al: float
    cost_per_label_with_al: float
    total_savings: float
    efficiency_ratio: float  # 2.4x = saved 58% of labels at same quality


@dataclass
class ConsensusOptimization:
    """Analysis of consensus workflow efficiency."""
    project_id: str
    single_annotator_cost: float  # Cost for one-pass annotation
    two_stage_consensus_cost: float  # Cost for 2-stage (disagreement resolution)
    three_stage_consensus_cost: float  # Cost for 3-stage (expert adjudication)
    optimal_consensus_stages: int
    optimal_overlap_percentage: float  # What % of items get reviewed
    recommended_configuration: str


@dataclass
class GoldenSetOptimization:
    """Analysis of golden set sizing for quality evaluation."""
    project_id: str
    annotator_id: str
    current_golden_rate: float  # % of their work that's golden
    annotator_accuracy: float
    recommended_golden_rate: float
    current_golden_set_cost: float
    optimized_golden_set_cost: float
    monthly_savings: float
    reasoning: str


@dataclass
class ThroughputCostFrontier:
    """Pareto-optimal configurations balancing quality and cost."""
    configurations: List[Dict[str, Any]]  # List of {quality_score, cost_per_label, config_name, ...}
    optimal_config: Dict[str, Any]  # Recommended config
    budget_constrained_config: Optional[Dict[str, Any]] = None
    quality_constrained_config: Optional[Dict[str, Any]] = None


@dataclass
class DriftDetectionOptimization:
    """Recommendation for drift check frequency based on data stability."""
    project_id: str
    current_check_frequency: DriftDetectionFrequency
    current_check_cost_monthly: float
    data_stability_score: float  # 0-1, higher = more stable
    recommended_frequency: DriftDetectionFrequency
    recommended_check_cost_monthly: float
    monthly_savings: float
    reasoning: str


@dataclass
class CostEfficiencyReport:
    """Comprehensive cost analysis for a project."""
    project_id: str
    total_labels: int
    average_cost_per_label: float
    total_project_cost: float
    cost_breakdown: Dict[str, float]  # {"annotator_time": X, "consensus": Y, ...}
    efficiency_metrics: Dict[str, Any]
    optimization_recommendations: List[str]
    monthly_burn_rate: float


# ---------------------------------------------------------------------------
# Main Analytics Class
# ---------------------------------------------------------------------------

class AnnotationCostAnalytics:
    """
    Measures and optimizes the cost of annotation operations.

    This is the economic engine for data labeling: it translates quality
    requirements (need 95% accuracy) into minimum cost (need 2-stage consensus)
    and identifies where cost can be cut without sacrificing quality.
    """

    def __init__(self):
        """Initialize the analytics engine."""
        self.annotators: Dict[str, AnnotatorProfile] = {}
        self.projects: Dict[str, Dict[str, Any]] = {}
        self.cost_history: List[Dict[str, Any]] = []
        self.optimization_history: List[Dict[str, Any]] = []

    # -----------------------------------------------------------------------
    # Core Cost Analysis Methods
    # -----------------------------------------------------------------------

    def cost_per_label(
        self,
        project_id: str,
        total_cost: float,
        total_labels: int,
    ) -> float:
        """
        Calculate the cost per label for a project.

        Args:
            project_id: Project identifier
            total_cost: Total cost spent on project (all annotators, QA, etc.)
            total_labels: Total number of labels produced

        Returns:
            Cost per label in USD

        This is the top-level efficiency metric. Track it over time to see
        if optimization efforts are working.

        Example:
        - Project: Image classification (5 classes)
        - Total cost: $5,000 (3 annotators × 40 hours × $40/hr average)
        - Total labels: 50,000 images
        - Cost per label: $0.10
        """
        if total_labels == 0:
            return 0.0

        cost_per = total_cost / total_labels
        self.projects[project_id] = {
            "total_cost": total_cost,
            "total_labels": total_labels,
            "cost_per_label": cost_per,
            "timestamp": datetime.now(),
        }
        return cost_per

    def active_learning_roi(
        self,
        project_id: str,
        labels_saved_by_al: int,
        cost_per_label: float,
    ) -> ActiveLearningMetrics:
        """
        Calculate ROI from active learning.

        Args:
            project_id: Project identifier
            labels_saved_by_al: Number of labels that didn't need to be manually annotated
                                (due to AL model confidence or uncertainty sampling)
            cost_per_label: Cost per label for this project

        Returns:
            ActiveLearningMetrics with savings breakdown

        Logic:
        Active learning saves money by:
        1. Model predicts labels on unlabeled data
        2. Only uncertain predictions sent to annotators
        3. This reduces total manual labels needed by 30-60%

        Example:
        - Train on 1,000 labeled images
        - Use AL to score remaining 9,000
        - AL identifies 5,000 images with high confidence (don't label)
        - Annotate only 4,000 images (expert review on uncertain)
        - Total labels: 5,000 (vs 9,000 needed without AL)
        - Cost: $500 (vs $900 without AL)
        - Savings: $400 (44% cost reduction, same 95% quality)
        """
        # Typical efficiency: 2.0x-2.4x (save 50-58% of labels)
        total_labels_without_al = labels_saved_by_al + 10000  # Placeholder
        cost_without_al = total_labels_without_al * cost_per_label
        cost_with_al = (total_labels_without_al - labels_saved_by_al) * cost_per_label

        total_savings = cost_without_al - cost_with_al
        efficiency_ratio = total_labels_without_al / (total_labels_without_al - labels_saved_by_al) if labels_saved_by_al < total_labels_without_al else 1.0

        metrics = ActiveLearningMetrics(
            project_id=project_id,
            total_labels_needed_naive=total_labels_without_al,
            total_labels_with_al=total_labels_without_al - labels_saved_by_al,
            labels_saved=labels_saved_by_al,
            cost_per_label_without_al=cost_per_label,
            cost_per_label_with_al=cost_per_label,  # Same cost per annotated label
            total_savings=total_savings,
            efficiency_ratio=efficiency_ratio,
        )

        self.optimization_history.append({
            "type": "active_learning",
            "project_id": project_id,
            "savings": total_savings,
            "timestamp": datetime.now(),
        })

        return metrics

    def consensus_overhead_analysis(
        self,
        project_id: str,
        annotators: List[AnnotatorProfile],
        overlap_percentage: float = 0.20,  # 20% of items reviewed by 2+ annotators
        disagreement_resolution_multiplier: float = 1.5,  # Expert review is 1.5x cost of annotation
    ) -> ConsensusOptimization:
        """
        Analyze the cost of consensus/review workflows.

        Args:
            project_id: Project identifier
            annotators: List of annotators involved
            overlap_percentage: What percentage of items get consensus review
            disagreement_resolution_multiplier: Cost of resolving disagreements

        Returns:
            ConsensusOptimization with configuration recommendations

        Logic:
        Consensus workflows improve quality but add cost:
        - Single pass: fastest, cheapest, lowest quality
        - 2-stage (annotate + review): medium cost, improved quality
        - 3-stage (annotate + review + expert adjudicate): highest cost, best quality

        Decision framework:
        - Low-risk classification (spam detection): single-pass okay
        - High-quality ML training data: 2-stage (10-20% review rate)
        - Medical/legal annotation: 3-stage (50%+ review rate)

        Cost calculation for 2-stage workflow:
        - Stage 1: All annotators label items → cost = n_items × cost_per_item
        - Stage 2: 20% of items reviewed by second annotator
          - If agreement: no additional cost
          - If disagreement: expert adjudicates (1.5x cost of single annotation)
        - Typical: ~30% of reviewed items have disagreement
        - Stage 2 cost = 0.20 × n_items × cost_per_item × (1 + 0.3 × 1.5)
        """
        # Calculate annotator costs
        avg_hourly_rate = sum(a.hourly_rate for a in annotators) / len(annotators) if annotators else 40
        items_per_hour = sum(a.items_per_hour for a in annotators) / len(annotators) if annotators else 10
        cost_per_item = avg_hourly_rate / items_per_hour

        # Single-pass cost
        assumed_items = 10000  # Use for comparison
        single_pass_cost = assumed_items * cost_per_item

        # 2-stage cost (additional review on subset)
        review_items = assumed_items * overlap_percentage
        disagreement_rate = 0.25  # Typical: 25% of reviews find disagreement
        adjudication_items = review_items * disagreement_rate
        two_stage_cost = single_pass_cost + (review_items * cost_per_item) + (
            adjudication_items * cost_per_item * disagreement_resolution_multiplier
        )

        # 3-stage cost (full expert review)
        three_stage_cost = single_pass_cost + (assumed_items * cost_per_item) + (
            assumed_items * cost_per_item * 0.5  # Expert review on all
        )

        # Recommendation: optimal stages + overlap
        recommended_stages = 2 if cost_per_item < 1.0 else 1  # 2-stage if items are cheap
        recommended_overlap = 0.15 if cost_per_item < 1.0 else 0.05

        optimization = ConsensusOptimization(
            project_id=project_id,
            single_annotator_cost=single_pass_cost,
            two_stage_consensus_cost=two_stage_cost,
            three_stage_consensus_cost=three_stage_cost,
            optimal_consensus_stages=recommended_stages,
            optimal_overlap_percentage=recommended_overlap,
            recommended_configuration=f"{recommended_stages}-stage consensus, {recommended_overlap*100:.0f}% overlap",
        )

        self.optimization_history.append({
            "type": "consensus",
            "project_id": project_id,
            "savings": single_pass_cost - two_stage_cost if recommended_stages == 1 else 0,
            "timestamp": datetime.now(),
        })

        return optimization

    def golden_set_optimization(
        self,
        project_id: str,
        annotator_id: str,
        annotator_accuracy: float,
        current_golden_rate: float,
        cost_per_label: float,
    ) -> GoldenSetOptimization:
        """
        Recommend optimal golden set rate for quality evaluation.

        Args:
            project_id: Project identifier
            annotator_id: Annotator to analyze
            annotator_accuracy: Measured accuracy on golden set
            current_golden_rate: Current % of work that's golden (e.g., 0.10 = 10%)
            cost_per_label: Cost per label in project

        Returns:
            GoldenSetOptimization with recommendation

        Logic:
        Golden sets are expensive (items pre-labeled by experts, used to check
        annotator quality). But diminishing returns: if annotator is 95% accurate,
        do you need 10% golden set or 2%?

        Confidence interval math:
        - Accuracy X, N trials, confidence 95%: need ~N = 370/(e^2) samples
        - If want to detect 2% accuracy drop with 95% confidence: need ~370 samples
        - If annotator is JUNIOR (90% → need 10% golden to catch drops)
        - If annotator is SENIOR (95% → need 2% golden, drops are rarer)

        Example:
        - Annotator: senior, 97% accuracy
        - Current golden rate: 10% of 10,000 work = 1,000 items at $0.10 = $100
        - To detect 2% drop with 95% confidence: need ~300 samples
        - Recommended golden rate: 3% of 10,000 = 300 items = $30
        - Savings: $70 per 10,000 items (~7% efficiency gain)
        """
        # Determine required golden rate based on accuracy
        if annotator_accuracy >= 0.95:
            recommended_golden_rate = 0.02  # 2% for senior annotators
            reasoning = "Senior annotator (95%+ accuracy). 2% golden set sufficient to detect quality issues."
        elif annotator_accuracy >= 0.90:
            recommended_golden_rate = 0.05  # 5% for mid-level
            reasoning = "Mid-level annotator (90-95% accuracy). 5% golden set provides good coverage."
        else:
            recommended_golden_rate = 0.10  # 10% for junior
            reasoning = "Junior annotator (<90% accuracy). 10% golden set needed for close monitoring."

        # Calculate costs
        assumed_annual_labels = 50000  # Use for comparison
        current_golden_labels = assumed_annual_labels * current_golden_rate
        current_golden_cost = current_golden_labels * cost_per_label

        optimized_golden_labels = assumed_annual_labels * recommended_golden_rate
        optimized_golden_cost = optimized_golden_labels * cost_per_label

        monthly_savings = (current_golden_cost - optimized_golden_cost) / 12

        optimization = GoldenSetOptimization(
            project_id=project_id,
            annotator_id=annotator_id,
            current_golden_rate=current_golden_rate,
            annotator_accuracy=annotator_accuracy,
            recommended_golden_rate=recommended_golden_rate,
            current_golden_set_cost=current_golden_cost,
            optimized_golden_set_cost=optimized_golden_cost,
            monthly_savings=monthly_savings,
            reasoning=reasoning,
        )

        return optimization

    def throughput_cost_frontier(
        self,
        project_id: str,
        base_cost_per_label: float,
    ) -> ThroughputCostFrontier:
        """
        Generate Pareto frontier of quality vs. cost configurations.

        Args:
            project_id: Project identifier
            base_cost_per_label: Baseline cost per label (single-pass)

        Returns:
            ThroughputCostFrontier with optimal configurations

        Logic:
        For a given project, we can trade off quality for cost:
        1. Single-pass (1 annotator): 0.85 quality, $0.10 cost
        2. 2-stage (1 annotator + 10% review): 0.92 quality, $0.12 cost
        3. 2-stage (1 annotator + 20% review): 0.94 quality, $0.14 cost
        4. 3-stage (full consensus): 0.97 quality, $0.25 cost

        Plot these and find Pareto frontier (no configuration dominates another).
        Examiner can then choose: optimize for cost, quality, or find sweet spot.

        Example frontier:
        - Budget-constrained (cost): 1-pass config, 0.85 quality, $0.10
        - Balanced: 2-stage 15% review, 0.91 quality, $0.12
        - Quality-focused: 3-stage, 0.97 quality, $0.25
        """
        configurations = [
            {
                "name": "Single-pass",
                "consensus_stages": 1,
                "review_percentage": 0.0,
                "quality_estimate": 0.85,
                "cost_per_label": base_cost_per_label,
            },
            {
                "name": "2-stage (10% review)",
                "consensus_stages": 2,
                "review_percentage": 0.10,
                "quality_estimate": 0.90,
                "cost_per_label": base_cost_per_label * 1.15,
            },
            {
                "name": "2-stage (20% review)",
                "consensus_stages": 2,
                "review_percentage": 0.20,
                "quality_estimate": 0.93,
                "cost_per_label": base_cost_per_label * 1.30,
            },
            {
                "name": "3-stage (50% review + expert)",
                "consensus_stages": 3,
                "review_percentage": 0.50,
                "quality_estimate": 0.96,
                "cost_per_label": base_cost_per_label * 2.50,
            },
            {
                "name": "3-stage (100% consensus + expert)",
                "consensus_stages": 3,
                "review_percentage": 1.0,
                "quality_estimate": 0.98,
                "cost_per_label": base_cost_per_label * 3.50,
            },
        ]

        # Recommend balanced config (0.93 quality, reasonable cost)
        optimal = configurations[2]  # 2-stage 20% review

        frontier = ThroughputCostFrontier(
            configurations=configurations,
            optimal_config=optimal,
            budget_constrained_config=configurations[0],
            quality_constrained_config=configurations[-1],
        )

        return frontier

    def drift_detection_frequency_optimizer(
        self,
        project_id: str,
        current_check_frequency: DriftDetectionFrequency,
        data_stability_score: float,  # 0-1, higher = more stable
        cost_per_check: float,  # Cost to run drift detection
    ) -> DriftDetectionOptimization:
        """
        Recommend drift check frequency based on data stability.

        Args:
            project_id: Project identifier
            current_check_frequency: How often drift is currently checked
            data_stability_score: Measure of data change (0=volatile, 1=stable)
            cost_per_check: Cost to run one drift detection check

        Returns:
            DriftDetectionOptimization with recommendation

        Logic:
        Drift detection (comparing new data to training set) costs money.
        Run it frequently on volatile data, rarely on stable data.

        Heuristic:
        - Stability 0.0-0.3 (high drift risk): weekly
        - Stability 0.3-0.6 (moderate drift): biweekly
        - Stability 0.6-0.85 (low drift): monthly
        - Stability 0.85-1.0 (very stable): quarterly
        """
        # Determine recommended frequency
        if data_stability_score < 0.3:
            recommended_freq = DriftDetectionFrequency.WEEKLY
            checks_per_month = 4.3
        elif data_stability_score < 0.6:
            recommended_freq = DriftDetectionFrequency.BIWEEKLY
            checks_per_month = 2.15
        elif data_stability_score < 0.85:
            recommended_freq = DriftDetectionFrequency.MONTHLY
            checks_per_month = 1.0
        else:
            recommended_freq = DriftDetectionFrequency.QUARTERLY
            checks_per_month = 0.25

        # Current cost
        current_freq_checks = {
            DriftDetectionFrequency.WEEKLY: 4.3,
            DriftDetectionFrequency.BIWEEKLY: 2.15,
            DriftDetectionFrequency.MONTHLY: 1.0,
            DriftDetectionFrequency.QUARTERLY: 0.25,
        }

        current_checks_per_month = current_freq_checks[current_check_frequency]
        current_cost = current_checks_per_month * cost_per_check
        recommended_cost = checks_per_month * cost_per_check
        monthly_savings = current_cost - recommended_cost

        # Determine stability description
        if data_stability_score < 0.3:
            stability_desc = 'volatile'
        elif data_stability_score < 0.6:
            stability_desc = 'moderately changing'
        elif data_stability_score < 0.85:
            stability_desc = 'stable'
        else:
            stability_desc = 'very stable'

        optimization = DriftDetectionOptimization(
            project_id=project_id,
            current_check_frequency=current_check_frequency,
            current_check_cost_monthly=current_cost,
            data_stability_score=data_stability_score,
            recommended_frequency=recommended_freq,
            recommended_check_cost_monthly=recommended_cost,
            monthly_savings=monthly_savings,
            reasoning=f"Data stability score {data_stability_score:.2f}. Data is {stability_desc}. Recommend {recommended_freq.value} checks.",
        )

        return optimization

    def get_efficiency_report(
        self,
        project_id: str,
        total_labels: int,
        total_cost: float,
        annotators: List[AnnotatorProfile],
        use_active_learning: bool = False,
        consensus_stage: int = 1,
        golden_set_percentage: float = 0.10,
    ) -> CostEfficiencyReport:
        """
        Generate comprehensive efficiency report with optimization recommendations.

        Args:
            project_id: Project identifier
            total_labels: Total labels produced
            total_cost: Total project cost
            annotators: Participating annotators
            use_active_learning: Whether AL is currently used
            consensus_stage: Current consensus workflow stage (1, 2, or 3)
            golden_set_percentage: Current golden set rate

        Returns:
            CostEfficiencyReport with detailed analysis and recommendations

        This is what project leads see: "Here's your cost breakdown, here's
        where you can optimize, here's the trade-off."
        """
        cost_per_label = self.cost_per_label(project_id, total_cost, total_labels)

        # Cost breakdown
        cost_breakdown = {
            "annotator_time": total_cost * 0.70,  # Typical: 70% goes to annotation
            "consensus_review": total_cost * 0.15,  # 15% to review
            "golden_set": total_cost * (golden_set_percentage * 0.5),  # Golden set portion
            "infrastructure": total_cost * 0.10,  # 10% to platform/tools
        }

        # Efficiency analysis
        efficiency_metrics = {
            "total_labels": total_labels,
            "cost_per_label": f"${cost_per_label:.3f}",
            "annotator_count": len(annotators),
            "avg_annotator_accuracy": sum(a.accuracy_rate for a in annotators) / len(annotators) if annotators else 0,
            "active_learning_used": use_active_learning,
            "consensus_stages": consensus_stage,
        }

        # Generate recommendations
        recommendations = []

        if not use_active_learning:
            recommendations.append(
                "MEDIUM-IMPACT: Enable active learning to reduce label volume by 40-60%. "
                "Example: If labeling 10K items, AL can reduce to 4-6K items at same quality."
            )

        if consensus_stage == 1:
            recommendations.append(
                "MEDIUM-IMPACT: Consider 2-stage consensus (10% review). "
                f"Cost increase ~15% but quality improvement 5-8 points. Current cost per label: ${cost_per_label:.3f} → ${cost_per_label * 1.15:.3f}."
            )

        if golden_set_percentage > 0.05:
            avg_annotator_accuracy = (
                sum(a.accuracy_rate for a in annotators) / len(annotators) if annotators else 0.90
            )
            if avg_annotator_accuracy > 0.95:
                recommendations.append(
                    f"LOW-IMPACT: Reduce golden set from {golden_set_percentage*100:.0f}% to 2% for senior annotators. "
                    f"Savings: ~${total_cost * (golden_set_percentage - 0.02) * 0.1 / 12:.2f}/month."
                )

        monthly_burn_rate = total_cost / 3 if total_cost else 0  # Assume project timeline

        report = CostEfficiencyReport(
            project_id=project_id,
            total_labels=total_labels,
            average_cost_per_label=cost_per_label,
            total_project_cost=total_cost,
            cost_breakdown=cost_breakdown,
            efficiency_metrics=efficiency_metrics,
            optimization_recommendations=recommendations,
            monthly_burn_rate=monthly_burn_rate,
        )

        return report
