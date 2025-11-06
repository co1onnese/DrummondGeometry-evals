"""Generate data ingestion completeness reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Sequence

from ..db import get_connection


@dataclass
class SymbolIngestionStats:
    symbol: str
    exchange: str | None
    interval: str
    bar_count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    estimated_missing_bars: int

    def to_row(self) -> Sequence[str]:
        return (
            self.symbol,
            self.exchange or "",
            self.interval,
            str(self.bar_count),
            self.first_timestamp.isoformat() if self.first_timestamp else "",
            self.last_timestamp.isoformat() if self.last_timestamp else "",
            str(self.estimated_missing_bars),
        )


def generate_ingestion_report(interval: str = "30min") -> List[SymbolIngestionStats]:
    """Inspect the database and compute bar counts and coverage per symbol."""

    query = """
        SELECT
            s.symbol,
            s.exchange,
            %s AS interval_type,
            COUNT(md.data_id) AS bar_count,
            MIN(md.timestamp) AS first_timestamp,
            MAX(md.timestamp) AS last_timestamp,
            CASE
                WHEN COUNT(md.data_id) > 1 THEN
                    GREATEST(
                        0,
                        (
                            ((EXTRACT(EPOCH FROM (MAX(md.timestamp) - MIN(md.timestamp))) / %s)::bigint + 1)
                        ) - COUNT(md.data_id)
                    )
                ELSE 0
            END AS estimated_missing
        FROM market_symbols s
        LEFT JOIN market_data md
            ON md.symbol_id = s.symbol_id
            AND md.interval_type = %s
        GROUP BY s.symbol, s.exchange
        ORDER BY s.symbol;
    """

    interval_seconds = _interval_to_seconds(interval)

    results: List[SymbolIngestionStats] = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (interval, interval_seconds, interval))
            for row in cur.fetchall():
                symbol, exchange, interval_value, bar_count, first_ts, last_ts, estimated_missing = row
                stats = SymbolIngestionStats(
                    symbol=symbol,
                    exchange=exchange,
                    interval=interval_value,
                    bar_count=bar_count or 0,
                    first_timestamp=first_ts,
                    last_timestamp=last_ts,
                    estimated_missing_bars=estimated_missing or 0,
                )
                results.append(stats)
    return results


def render_markdown_report(stats: Iterable[SymbolIngestionStats]) -> str:
    """Render a simple Markdown table from stats."""

    rows = list(stats)
    header = "| Symbol | Exchange | Interval | Bars | First Timestamp | Last Timestamp | Missing |"
    separator = "| --- | --- | --- | ---: | --- | --- | ---: |"
    lines = [header, separator]
    for stat in rows:
        symbol, exchange, interval, count, first_ts, last_ts, missing = stat.to_row()
        line = (
            f"| {symbol} | {exchange} | {interval} | {count} | {first_ts} | {last_ts} | {missing} |"
        )
        lines.append(line)

    if len(lines) == 2:
        lines.append("| _no symbols_ |  |  | 0 |  |  | 0 |")

    return "\n".join(lines)


def write_report(stats: Iterable[SymbolIngestionStats], output_path: Path) -> None:
    output_path.write_text(render_markdown_report(stats), encoding="utf-8")


def _interval_to_seconds(interval: str) -> int:
    mapping = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    return mapping.get(interval, 1800)


__all__ = [
    "SymbolIngestionStats",
    "generate_ingestion_report",
    "render_markdown_report",
    "write_report",
]
