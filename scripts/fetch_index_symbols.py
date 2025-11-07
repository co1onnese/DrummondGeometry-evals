#!/usr/bin/env python3
"""
Fetch S&P 500 and Nasdaq 100 constituent symbols from Wikipedia.
Saves deduplicated list to CSV for reuse.
"""

import csv
import logging
import re
from pathlib import Path
from typing import Dict, List, Set

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Wikipedia URLs
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"

# Output directory
OUTPUT_DIR = Path(__file__).parent.parent / "data"


def fetch_sp500_symbols() -> List[Dict[str, str]]:
    """
    Fetch S&P 500 constituent symbols from Wikipedia.

    Returns:
        List of dicts with keys: symbol, name, sector, industry
    """
    logger.info("Fetching S&P 500 symbols from Wikipedia...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(SP500_URL, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch S&P 500 page: {e}")
        raise

    soup = BeautifulSoup(response.content, "lxml")

    # Find the constituents table - it's the first table with id "constituents"
    table = soup.find("table", {"id": "constituents"})
    if not table:
        # Fallback: find first table with class wikitable sortable
        table = soup.find("table", {"class": "wikitable sortable"})

    if not table:
        raise ValueError("Could not find S&P 500 constituents table on Wikipedia")

    symbols = []
    rows = table.find_all("tr")[1:]  # Skip header row

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 4:
            continue

        # Extract data
        symbol = cols[0].get_text(strip=True)
        name = cols[1].get_text(strip=True)
        sector = cols[2].get_text(strip=True) if len(cols) > 2 else ""
        industry = cols[3].get_text(strip=True) if len(cols) > 3 else ""

        # Clean symbol (remove any dots for Class A/B shares)
        # EODHD uses format like BRK.A, but we'll normalize
        symbol = symbol.replace(".", "-")

        symbols.append({
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "industry": industry,
            "index": "SP500"
        })

    logger.info(f"Fetched {len(symbols)} S&P 500 symbols")
    return symbols


def fetch_nasdaq100_symbols() -> List[Dict[str, str]]:
    """
    Fetch Nasdaq 100 constituent symbols from Wikipedia.

    Returns:
        List of dicts with keys: symbol, name, sector, industry
    """
    logger.info("Fetching Nasdaq 100 symbols from Wikipedia...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(NASDAQ100_URL, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch Nasdaq 100 page: {e}")
        raise

    soup = BeautifulSoup(response.content, "lxml")

    # Find the constituents table - look for table with id "constituents"
    table = soup.find("table", {"id": "constituents"})
    if not table:
        # Fallback: find table with specific class
        tables = soup.find_all("table", {"class": "wikitable sortable"})
        # Usually the first or second table
        for t in tables:
            # Check if it has "Ticker" or "Symbol" in header
            header = t.find("tr")
            if header and ("Ticker" in header.get_text() or "Symbol" in header.get_text()):
                table = t
                break

    if not table:
        raise ValueError("Could not find Nasdaq 100 constituents table on Wikipedia")

    symbols = []
    rows = table.find_all("tr")[1:]  # Skip header row

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 2:
            continue

        # Extract data - column order may vary
        # Common patterns: [Company, Ticker, Sector, Industry] or [Ticker, Company, Sector]
        # Let's be flexible

        # Try to find ticker (usually uppercase, short)
        ticker_col = None
        name_col = None

        for i, col in enumerate(cols[:3]):  # Check first 3 columns
            text = col.get_text(strip=True)
            # Ticker pattern: uppercase, 1-5 chars
            if re.match(r'^[A-Z]{1,5}$', text):
                ticker_col = i
            elif len(text) > 5 and not re.match(r'^[A-Z]{1,5}$', text):
                name_col = i

        if ticker_col is None:
            # If we can't determine, assume first column is company, second is ticker
            # or first is ticker, second is company
            if re.match(r'^[A-Z]{1,5}$', cols[0].get_text(strip=True)):
                ticker_col = 0
                name_col = 1
            else:
                ticker_col = 1
                name_col = 0

        symbol = cols[ticker_col].get_text(strip=True) if ticker_col is not None else ""
        name = cols[name_col].get_text(strip=True) if name_col is not None else ""
        sector = cols[2].get_text(strip=True) if len(cols) > 2 else ""
        industry = cols[3].get_text(strip=True) if len(cols) > 3 else ""

        if not symbol:
            continue

        # Clean symbol
        symbol = symbol.replace(".", "-")

        symbols.append({
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "industry": industry,
            "index": "NASDAQ100"
        })

    logger.info(f"Fetched {len(symbols)} Nasdaq 100 symbols")
    return symbols


def merge_and_deduplicate(sp500_symbols: List[Dict[str, str]],
                          nasdaq100_symbols: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Merge symbol lists and deduplicate.
    For overlapping symbols, mark them as members of both indices.

    Returns:
        Deduplicated list with index membership information
    """
    logger.info("Merging and deduplicating symbol lists...")

    symbol_map: Dict[str, Dict[str, str]] = {}

    # Add S&P 500 symbols
    for sym_data in sp500_symbols:
        symbol = sym_data["symbol"]
        symbol_map[symbol] = sym_data.copy()
        symbol_map[symbol]["indices"] = "SP500"

    # Add Nasdaq 100 symbols
    for sym_data in nasdaq100_symbols:
        symbol = sym_data["symbol"]
        if symbol in symbol_map:
            # Symbol is in both indices
            symbol_map[symbol]["indices"] = "SP500,NASDAQ100"
            logger.info(f"Overlap detected: {symbol} is in both S&P 500 and Nasdaq 100")
        else:
            symbol_map[symbol] = sym_data.copy()
            symbol_map[symbol]["indices"] = "NASDAQ100"

    # Convert back to list
    merged = list(symbol_map.values())

    logger.info(f"Total unique symbols: {len(merged)}")
    logger.info(f"S&P 500 only: {sum(1 for s in merged if s['indices'] == 'SP500')}")
    logger.info(f"Nasdaq 100 only: {sum(1 for s in merged if s['indices'] == 'NASDAQ100')}")
    logger.info(f"Both indices: {sum(1 for s in merged if 'SP500,NASDAQ100' in s['indices'])}")

    return sorted(merged, key=lambda x: x["symbol"])


def save_to_csv(symbols: List[Dict[str, str]], filename: str) -> Path:
    """
    Save symbols to CSV file.

    Args:
        symbols: List of symbol dictionaries
        filename: Output filename

    Returns:
        Path to saved CSV file
    """
    output_path = OUTPUT_DIR / filename
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(f"Saving {len(symbols)} symbols to {output_path}...")

    fieldnames = ["symbol", "name", "sector", "industry", "indices"]

    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for sym_data in symbols:
            # Remove the 'index' key if it exists (from individual lists)
            row = {k: v for k, v in sym_data.items() if k in fieldnames}
            writer.writerow(row)

    logger.info(f"Successfully saved to {output_path}")
    return output_path


def main() -> None:
    """Main execution function."""
    try:
        # Fetch symbols from Wikipedia
        sp500_symbols = fetch_sp500_symbols()
        nasdaq100_symbols = fetch_nasdaq100_symbols()

        # Merge and deduplicate
        all_symbols = merge_and_deduplicate(sp500_symbols, nasdaq100_symbols)

        # Save to CSV files
        # Save merged list
        merged_csv = save_to_csv(all_symbols, "index_constituents.csv")

        # Also save individual lists for reference
        save_to_csv(sp500_symbols, "sp500_constituents.csv")
        save_to_csv(nasdaq100_symbols, "nasdaq100_constituents.csv")

        logger.info("=" * 60)
        logger.info("Symbol fetch complete!")
        logger.info(f"Merged list: {merged_csv}")
        logger.info(f"Total unique symbols: {len(all_symbols)}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error fetching symbols: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
