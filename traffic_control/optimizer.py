"""Explainable adaptive signal timing optimizer.

This module produces a *recommended* signal plan from observed traffic state.
It does not directly control traffic controllers. Real actuation requires an
approved traffic-controller integration and operational authorization.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass(frozen=True)
class ApproachState:
    approach_id: str
    vehicle_count: int
    queue_length: int
    avg_speed_kph: float = 0.0
    emergency_vehicle: bool = False
    emergency_confidence: float = 0.0
    saturated: bool = False

    def normalized_demand(self) -> float:
        queue = max(0, self.queue_length)
        vehicles = max(0, self.vehicle_count)
        speed_factor = 1.0 if self.avg_speed_kph <= 5 else max(0.25, min(1.0, 30.0 / self.avg_speed_kph))
        saturation = 1.15 if self.saturated else 1.0
        return (queue * 1.5 + vehicles) * speed_factor * saturation


@dataclass(frozen=True)
class PhaseRecommendation:
    approach_id: str
    green_seconds: int
    demand_score: float
    emergency_priority: bool


@dataclass(frozen=True)
class SignalPlan:
    intersection_id: str
    cycle_seconds: int
    phases: tuple[PhaseRecommendation, ...]
    reason: str
    emergency_priority_approach: str | None = None

    def to_dict(self) -> dict:
        result = asdict(self)
        result["phases"] = [asdict(phase) for phase in self.phases]
        return result


class SignalOptimizer:
    """Deterministic, bounded optimizer suitable for simulation/prototyping.

    The optimizer intentionally avoids unsafe abrupt changes. It preserves a
    minimum green, caps each phase, and normalizes total green time to the
    configured cycle. Emergency priority is only considered above the supplied
    confidence threshold.
    """

    def __init__(self, min_green: int = 10, max_green: int = 90, cycle_seconds: int = 120,
                 emergency_confidence_threshold: float = 0.90):
        if min_green <= 0 or max_green < min_green or cycle_seconds <= 0:
            raise ValueError("Invalid signal timing bounds")
        self.min_green = min_green
        self.max_green = max_green
        self.cycle_seconds = cycle_seconds
        self.emergency_confidence_threshold = emergency_confidence_threshold

    def optimize(self, intersection_id: str, approaches: Iterable[ApproachState]) -> SignalPlan:
        states = tuple(approaches)
        if not states:
            raise ValueError("At least one approach is required")
        if len(states) * self.min_green > self.cycle_seconds:
            raise ValueError("Cycle is too short for the configured minimum green")

        emergency = next((s for s in states if s.emergency_vehicle and s.emergency_confidence >= self.emergency_confidence_threshold), None)
        if emergency:
            # Give the emergency approach the largest safe phase while keeping
            # a minimum service window for every other approach.
            remaining = self.cycle_seconds - self.min_green * (len(states) - 1)
            priority_green = min(self.max_green, max(self.min_green, remaining))
            other = self.cycle_seconds - priority_green
            non_emergency = [s for s in states if s.approach_id != emergency.approach_id]
            phases = [PhaseRecommendation(emergency.approach_id, priority_green,
                                          emergency.normalized_demand(), True)]
            self._append_proportional(phases, non_emergency, other)
            reason = "Emergency vehicle priority recommendation based on confidence-gated detection."
            return SignalPlan(intersection_id, self.cycle_seconds, tuple(phases), reason, emergency.approach_id)

        scores = {s.approach_id: max(1.0, s.normalized_demand()) for s in states}
        total = sum(scores.values())
        raw = {s.approach_id: self.min_green + (self.cycle_seconds - self.min_green * len(states)) * scores[s.approach_id] / total for s in states}
        greens = {k: max(self.min_green, min(self.max_green, int(round(v)))) for k, v in raw.items()}
        self._rebalance(greens, scores, states)
        phases = tuple(PhaseRecommendation(s.approach_id, greens[s.approach_id], scores[s.approach_id], False) for s in states)
        return SignalPlan(
            intersection_id,
            self.cycle_seconds,
            phases,
            "Demand-weighted recommendation using queue length, volume, speed and saturation.",
            None,
        )

    def _append_proportional(self, phases: list[PhaseRecommendation], states: list[ApproachState], seconds: int) -> None:
        if not states:
            return
        scores = {s.approach_id: max(1.0, s.normalized_demand()) for s in states}
        total = sum(scores.values())
        allocations = {s.approach_id: self.min_green + max(0, seconds - self.min_green * len(states)) * scores[s.approach_id] / total for s in states}
        greens = {k: max(self.min_green, min(self.max_green, int(round(v)))) for k, v in allocations.items()}
        self._rebalance(greens, scores, states, target=seconds)
        for s in states:
            phases.append(PhaseRecommendation(s.approach_id, greens[s.approach_id], scores[s.approach_id], False))

    def _rebalance(self, greens: dict[str, int], scores: dict[str, float], states: tuple[ApproachState, ...] | list[ApproachState], target: int | None = None) -> None:
        target = self.cycle_seconds if target is None else target
        while sum(greens.values()) < target:
            candidates = [s for s in states if greens[s.approach_id] < self.max_green]
            if not candidates:
                break
            candidate = max(candidates, key=lambda s: (scores[s.approach_id] / greens[s.approach_id], scores[s.approach_id]))
            greens[candidate.approach_id] += 1
        while sum(greens.values()) > target:
            candidates = [s for s in states if greens[s.approach_id] > self.min_green]
            if not candidates:
                break
            candidate = min(candidates, key=lambda s: (scores[s.approach_id], -greens[s.approach_id]))
            greens[candidate.approach_id] -= 1
        if sum(greens.values()) != target:
            raise RuntimeError("Unable to produce a bounded signal plan")
