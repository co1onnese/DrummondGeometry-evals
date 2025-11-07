# Drummond Geometry Enhancement Plan

Prepared by: GPT-5 Codex  
Source feedback: `docs/Critical_Review_grok.md`

## Purpose & Context

- Preserve the existing high fidelity to Charles Drummond's methodology while layering in refinements highlighted by Grok's review.
- Sequence enhancements to minimize regression risk and keep prediction/backtesting capabilities aligned.
- Provide clear documentation, testing, and benchmarking pathways before any production rollout.

## Strategic Objectives

1. Clarify documentation to explain methodological choices (especially volatility-based envelopes and pattern logic).
2. Refine pattern detection algorithms for Exhaust, C-Wave, and PLdot Refresh with richer signal filters.
3. Strengthen multi-timeframe confluence, trading logic, and signal generation with zone weighting, risk-adjusted sizing, and trailing stops.
4. Establish objective benchmarking, monitoring, and calibration artifacts to quantify advantages over traditional indicators.

## Phase Breakdown

### Phase 1 – Documentation Refresh (Low Effort, High Clarity)

- Expand inline docstrings and comments in calculation modules to reference Drummond principles.
- Add analyst-facing documentation in `docs/` covering envelope rationale, pattern detection narratives, and a change log entry describing upcoming functional refinements.

### Phase 2 – Pattern Detection Refinements (Medium Effort)

- Enhance Exhaust detection with minimum envelope extension, momentum divergence checks, and temporal filters.
- Incorporate PLdot slope acceleration, optional volume confirmation, and envelope expansion tracking for C-Wave detection.
- Introduce adaptive tolerance logic for PLdot Refresh based on volatility regimes and return velocity.
- Surface new thresholds via configuration hooks with backward-compatible defaults; update unit tests with synthetic datasets covering new edge cases.

### Phase 3 – Trading & Signal Logic Upgrades (High Effort)

- Integrate Drummond line projections into confluence zone scoring with timeframe-aware weighting and volatility-tuned tolerances.
- Replace placeholder multi-timeframe trading strategy with pattern-gated entries, trailing stops anchored to PLdot/envelopes, and envelope-width-based position sizing.
- Align prediction engine signal generation with the enhanced strategy, ensuring the aggregator respects new confidence and sizing metrics.
- Extend persistence models only if additional metadata is required, coordinating migrations as needed.

### Phase 4 – Validation & Benchmarking (Ongoing)

- Build benchmarking harnesses contrasting DG signals with RSI, MACD, and Bollinger Bands across varied market regimes.
- Segment performance analyses by trend vs. congestion states and across asset classes; include volatility-adjusted metrics.
- Implement monitoring dashboards and calibration routines to track latency, throughput, signal accuracy, and forward-edge metrics.

## Risks & Mitigations

- **Overfitting Enhancements**: Mitigate via cross-validation, benchmark comparisons, and preserving feature toggles for new heuristics.
- **Schema Drift**: Coordinate migrations carefully; maintain compatibility for existing data consumers.
- **Testing Debt**: Expand unit/integration coverage in lockstep with code changes; enforce regression suites before rollout.

## Detailed TODO List

| ID | Status | Area | Task Description | Notes |
|----|--------|------|------------------|-------|
| T1 | Pending | Documentation | Update `calculations/envelopes.py` docstrings and `docs/` references to explain volatility-based envelope rationale. | Include citation from Grok review. |
| T2 | Pending | Documentation | Author pattern detection explainer (with diagrams callouts) covering PLdot Push, Refresh, Exhaust, C-Wave, Congestion Oscillation. | Place in `docs/` and cross-link from README change log. |
| T3 | Pending | Tests Inventory | Audit existing tests in `tests/calculations/` and `tests/backtesting/` to map current coverage for pattern and strategy behaviors. | Document findings in project wiki or README section. |
| T4 | Pending | Patterns | Implement Exhaust pattern enhancements (extension threshold, momentum divergence, temporal filter) with configurable parameters. | Ensure defaults replicate current behavior when disabled. |
| T5 | Pending | Patterns | Extend C-Wave detection for slope acceleration and optional volume confirmation; add envelope expansion checks. | Introduce feature flags/config options. |
| T6 | Pending | Patterns | Refine PLdot Refresh detection with adaptive tolerances and return-speed metrics; add multi-timeframe confirmation hooks. | Update related data structures if necessary. |
| T7 | Pending | Patterns Tests | Create comprehensive synthetic datasets and regression tests validating new pattern logic. | Expand `tests/calculations/test_patterns.py`. |
| T8 | Pending | Confluence | Integrate Drummond line projections into zone aggregation with timeframe-weighted strengths and volatility-adjusted tolerances. | Update `MultiTimeframeAnalysis` structures as required. |
| T9 | Pending | Trading Strategy | Replace placeholder rules in `backtesting/strategies/multi_timeframe.py` with pattern-gated entries, trailing stops, and envelope-based position sizing. | Maintain configuration parity with CLI. |
| T10 | Pending | Strategy Tests | Expand strategy tests to cover new entry/exit logic, trailing stops, and sizing outcomes. | Use backtest fixtures for deterministic assertions. |
| T11 | Pending | Prediction Engine | Align `prediction/engine.py` signal generation with upgraded strategy, including sizing, trailing stops, and pattern filters. | Ensure aggregator thresholds stay consistent. |
| T12 | Pending | Monitoring | Complete `prediction/monitoring/performance.py` to capture latency/accuracy metrics reflecting enhanced logic. | Add tests under `tests/prediction/monitoring/`. |
| T13 | Pending | Benchmarking | Build benchmarking harness comparing DG outputs to RSI/MACD/Bollinger Bands across regimes; store reports in `docs/`. | Consider pytest marker or CLI command for repeatability. |
| T14 | Pending | Regime Analysis | Implement regime segmentation (trend vs congestion) in validation pipeline and summarize results. | Feed insights into documentation dashboards. |
| T15 | Pending | Reporting | Update README roadmap and docs change log to reflect enhancement plan and testing requirements. | Communicate rollout checklist. |

*No implementation work has begun. This document captures the agreed strategic plan and actionable TODOs prior to any code changes.*

