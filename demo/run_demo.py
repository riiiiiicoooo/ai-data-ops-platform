#!/usr/bin/env python3
"""
AI Data Operations Platform - Complete Demo Pipeline

This script demonstrates the full annotation workflow:
1. Schema definition (fraud classification)
2. Task creation
3. Annotation submission from multiple annotators
4. Inter-annotator agreement scoring
5. Consensus resolution (weighted vote)
6. Per-annotator accuracy tracking

Expected runtime: < 5 seconds
"""

import sys
import os
from uuid import uuid4
import random

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.task_engine.schema_registry import SchemaRegistry
from src.quality.agreement_calculator import AgreementCalculator
from src.annotation.consensus_resolver import (
    ConsensusResolver,
    AnnotatorVote,
    ConsensusMethod,
)


def print_header(title):
    """Print formatted section header."""
    print(f"\n{'='*60}")
    print(f"{title:^60}")
    print(f"{'='*60}\n")


def print_step(num, description):
    """Print step header."""
    print(f"\n[Step {num}] {description}")
    print("-" * 60)


def run_demo():
    """Execute the complete demo pipeline."""

    print_header("AI Data Operations Platform - Demo")

    # ====================================================================
    # Step 1: Schema Registry - Define annotation schema
    # ====================================================================
    print_step(1, "Schema Definition")

    registry = SchemaRegistry()
    org_id = uuid4()
    user_id = uuid4()

    schema = registry.create_from_preset(
        org_id=org_id,
        preset_name="fraud_classification",
        created_by=user_id
    )

    print(f"✓ Created schema: {schema.name} v{schema.version}")
    print(f"  Input type: {schema.input_type.value}")
    print(f"  Output fields: {[f.name for f in schema.output_fields]}")
    print(f"  Primary metric: {schema.primary_metric.value}")
    print(f"  Validation rules: {len(schema.validation_rules)}")

    # ====================================================================
    # Step 2: Task Definition
    # ====================================================================
    print_step(2, "Task Creation")

    # Create synthetic transactions for annotation
    transactions = [
        {"id": f"TXN_{i:04d}", "amount": 50 + random.randint(0, 1000), "merchant": f"merchant_{i % 5}"}
        for i in range(10)
    ]

    print(f"✓ Created {len(transactions)} annotation tasks")
    print(f"  Amount range: ${transactions[0]['amount']} - ${max(t['amount'] for t in transactions)}")

    # ====================================================================
    # Step 3: Annotation Submission
    # ====================================================================
    print_step(3, "Annotation Submission")

    # Three annotators with different accuracy profiles
    annotators = {
        "expert": {"accuracy": 0.95, "description": "95% accurate, slow"},
        "senior": {"accuracy": 0.88, "description": "88% accurate, moderate speed"},
        "junior": {"accuracy": 0.78, "description": "78% accurate, fast"},
    }

    # Simulate annotations
    all_annotations = {}

    for idx, txn in enumerate(transactions):
        task_id = f"task_{idx:02d}"
        task_annotations = {}

        # Simple heuristic: high amounts (>300) are more likely fraud
        true_fraud = txn["amount"] > 300

        for ann_name, ann_profile in annotators.items():
            # Annotator makes mistakes according to accuracy
            is_fraud = true_fraud

            # Simulate annotator error
            error_rate = 1 - ann_profile["accuracy"]
            if random.random() < error_rate:
                is_fraud = not is_fraud  # Mistake

            annotation = {
                "label": "fraud" if is_fraud else "legitimate",
                "confidence": "high" if txn["amount"] > 500 else "medium" if txn["amount"] > 300 else "low",
                "reasoning": f"Amount ${txn['amount']} from {txn['merchant']}"
            }

            # Validate annotation against schema
            errors = registry.validate_annotation(schema.schema_id, annotation)
            if not errors:
                task_annotations[ann_name] = annotation

        all_annotations[task_id] = task_annotations

    print(f"✓ Received annotations from {len(annotators)} annotators")
    print(f"  Total annotations: {sum(len(a) for a in all_annotations.values())}")

    for ann_name, profile in annotators.items():
        count = sum(1 for a in all_annotations.values() if ann_name in a)
        print(f"    {ann_name}: {count} annotations ({profile['description']})")

    # ====================================================================
    # Step 4: Agreement Scoring
    # ====================================================================
    print_step(4, "Inter-Annotator Agreement Scoring")

    calc = AgreementCalculator()

    # Compute agreement for each task
    all_agreement_scores = []
    agreement_by_amount = {"low": [], "medium": [], "high": []}

    for task_id, annotations in all_annotations.items():
        if len(annotations) < 2:
            continue

        # Extract labels for agreement calculation
        labels = [annotations[ann]["label"] for ann in sorted(annotations.keys())]

        # Compute Fleiss' kappa (3 annotators)
        result = calc.fleiss_kappa([labels])
        all_agreement_scores.append(result.score)

        # Categorize by transaction amount
        task_idx = int(task_id.split("_")[1])
        amount = transactions[task_idx]["amount"]
        if amount > 500:
            agreement_by_amount["high"].append(result.score)
        elif amount > 300:
            agreement_by_amount["medium"].append(result.score)
        else:
            agreement_by_amount["low"].append(result.score)

    if all_agreement_scores:
        mean_agreement = sum(all_agreement_scores) / len(all_agreement_scores)
        print(f"✓ Batch Agreement Analysis")
        print(f"  Tasks analyzed: {len(all_agreement_scores)}")
        print(f"  Mean Fleiss' kappa: {mean_agreement:.3f}")
        print(f"  Interpretation: {'STRONG' if mean_agreement > 0.80 else 'MODERATE' if mean_agreement > 0.60 else 'FAIR'}")
        print(f"  Min: {min(all_agreement_scores):.3f}, Max: {max(all_agreement_scores):.3f}")

        # Show first task details
        first_task_id = f"task_00"
        first_annotations = all_annotations[first_task_id]
        first_labels = [first_annotations[ann]["label"] for ann in sorted(first_annotations.keys())]
        first_result = calc.fleiss_kappa([first_labels])
        print(f"\n  Task 0 example:")
        print(f"    Labels: {first_labels}")
        print(f"    Kappa: {first_result.score:.3f}")
        if 'observed_agreement' in first_result.details:
            print(f"    Raw agreement: {first_result.details['observed_agreement']:.0%}")

    # ====================================================================
    # Step 5: Consensus Resolution
    # ====================================================================
    print_step(5, "Consensus Resolution (Weighted Vote)")

    resolver = ConsensusResolver()
    consensus_results = {}

    for task_id, annotations in all_annotations.items():
        # Create votes with accuracy metadata
        votes = [
            AnnotatorVote(
                annotator_id=uuid4(),
                annotation_data=annotations[ann_name],
                accuracy_score=annotators[ann_name]["accuracy"],
                skill_level="expert" if annotators[ann_name]["accuracy"] > 0.90 else "senior"
            )
            for ann_name in sorted(annotations.keys())
        ]

        # Resolve with weighted vote (DEC-004)
        result = resolver.resolve(
            votes,
            method=ConsensusMethod.WEIGHTED_VOTE,
            label_field="label",
            min_agreement=0.0
        )

        consensus_results[task_id] = result

    # Analyze results
    resolved = sum(1 for r in consensus_results.values() if r.passed_quality)
    needs_expert = sum(1 for r in consensus_results.values() if not r.passed_quality)

    print(f"✓ Consensus Resolution Complete")
    print(f"  Resolved automatically: {resolved}/{len(consensus_results)} ({resolved/len(consensus_results):.0%})")
    print(f"  Need expert review: {needs_expert}")
    print(f"  Method: {ConsensusMethod.WEIGHTED_VOTE.value}")

    # Show example
    first_result = consensus_results[f"task_00"]
    print(f"\n  Task 0 consensus:")
    print(f"    Label: {first_result.resolved_annotation.get('label')}")
    print(f"    Agreement: {first_result.agreement_score:.3f}")
    print(f"    Confidence: {first_result.confidence:.3f}")
    if "margin" in first_result.details:
        print(f"    Margin: {first_result.details['margin']:.3f}")

    # ====================================================================
    # Step 6: Consensus Distribution
    # ====================================================================
    print_step(6, "Consensus Distribution Analysis")

    distribution = resolver.get_resolution_distribution(consensus_results)

    print(f"✓ Distribution Summary")
    print(f"  Total tasks: {distribution['total_tasks']}")
    print(f"  Resolved: {distribution['resolved']}")
    print(f"  Unresolved: {distribution['unresolved']}")
    print(f"  Resolution rate: {distribution['resolution_rate']:.0%}")
    print(f"  Avg agreement: {distribution['avg_agreement']:.3f}")
    print(f"  Needs expert: {distribution['needs_expert']}")

    # ====================================================================
    # Step 7: Annotator Accuracy Tracking
    # ====================================================================
    print_step(7, "Per-Annotator Accuracy Tracking")

    annotator_scores = {}

    for task_id, annotations in all_annotations.items():
        consensus = consensus_results[task_id]

        if not consensus.passed_quality:
            continue

        consensus_label = consensus.resolved_annotation.get("label")

        for ann_name, annotation in annotations.items():
            if ann_name not in annotator_scores:
                annotator_scores[ann_name] = {"correct": 0, "total": 0}

            annotator_scores[ann_name]["total"] += 1
            if annotation["label"] == consensus_label:
                annotator_scores[ann_name]["correct"] += 1

    print(f"✓ Accuracy Report")
    total_correct = 0
    total_items = 0

    for ann_name in sorted(annotators.keys()):
        scores = annotator_scores.get(ann_name, {"correct": 0, "total": 0})
        if scores["total"] > 0:
            accuracy = scores["correct"] / scores["total"]
            expected = annotators[ann_name]["accuracy"]
            status = "✓" if abs(accuracy - expected) < 0.15 else "⚠"
            print(f"  {ann_name:10s}: {accuracy:5.1%} ({scores['correct']:2d}/{scores['total']:2d} correct) {status}")
            total_correct += scores["correct"]
            total_items += scores["total"]

    if total_items > 0:
        overall_accuracy = total_correct / total_items
        print(f"  {'OVERALL':10s}: {overall_accuracy:5.1%} ({total_correct:2d}/{total_items:2d} correct)")

    # ====================================================================
    # Final Summary Report
    # ====================================================================
    print_header("Quality Report Summary")

    print("Inter-Annotator Agreement:")
    if all_agreement_scores:
        mean_kappa = sum(all_agreement_scores) / len(all_agreement_scores)
        print(f"  Mean Fleiss' Kappa: {mean_kappa:.3f}")
        interpretation = "STRONG (>0.80)" if mean_kappa > 0.80 else "MODERATE (0.60-0.80)" if mean_kappa > 0.60 else "FAIR (0.40-0.60)"
        print(f"  Interpretation: {interpretation}")

    print(f"\nConsensus Resolution:")
    print(f"  Auto-resolution rate: {distribution['resolution_rate']:.0%}")
    print(f"  Target: 85%+ (DEC-004)")
    print(f"  Status: {'✓ PASS' if distribution['resolution_rate'] >= 0.85 else '⚠ NEEDS REVIEW'}")

    print(f"\nAnnotator Performance:")
    for ann_name in sorted(annotators.keys()):
        scores = annotator_scores.get(ann_name, {"correct": 0, "total": 0})
        if scores["total"] > 0:
            measured = scores["correct"] / scores["total"]
            expected = annotators[ann_name]["accuracy"]
            print(f"  {ann_name:10s}: {measured:.1%} (expected {expected:.0%})")

    print(f"\nBatch Quality Metrics:")
    usable_items = distribution['resolved']
    total_items = distribution['total_tasks']
    usable_rate = usable_items / total_items if total_items > 0 else 0
    print(f"  Total items: {total_items}")
    print(f"  Usable items: {usable_items}")
    print(f"  Usable rate: {usable_rate:.0%}")
    print(f"  Target: > 95%")
    print(f"  Status: {'✓ PASS' if usable_rate >= 0.95 else '⚠ NEEDS REVIEW'}")

    print_header("Demo Complete")
    print("Next steps:")
    print("  - See DEMO.md for detailed walkthrough")
    print("  - See CONTRIBUTING.md for extending these components")
    print("  - Run: docker-compose up -d  (to start infrastructure)")
    print("  - Run: python -m pytest tests/  (to run test suite)")


if __name__ == "__main__":
    run_demo()
