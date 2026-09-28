from dataclasses import dataclass
from typing import Iterable


@dataclass
class RuleMetrics:
    violation_type: str
    true_positive: int
    false_positive: int
    false_negative: int
    human_overrides: int
    true_negative: int | None = None

    @property
    def precision(self) -> float:
        total = self.true_positive + self.false_positive
        return self.true_positive / total if total else 0.0

    @property
    def recall(self) -> float:
        total = self.true_positive + self.false_negative
        return self.true_positive / total if total else 0.0

    @property
    def false_discovery_rate(self) -> float:
        total = self.true_positive + self.false_positive
        return self.false_positive / total if total else 0.0

    @property
    def false_positive_rate(self) -> float | None:
        """True FPR when TN is available; otherwise None because FPR is not identifiable."""
        if self.true_negative is None:
            return None
        total = self.false_positive + self.true_negative
        return self.false_positive / total if total else 0.0


def render_accuracy_audit_report(metrics: Iterable[RuleMetrics]) -> str:
    lines = [
        "# Accuracy and Audit Report",
        "",
        "Privacy basis: retention and redaction controls are designed around India's Digital Personal Data Protection Act, 2023.",
        "",
        "| Rule | Precision | Recall | False Positive Rate | False Discovery Rate | Human Overrides |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in metrics:
        fpr = "N/A" if item.false_positive_rate is None else f"{item.false_positive_rate:.2f}"
        lines.append(
            f"| {item.violation_type} | {item.precision:.2f} | {item.recall:.2f} | "
            f"{fpr} | {item.false_discovery_rate:.2f} | {item.human_overrides} |"
        )
    return "\n".join(lines) + "\n"
