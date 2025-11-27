#!/usr/bin/env python3
"""
Envelope Method Validation Script

This script compares different envelope calculation methods (pldot_range vs hlc_range)
and provides validation metrics to assess their effectiveness for Drummond Geometry analysis.

Metrics calculated:
- Containment Rate: How often price stays within the envelope
- Touch Rate: How often price touches envelope boundaries (upper/lower)
- Reversal Accuracy: How often touches lead to price reversals
- Average Width: Mean envelope width as percentage of price

Usage:
    python scripts/validate_envelope_methods.py --symbol AAPL --days 30
    python scripts/validate_envelope_methods.py --symbol MSFT --days 60 --interval 1h
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import psycopg
import structlog

from dgas.calculations.envelopes import EnvelopeCalculator, EnvelopeSeries
from dgas.calculations.pldot import PLDotCalculator
from dgas.data.models import IntervalData
from dgas.data.repository import fetch_market_data
from dgas.settings import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class EnvelopeMetrics:
    """Validation metrics for an envelope calculation method."""
    method: str
    total_bars: int
    
    # Containment metrics
    containment_rate: float  # % of bars where close is within envelope
    upper_breach_rate: float  # % of bars where close > upper
    lower_breach_rate: float  # % of bars where close < lower
    
    # Touch metrics
    upper_touch_rate: float  # % of bars touching upper envelope
    lower_touch_rate: float  # % of bars touching lower envelope
    total_touch_rate: float  # % of bars touching either envelope
    
    # Reversal metrics (bars after touch)
    upper_touch_reversal_rate: float  # % of upper touches followed by down move
    lower_touch_reversal_rate: float  # % of lower touches followed by up move
    overall_reversal_accuracy: float  # Overall reversal accuracy
    
    # Width metrics
    avg_width_pct: float  # Average width as % of price
    min_width_pct: float
    max_width_pct: float
    
    # Position distribution
    avg_position: float  # Average position within envelope (0-1)
    position_std: float  # Standard deviation of position


@dataclass
class ValidationResult:
    """Complete validation result comparing methods."""
    symbol: str
    interval: str
    start_date: datetime
    end_date: datetime
    pldot_range_metrics: EnvelopeMetrics
    hlc_range_metrics: EnvelopeMetrics


def load_data(
    conn: psycopg.Connection,
    symbol: str, 
    interval: str, 
    days: int,
) -> Tuple[List[IntervalData], Optional[str]]:
    """Load historical data for a symbol."""
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    intervals = fetch_market_data(
        conn=conn,
        symbol=symbol,
        interval=interval,
        start=start_date,
        end=end_date
    )
    
    if not intervals:
        return [], f"No data found for {symbol} ({interval}) in the last {days} days"
    
    return intervals, None


def calculate_envelope_metrics(
    intervals: List[IntervalData],
    envelopes: List[EnvelopeSeries],
    method: str,
    touch_threshold: float = 0.05,  # Within 5% of boundary = touch
    reversal_bars: int = 3,  # Look ahead N bars for reversal
) -> EnvelopeMetrics:
    """Calculate validation metrics for envelope series."""
    
    if not envelopes:
        return EnvelopeMetrics(
            method=method,
            total_bars=0,
            containment_rate=0.0,
            upper_breach_rate=0.0,
            lower_breach_rate=0.0,
            upper_touch_rate=0.0,
            lower_touch_rate=0.0,
            total_touch_rate=0.0,
            upper_touch_reversal_rate=0.0,
            lower_touch_reversal_rate=0.0,
            overall_reversal_accuracy=0.0,
            avg_width_pct=0.0,
            min_width_pct=0.0,
            max_width_pct=0.0,
            avg_position=0.0,
            position_std=0.0,
        )
    
    # Create aligned dataframe
    interval_df = pd.DataFrame([
        {
            "timestamp": i.timestamp,
            "high": float(i.high),
            "low": float(i.low),
            "close": float(i.close),
        }
        for i in intervals
    ]).set_index("timestamp")
    
    envelope_df = pd.DataFrame([
        {
            "timestamp": e.timestamp,
            "center": float(e.center),
            "upper": float(e.upper),
            "lower": float(e.lower),
            "width": float(e.width),
            "position": float(e.position),
        }
        for e in envelopes
    ]).set_index("timestamp")
    
    # Join on timestamp
    df = interval_df.join(envelope_df, how="inner")
    
    if df.empty:
        logger.warning(f"No aligned data for {method} envelope validation")
        return EnvelopeMetrics(
            method=method, total_bars=0,
            containment_rate=0.0, upper_breach_rate=0.0, lower_breach_rate=0.0,
            upper_touch_rate=0.0, lower_touch_rate=0.0, total_touch_rate=0.0,
            upper_touch_reversal_rate=0.0, lower_touch_reversal_rate=0.0,
            overall_reversal_accuracy=0.0,
            avg_width_pct=0.0, min_width_pct=0.0, max_width_pct=0.0,
            avg_position=0.0, position_std=0.0,
        )
    
    total_bars = len(df)
    
    # Containment metrics
    within_envelope = (df["close"] >= df["lower"]) & (df["close"] <= df["upper"])
    above_upper = df["close"] > df["upper"]
    below_lower = df["close"] < df["lower"]
    
    containment_rate = within_envelope.sum() / total_bars
    upper_breach_rate = above_upper.sum() / total_bars
    lower_breach_rate = below_lower.sum() / total_bars
    
    # Touch metrics (price within threshold of boundary)
    upper_distance = (df["upper"] - df["high"]).abs() / df["width"]
    lower_distance = (df["low"] - df["lower"]).abs() / df["width"]
    
    upper_touch = (upper_distance <= touch_threshold) | (df["high"] >= df["upper"])
    lower_touch = (lower_distance <= touch_threshold) | (df["low"] <= df["lower"])
    
    upper_touch_rate = upper_touch.sum() / total_bars
    lower_touch_rate = lower_touch.sum() / total_bars
    total_touch_rate = (upper_touch | lower_touch).sum() / total_bars
    
    # Reversal metrics
    df["future_close"] = df["close"].shift(-reversal_bars)
    
    upper_touch_indices = df[upper_touch].index
    lower_touch_indices = df[lower_touch].index
    
    upper_reversals = 0
    upper_touch_count = 0
    for idx in upper_touch_indices:
        if idx in df.index:
            current_close = df.loc[idx, "close"]
            future_close = df.loc[idx, "future_close"]
            if pd.notna(future_close):
                upper_touch_count += 1
                if future_close < current_close:  # Price went down after upper touch
                    upper_reversals += 1
    
    lower_reversals = 0
    lower_touch_count = 0
    for idx in lower_touch_indices:
        if idx in df.index:
            current_close = df.loc[idx, "close"]
            future_close = df.loc[idx, "future_close"]
            if pd.notna(future_close):
                lower_touch_count += 1
                if future_close > current_close:  # Price went up after lower touch
                    lower_reversals += 1
    
    upper_touch_reversal_rate = upper_reversals / upper_touch_count if upper_touch_count > 0 else 0.0
    lower_touch_reversal_rate = lower_reversals / lower_touch_count if lower_touch_count > 0 else 0.0
    
    total_reversals = upper_reversals + lower_reversals
    total_touches = upper_touch_count + lower_touch_count
    overall_reversal_accuracy = total_reversals / total_touches if total_touches > 0 else 0.0
    
    # Width metrics
    width_pct = (df["width"] / df["center"]) * 100
    avg_width_pct = width_pct.mean()
    min_width_pct = width_pct.min()
    max_width_pct = width_pct.max()
    
    # Position metrics
    avg_position = df["position"].mean()
    position_std = df["position"].std()
    
    return EnvelopeMetrics(
        method=method,
        total_bars=total_bars,
        containment_rate=containment_rate,
        upper_breach_rate=upper_breach_rate,
        lower_breach_rate=lower_breach_rate,
        upper_touch_rate=upper_touch_rate,
        lower_touch_rate=lower_touch_rate,
        total_touch_rate=total_touch_rate,
        upper_touch_reversal_rate=upper_touch_reversal_rate,
        lower_touch_reversal_rate=lower_touch_reversal_rate,
        overall_reversal_accuracy=overall_reversal_accuracy,
        avg_width_pct=avg_width_pct,
        min_width_pct=min_width_pct,
        max_width_pct=max_width_pct,
        avg_position=avg_position,
        position_std=position_std,
    )


def validate_envelope_methods(
    conn: psycopg.Connection,
    symbol: str,
    interval: str,
    days: int,
    period: int = 3,
    multiplier: float = 1.5,
) -> Optional[ValidationResult]:
    """Run validation comparing pldot_range and hlc_range envelope methods."""
    
    # Load data
    intervals, error = load_data(conn, symbol, interval, days)
    if error:
        logger.error(error)
        return None
    
    logger.info(f"Loaded {len(intervals)} bars for {symbol} ({interval})")
    
    # Calculate PLdot
    pldot_calc = PLDotCalculator(period=period, displacement=1)
    pldot_series = pldot_calc.from_intervals(intervals)
    
    if not pldot_series:
        logger.error("Failed to calculate PLdot series")
        return None
    
    logger.info(f"Calculated {len(pldot_series)} PLdot values")
    
    # Calculate envelopes with both methods
    pldot_range_calc = EnvelopeCalculator(
        method="pldot_range", 
        period=period, 
        multiplier=multiplier
    )
    hlc_range_calc = EnvelopeCalculator(
        method="hlc_range", 
        period=period, 
        multiplier=multiplier
    )
    
    pldot_range_envelopes = pldot_range_calc.from_intervals(intervals, pldot_series)
    hlc_range_envelopes = hlc_range_calc.from_intervals(intervals, pldot_series)
    
    logger.info(f"Calculated {len(pldot_range_envelopes)} pldot_range envelopes")
    logger.info(f"Calculated {len(hlc_range_envelopes)} hlc_range envelopes")
    
    # Calculate metrics for each method
    pldot_range_metrics = calculate_envelope_metrics(
        intervals, pldot_range_envelopes, "pldot_range"
    )
    hlc_range_metrics = calculate_envelope_metrics(
        intervals, hlc_range_envelopes, "hlc_range"
    )
    
    # Determine date range
    start_date = intervals[0].timestamp if intervals else datetime.now(timezone.utc)
    end_date = intervals[-1].timestamp if intervals else datetime.now(timezone.utc)
    
    return ValidationResult(
        symbol=symbol,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        pldot_range_metrics=pldot_range_metrics,
        hlc_range_metrics=hlc_range_metrics,
    )


def print_metrics_comparison(result: ValidationResult) -> None:
    """Print formatted comparison of envelope methods."""
    
    print("\n" + "=" * 80)
    print(f"ENVELOPE METHOD VALIDATION REPORT")
    print("=" * 80)
    print(f"Symbol: {result.symbol}")
    print(f"Interval: {result.interval}")
    print(f"Period: {result.start_date.strftime('%Y-%m-%d')} to {result.end_date.strftime('%Y-%m-%d')}")
    print("=" * 80)
    
    pr = result.pldot_range_metrics
    hr = result.hlc_range_metrics
    
    print(f"\n{'Metric':<35} {'pldot_range':>15} {'hlc_range':>15} {'Difference':>15}")
    print("-" * 80)
    
    # Containment metrics
    print("\nCONTAINMENT METRICS:")
    print(f"{'Total Bars':<35} {pr.total_bars:>15} {hr.total_bars:>15} {'-':>15}")
    print(f"{'Containment Rate':<35} {pr.containment_rate:>14.1%} {hr.containment_rate:>14.1%} {(hr.containment_rate - pr.containment_rate):>+14.1%}")
    print(f"{'Upper Breach Rate':<35} {pr.upper_breach_rate:>14.1%} {hr.upper_breach_rate:>14.1%} {(hr.upper_breach_rate - pr.upper_breach_rate):>+14.1%}")
    print(f"{'Lower Breach Rate':<35} {pr.lower_breach_rate:>14.1%} {hr.lower_breach_rate:>14.1%} {(hr.lower_breach_rate - pr.lower_breach_rate):>+14.1%}")
    
    # Touch metrics
    print("\nTOUCH METRICS:")
    print(f"{'Upper Touch Rate':<35} {pr.upper_touch_rate:>14.1%} {hr.upper_touch_rate:>14.1%} {(hr.upper_touch_rate - pr.upper_touch_rate):>+14.1%}")
    print(f"{'Lower Touch Rate':<35} {pr.lower_touch_rate:>14.1%} {hr.lower_touch_rate:>14.1%} {(hr.lower_touch_rate - pr.lower_touch_rate):>+14.1%}")
    print(f"{'Total Touch Rate':<35} {pr.total_touch_rate:>14.1%} {hr.total_touch_rate:>14.1%} {(hr.total_touch_rate - pr.total_touch_rate):>+14.1%}")
    
    # Reversal metrics
    print("\nREVERSAL METRICS (key for trading):")
    print(f"{'Upper Touch Reversal Rate':<35} {pr.upper_touch_reversal_rate:>14.1%} {hr.upper_touch_reversal_rate:>14.1%} {(hr.upper_touch_reversal_rate - pr.upper_touch_reversal_rate):>+14.1%}")
    print(f"{'Lower Touch Reversal Rate':<35} {pr.lower_touch_reversal_rate:>14.1%} {hr.lower_touch_reversal_rate:>14.1%} {(hr.lower_touch_reversal_rate - pr.lower_touch_reversal_rate):>+14.1%}")
    print(f"{'Overall Reversal Accuracy':<35} {pr.overall_reversal_accuracy:>14.1%} {hr.overall_reversal_accuracy:>14.1%} {(hr.overall_reversal_accuracy - pr.overall_reversal_accuracy):>+14.1%}")
    
    # Width metrics
    print("\nWIDTH METRICS:")
    print(f"{'Avg Width (% of price)':<35} {pr.avg_width_pct:>14.2f}% {hr.avg_width_pct:>14.2f}% {(hr.avg_width_pct - pr.avg_width_pct):>+14.2f}%")
    print(f"{'Min Width (% of price)':<35} {pr.min_width_pct:>14.2f}% {hr.min_width_pct:>14.2f}% {(hr.min_width_pct - pr.min_width_pct):>+14.2f}%")
    print(f"{'Max Width (% of price)':<35} {pr.max_width_pct:>14.2f}% {hr.max_width_pct:>14.2f}% {(hr.max_width_pct - pr.max_width_pct):>+14.2f}%")
    
    # Position metrics
    print("\nPOSITION METRICS:")
    print(f"{'Avg Position (0=lower, 1=upper)':<35} {pr.avg_position:>14.3f} {hr.avg_position:>14.3f} {(hr.avg_position - pr.avg_position):>+14.3f}")
    print(f"{'Position Std Dev':<35} {pr.position_std:>14.3f} {hr.position_std:>14.3f} {(hr.position_std - pr.position_std):>+14.3f}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY:")
    print("=" * 80)
    
    # Determine which method is better for each key metric
    better_containment = "pldot_range" if pr.containment_rate > hr.containment_rate else "hlc_range"
    better_reversal = "pldot_range" if pr.overall_reversal_accuracy > hr.overall_reversal_accuracy else "hlc_range"
    better_touch_rate = "pldot_range" if pr.total_touch_rate > hr.total_touch_rate else "hlc_range"
    
    print(f"Better Containment: {better_containment} ({max(pr.containment_rate, hr.containment_rate):.1%})")
    print(f"Better Reversal Accuracy: {better_reversal} ({max(pr.overall_reversal_accuracy, hr.overall_reversal_accuracy):.1%})")
    print(f"More Touches (trading opportunities): {better_touch_rate} ({max(pr.total_touch_rate, hr.total_touch_rate):.1%})")
    
    # Overall recommendation
    pr_score = (pr.containment_rate * 0.3 + pr.overall_reversal_accuracy * 0.5 + pr.total_touch_rate * 0.2)
    hr_score = (hr.containment_rate * 0.3 + hr.overall_reversal_accuracy * 0.5 + hr.total_touch_rate * 0.2)
    
    recommended = "pldot_range" if pr_score >= hr_score else "hlc_range"
    print(f"\nRecommended Method: {recommended}")
    print(f"(Weighted score: pldot_range={pr_score:.3f}, hlc_range={hr_score:.3f})")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Validate and compare envelope calculation methods"
    )
    parser.add_argument(
        "--symbol", 
        type=str, 
        default="AAPL",
        help="Symbol to analyze (default: AAPL)"
    )
    parser.add_argument(
        "--interval", 
        type=str, 
        default="30min",
        help="Data interval (default: 30min)"
    )
    parser.add_argument(
        "--days", 
        type=int, 
        default=30,
        help="Number of days of history to analyze (default: 30)"
    )
    parser.add_argument(
        "--period", 
        type=int, 
        default=3,
        help="PLdot/envelope period (default: 3)"
    )
    parser.add_argument(
        "--multiplier", 
        type=float, 
        default=1.5,
        help="Envelope multiplier (default: 1.5)"
    )
    parser.add_argument(
        "--symbols-file",
        type=str,
        help="Path to file with list of symbols (one per line)"
    )
    
    args = parser.parse_args()
    
    # Initialize
    settings = get_settings()
    
    # Determine symbols to process
    if args.symbols_file:
        with open(args.symbols_file) as f:
            symbols = [line.strip() for line in f if line.strip()]
    else:
        symbols = [args.symbol]
    
    # Connect to database and process symbols
    all_results = []
    with psycopg.connect(settings.database_url) as conn:
        for symbol in symbols:
            print(f"\nProcessing {symbol}...")
            result = validate_envelope_methods(
                conn=conn,
                symbol=symbol,
                interval=args.interval,
                days=args.days,
                period=args.period,
                multiplier=args.multiplier,
            )
            
            if result:
                all_results.append(result)
                print_metrics_comparison(result)
    
    # Aggregate summary if multiple symbols
    if len(all_results) > 1:
        print("\n" + "=" * 80)
        print("AGGREGATE SUMMARY ACROSS ALL SYMBOLS")
        print("=" * 80)
        
        # Calculate average metrics
        pr_containment = sum(r.pldot_range_metrics.containment_rate for r in all_results) / len(all_results)
        hr_containment = sum(r.hlc_range_metrics.containment_rate for r in all_results) / len(all_results)
        
        pr_reversal = sum(r.pldot_range_metrics.overall_reversal_accuracy for r in all_results) / len(all_results)
        hr_reversal = sum(r.hlc_range_metrics.overall_reversal_accuracy for r in all_results) / len(all_results)
        
        pr_touch = sum(r.pldot_range_metrics.total_touch_rate for r in all_results) / len(all_results)
        hr_touch = sum(r.hlc_range_metrics.total_touch_rate for r in all_results) / len(all_results)
        
        print(f"\nAverage Containment Rate: pldot_range={pr_containment:.1%}, hlc_range={hr_containment:.1%}")
        print(f"Average Reversal Accuracy: pldot_range={pr_reversal:.1%}, hlc_range={hr_reversal:.1%}")
        print(f"Average Touch Rate: pldot_range={pr_touch:.1%}, hlc_range={hr_touch:.1%}")
        
        # Count wins
        pr_wins = sum(1 for r in all_results if r.pldot_range_metrics.overall_reversal_accuracy >= r.hlc_range_metrics.overall_reversal_accuracy)
        hr_wins = len(all_results) - pr_wins
        
        print(f"\nReversal Accuracy Wins: pldot_range={pr_wins}, hlc_range={hr_wins}")
        print("=" * 80)


if __name__ == "__main__":
    main()