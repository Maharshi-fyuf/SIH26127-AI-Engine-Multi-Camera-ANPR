# Adaptive Traffic Signal Control — Future Scope / Prototype

YUVATECH now contains a deterministic **signal timing recommendation engine**.
It uses camera-derived traffic state (vehicle volume, queue length, speed and
saturation) and confidence-gated emergency-vehicle detection to calculate a
bounded green-time plan for an intersection.

## Flow

Camera network → detection/tracking → traffic state → signal optimizer → recommended phase plan → authorized traffic controller integration (future)

## Safety boundary

The prototype **does not directly actuate traffic signals**. The API returns a
recommendation only. Production actuation requires an approved traffic
controller interface, fail-safe interlocks, operator/authority authorization,
conflict checking, rollback behavior and field validation.

## Example API

`POST /api/signals/optimize`

The request accepts an intersection ID, cycle length and per-approach traffic
state. The response includes each approach's recommended green time, demand
score and whether it received emergency priority.

## Logic

1. Queue length contributes more weight than raw vehicle count.
2. Low observed speed increases demand weighting, while the effect is bounded.
3. Saturation adds a bounded demand multiplier.
4. Minimum and maximum green limits are always enforced.
5. The complete cycle is rebalanced to the requested cycle length.
6. Emergency priority is enabled only when the emergency classification is
   above the configured confidence threshold.
7. Every recommendation is audit logged.

## Future production stages

- Connect to an authorized traffic-controller/ITS interface.
- Add phase compatibility and conflict matrices.
- Add yellow/all-red clearance intervals.
- Add pedestrian phase constraints.
- Add short-horizon traffic prediction.
- Compare fixed-time vs adaptive timing in a simulator before field deployment.
- Add operator approval and automatic rollback/failsafe behavior.
