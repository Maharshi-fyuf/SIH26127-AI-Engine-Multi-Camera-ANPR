from dataclasses import dataclass
from typing import Iterable


@dataclass
class RuleMetrics:
    violation_type: str
    true_positive: int
    false_positive: int
    false_negative: int
    human_overrides: int

    @property
    def precision(self) -> float:
        total = self.true_positive + self.false_positive
        return self.true_positive / total if total else 0.0

    @property
    def recall(self) -> float:
        total = self.true_positive + self.false_negative
        return self.true_positive / total if total else 0.0

    @property
    def false_positive_rate(self) -> float:
        total = self.true_positive + self.false_positive
        return self.false_positive / total if total else 0.0


def render_accuracy_audit_report(metrics: Iterable[RuleMetrics]) -> str:
    lines = [
        "# Accuracy and Audit Report",
        "",
        "Privacy basis: retention and redaction controls are designed around India's Digital Personal Data Protection Act, 2023.",
        "",
        "| Rule | Precision | Recall | False Positive Rate | Human Overrides |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for item in metrics:
        lines.append(
            f"| {item.violation_type} | {item.precision:.2f} | {item.recall:.2f} | "
            f"{item.false_positive_rate:.2f} | {item.human_overrides} |"
        )
    return "\n".join(lines) + "\n"
