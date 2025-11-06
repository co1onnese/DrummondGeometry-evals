# Phase 2 Notes ? Core Drummond Geometry Calculations

## Objectives

Deliver the computational foundation required to support Drummond Geometry analytics:

1. **PLdot Engine** ? Accurate rolling projection with validation against known formulas.
2. **Envelope Computation** ? ATR-based and percentage-based envelopes; extension to custom methods later.
3. **Drummond Lines** ? Two-bar trendline calculations, forward projection, and zone aggregation logic.
4. **Market State Classifier** ? Implement the five state machine (trend, congestion entrance/action/exit, reversal).
5. **Pattern Detection Primitives** ? PLdot push, exhaust, C-wave detection scaffolding.
6. **Service Layer** ? Internal API (Python service/CLI) for multi-symbol/multi-timeframe batch calculation.
7. **Multi-Timeframe Coordination** ? Framework to align higher/lower timeframe signals and derive confluence metrics.

## Dependencies & Inputs

- Phase 1 ingestion pipeline (market data stored in PostgreSQL).
- Design references: `prd/03_python_data_models.md`, `prd/05_backtesting_architecture.md`, `prd/06_prediction_system.md`.
- Calculations need to be reusable by later phases (backtesting, real-time prediction, CLI/dashboard).

## Proposed Package Structure

```
src/dgas/
  calculations/
    __init__.py
    pldot.py
    envelopes.py
    drummond_lines.py
    market_state.py
    patterns.py
    timeframe.py
  services/
    calculator.py
    coordination.py
```

Supporting modules:
- `dgas/calculations/utils.py` ? shared helpers (rolling windows, smoothing).
- `dgas/services/calculator.py` ? orchestrate indicator computation per symbol/timeframe.
- `dgas/services/coordination.py` ? evaluate multi-timeframe alignment and produce confidence scores.

## Implementation Notes

### PLdot
- Use rolling 3-bar window derived from historical data.
- Support forward projection: PLdot plotted at t+1 interval.
- Provide verifying tests using synthetic OHLCV sequences and reference outputs (from documentation or custom calculations).

### Envelopes
- ATR-based envelope: compute ATR (n-period, default 14) and multiply by configured factor.
- Percentage-based envelope: simple relative offset percent from PLdot value.
- Consider storing additional metadata (band squeeze, position) in future phases ? structure design to extend.

### Drummond Lines
- Compute two-bar trendlines for each classification (5-1, 5-2, etc.).
- Need to store start/end points, slope, strength metrics.
- For Phase 2, implement a subset (e.g., 5-1 and 5-2) with extension hooks.
- Provide zone aggregation (support/resistance grouping) as per PRD requirements.

### Market States
- Implement logic based on PLdot relationship and consecutive closes.
- Maintain state transitions and track duration (number of bars in current state).
- Output enumerated state plus confidence score (initially deterministic, later augment with probabilities).

### Patterns
- Provide detection scaffolding for PLdot push, exhaust, C-wave.
- For Phase 2, implement detection criteria referencing PRD definitions.
- Return metadata indicating confidence, duration, associated levels.

### Multi-Timeframe Coordination
- Accept precomputed indicator outputs per timeframe.
- Calculate confluence (e.g., overlapping support/resistance within tolerance).
- Produce scoring metrics consumed by Phase 4 signal engine.

## Testing Strategy

- Unit tests for each calculation module using synthetic OHLCV data.
- Snapshot tests for multi-timeframe coordination outputs.
- Integration tests verifying database read ? calculation ? storage (if results persisted).
- Validate handling of missing data and irregular intervals (gaps from Phase 1 quality checks).

## Work Breakdown (Aligned with TODOs)

1. **phase2-plan** ? Document scope (this file) and create backlog tasks.
2. **phase2-pldot** ? Implement PLdot module + tests; integrate with service layer prototype.
3. **phase2-envelopes** ? Add envelope calculations and tests; ensure compatibility with PLdot output.
4. **phase2-drummond-lines** ? Minimal viable Drummond lines + zone aggregator.
5. **phase2-states-patterns** ? Market state classifier and initial pattern modules.
6. **phase2-api** ? Service/CLI layer to run calculations for stored data, returning JSON/CSV/DB inserts.

## Considerations

- Performance: initial implementation can be pandas-based; plan optimization (NumPy, vectorization) later.
- Storage: decide whether to persist calculations in dedicated tables (likely yes, matching PRD schema).
- Incremental updates: design function signatures so Phase 1 incremental jobs can call into Phase 2 calculators.

