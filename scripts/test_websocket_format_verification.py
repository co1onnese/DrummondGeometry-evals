#!/usr/bin/env python3
"""Enhanced test script for EODHD WebSocket format verification.

This script tests WebSocket connection and logs all messages to understand
the actual EODHD API format. Use this to verify message structure before
updating the production code.

Usage:
    python scripts/test_websocket_format_verification.py --symbols AAPL MSFT GOOGL
    python scripts/test_websocket_format_verification.py --test-subscription-formats
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import ssl
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from dgas.settings import get_settings
from rich.console import Console
from rich.table import Table

console = Console()

# EODHD WebSocket endpoint
# Correct URL format: wss://ws.eodhistoricaldata.com/ws/{exchange}?api_token={token}
# For US stocks, use exchange="us"
EODHD_WS_URL = "wss://ws.eodhistoricaldata.com/ws"

# Message log for analysis
message_log: List[Dict[str, Any]] = []


async def test_connection_basic(api_token: str, symbols: List[str], verify_ssl: bool = True) -> bool:
    """Test basic WebSocket connection."""
    console.print("[bold cyan]Testing Basic Connection...[/bold cyan]")
    
    # Try different URL formats with correct base URL
    # Correct format: wss://ws.eodhistoricaldata.com/ws/{exchange}?api_token={token}
    # For US trades: /ws/us
    # For US quotes: /ws/us-quote
    exchange = "us"  # For US stocks (trades endpoint)
    url_variants = [
        f"{EODHD_WS_URL}/{exchange}?api_token={api_token}",  # Correct format: /ws/us
    ]
    
    # SSL context - allow unverified for testing if needed
    ssl_context = False  # Use False to disable SSL entirely, or create unverified context
    if not verify_ssl:
        # Create SSL context that doesn't verify certificates
        try:
            # Try the private method first (Python 3.4+)
            ssl_context = ssl._create_unverified_context()
        except (AttributeError, TypeError):
            # Fallback: create context manually
            try:
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            except AttributeError:
                # Very old Python - use PROTOCOL_TLS
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        console.print(f"[yellow]⚠ SSL verification disabled for testing (context type: {type(ssl_context).__name__})[/yellow]")
    
    for url_idx, ws_url in enumerate(url_variants, 1):
        console.print(f"\n[cyan]Trying URL variant {url_idx}: {ws_url}[/cyan]")
        # Debug: verify URL construction
        if "/us" not in ws_url:
            console.print(f"[red]ERROR: URL missing /us exchange![/red]")
            console.print(f"[dim]EODHD_WS_URL={EODHD_WS_URL}, exchange={exchange}[/dim]")
        
        try:
            # Try connecting with SSL context
            # websockets library: ssl=False disables SSL, ssl=context uses context
            if not verify_ssl and ssl_context is not False:
                console.print(f"[dim]Using SSL context: check_hostname={getattr(ssl_context, 'check_hostname', 'N/A')}, verify_mode={getattr(ssl_context, 'verify_mode', 'N/A')}[/dim]")
                websocket_conn = websockets.connect(ws_url, ssl=ssl_context)
            elif not verify_ssl:
                # Last resort: try ssl=False (might not work for wss://)
                console.print("[yellow]Attempting connection without SSL verification...[/yellow]")
                websocket_conn = websockets.connect(ws_url, ssl=ssl_context)
            else:
                websocket_conn = websockets.connect(ws_url)
            
            async with websocket_conn as websocket:
                console.print("[green]✓[/green] Connected to WebSocket")
                
                # Test subscription format (official: symbols as comma-separated string)
                symbols_str = ",".join(symbols)
                subscribe_msg = {
                    "action": "subscribe",
                    "symbols": symbols_str,  # Comma-separated string, not array
                }
                subscribe_json = json.dumps(subscribe_msg)
                await websocket.send(subscribe_json)
                console.print(f"[cyan]Sent subscription: {subscribe_json}[/cyan]")
                console.print(f"[dim]  (symbols type: {type(subscribe_msg['symbols']).__name__}, value: {repr(subscribe_msg['symbols'])})[/dim]")
                
                # Wait for subscription confirmation or first message
                console.print("[yellow]Waiting for subscription confirmation or messages (30 seconds)...[/yellow]")
                console.print("[dim]Note: If market is closed, you may not receive trade updates[/dim]")
                start_time = time.time()
                messages_received = 0
                subscription_confirmed = False
                
                try:
                    while time.time() - start_time < 30:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                            messages_received += 1
                            
                            # Log raw message
                            log_entry = {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "raw_message": message,
                                "message_number": messages_received,
                            }
                            
                            # Try to parse JSON
                            try:
                                data = json.loads(message)
                                log_entry["parsed"] = data
                                log_entry["message_type"] = data.get("type") or data.get("action") or "unknown"
                                
                                # Print summary
                                msg_type = log_entry["message_type"]
                                
                                # Check for authorization/status messages
                                if "status_code" in data or "message" in data:
                                    status_code = data.get("status_code")
                                    message = data.get("message", "")
                                    if status_code == 200 or "authorized" in message.lower():
                                        console.print(f"[green]✓[/green] Authorized: {json.dumps(data, indent=2)}")
                                    elif "subscribed" in message.lower():
                                        subscription_confirmed = True
                                        console.print(f"[green]✓[/green] Subscription confirmed: {json.dumps(data, indent=2)}")
                                    else:
                                        console.print(f"[yellow]Status message: {json.dumps(data, indent=2)}[/yellow]")
                                elif msg_type in ["connected", "subscribed"] or data.get("action") == "subscribed":
                                    subscription_confirmed = True
                                    console.print(f"[green]✓[/green] Subscription confirmed: {json.dumps(data, indent=2)}")
                                elif "s" in data:  # EODHD format: "s" = symbol
                                    symbol = data.get("s", "unknown")
                                    price = data.get("p", "N/A")
                                    volume = data.get("v", "N/A")
                                    timestamp = data.get("t", "N/A")
                                    console.print(f"[green]✓[/green] Trade update: {symbol} @ ${price} vol={volume} t={timestamp}")
                                    if messages_received <= 5:  # Show full details for first 5
                                        console.print(f"[dim]Full message: {json.dumps(data, indent=2)}[/dim]")
                                elif "symbol" in data or "price" in str(data).lower():
                                    symbol = data.get("symbol") or data.get("code") or "unknown"
                                    console.print(f"[dim]Price update for {symbol}: {json.dumps(data, indent=2)}[/dim]")
                                else:
                                    console.print(f"[yellow]?[/yellow] Unknown message type: {json.dumps(data, indent=2)}")
                            except json.JSONDecodeError:
                                log_entry["parse_error"] = "Invalid JSON"
                                console.print(f"[red]✗[/red] Invalid JSON: {message[:200]}...")
                            
                            message_log.append(log_entry)
                            
                            # Print first 10 messages in detail
                            if messages_received <= 10:
                                console.print(f"\n[bold]Message #{messages_received}:[/bold]")
                                console.print(f"[dim]{json.dumps(log_entry, indent=2)}[/dim]\n")
                            
                        except asyncio.TimeoutError:
                            if messages_received == 0:
                                console.print("[yellow]No messages received yet...[/yellow]")
                            continue
                            
                except ConnectionClosed as e:
                    console.print(f"[yellow]Connection closed by server (code: {e.code}, reason: {e.reason})[/yellow]")
                    if not subscription_confirmed and messages_received == 0:
                        console.print("[red]⚠ Connection closed immediately after subscription - subscription may have been rejected[/red]")
                        console.print("[yellow]Check:[/yellow]")
                        console.print("  1. Subscription format (should be comma-separated string, not array)")
                        console.print("  2. Market hours (no data when market is closed)")
                        console.print("  3. API token permissions (WebSocket access may require premium plan)")
                
                console.print(f"\n[bold]Received {messages_received} messages total[/bold]")
                if subscription_confirmed:
                    console.print(f"[green]✓ Subscription confirmed![/green]")
                if messages_received > 0:
                    console.print(f"[green]✓ URL variant {url_idx} works![/green]")
                    return True
                elif subscription_confirmed:
                    console.print(f"[yellow]⚠ Subscription confirmed but no trade messages (market may be closed)[/yellow]")
                    return True  # Consider success if subscription was confirmed
                else:
                    console.print(f"[yellow]⚠ No messages received[/yellow]")
                    return False
                
        except (ssl.SSLCertVerificationError, ssl.SSLError) as e:
            error_msg = str(e)
            if "hostname" in error_msg.lower() or "certificate" in error_msg.lower():
                console.print(f"[yellow]✗ SSL certificate/hostname error with variant {url_idx}: {error_msg}[/yellow]")
                console.print("[yellow]This URL likely doesn't exist or has certificate issues[/yellow]")
            else:
                console.print(f"[yellow]✗ SSL error with variant {url_idx}: {error_msg}[/yellow]")
            
            if url_idx < len(url_variants):
                continue  # Try next variant
            else:
                console.print("\n[bold red]All URL variants failed![/bold red]")
                console.print("[yellow]Possible issues:[/yellow]")
                console.print("  1. WebSocket URL is incorrect - check EODHD documentation")
                console.print("  2. WebSocket requires different authentication")
                console.print("  3. WebSocket access not included in your API plan")
                console.print("  4. WebSocket service may be at a different endpoint")
                return False
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            console.print(f"[yellow]✗ Connection failed with variant {url_idx} ({error_type}): {error_msg}[/yellow]")
            
            # If it's a connection error (not SSL), this might be progress
            if "connection" in error_msg.lower() and "ssl" not in error_msg.lower():
                console.print("[dim]  (This might mean the URL exists but connection failed for other reasons)[/dim]")
            
            if url_idx < len(url_variants):
                continue  # Try next variant
            else:
                import traceback
                console.print(f"\n[bold red]All URL variants failed[/bold red]")
                console.print("[yellow]Recommendation: Check EODHD documentation for correct WebSocket URL[/yellow]")
                console.print(f"[dim]Last error traceback:\n{traceback.format_exc()}[/dim]")
                return False
    
    return False


async def test_subscription_formats(api_token: str, symbols: List[str], verify_ssl: bool = True) -> Dict[str, bool]:
    """Test different subscription message formats."""
    console.print("\n[bold cyan]Testing Subscription Formats...[/bold cyan]")
    
    # Official format: {"action": "subscribe", "symbols": "AAPL,TSLA"}
    # Symbols must be comma-separated string
    symbols_str = ",".join(symbols)
    
    formats = [
        {
            "name": "Format 1: Official format (comma-separated string)",
            "message": {"action": "subscribe", "symbols": symbols_str},
        },
        {
            "name": "Format 2: Array format (to test if it works)",
            "message": {"action": "subscribe", "symbols": symbols},
        },
        {
            "name": "Format 3: With .US suffix",
            "message": {"action": "subscribe", "symbols": ",".join([f"{s}.US" for s in symbols])},
        },
    ]
    
    results = {}
    exchange = "us"  # For US stocks
    ws_url = f"{EODHD_WS_URL}/{exchange}?api_token={api_token}"
    
    # SSL context
    ssl_context = None
    if not verify_ssl:
        try:
            ssl_context = ssl._create_unverified_context()
        except AttributeError:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
    
    for fmt in formats:
        console.print(f"\n[cyan]Testing: {fmt['name']}[/cyan]")
        try:
            if ssl_context:
                websocket_conn = websockets.connect(ws_url, ssl=ssl_context)
            else:
                websocket_conn = websockets.connect(ws_url)
            
            async with websocket_conn as websocket:
                # Send subscription
                await websocket.send(json.dumps(fmt["message"]))
                console.print(f"  [dim]Sent: {json.dumps(fmt['message'])}[/dim]")
                
                # Wait for response
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(response)
                    console.print(f"  [green]✓[/green] Response: {json.dumps(data, indent=2)}")
                    
                    # Check if subscription was accepted
                    if "error" in data or "Error" in str(data):
                        console.print(f"  [red]✗[/red] Subscription rejected")
                        results[fmt["name"]] = False
                    else:
                        console.print(f"  [green]✓[/green] Subscription accepted")
                        results[fmt["name"]] = True
                        
                        # Try to receive a price update
                        try:
                            price_msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                            price_data = json.loads(price_msg)
                            console.print(f"  [green]✓[/green] Price update received: {json.dumps(price_data, indent=2)}")
                        except asyncio.TimeoutError:
                            console.print(f"  [yellow]⚠[/yellow] No price update received (may be normal if market closed)")
                        
                except asyncio.TimeoutError:
                    console.print(f"  [yellow]⚠[/yellow] No response (may indicate format issue)")
                    results[fmt["name"]] = False
                except json.JSONDecodeError:
                    console.print(f"  [red]✗[/red] Invalid JSON response: {response[:200]}")
                    results[fmt["name"]] = False
                    
        except Exception as e:
            console.print(f"  [red]✗[/red] Error: {e}")
            results[fmt["name"]] = False
        
        # Small delay between tests
        await asyncio.sleep(2)
    
    return results


async def test_message_parsing(api_token: str, symbols: List[str], duration: int = 60, verify_ssl: bool = True) -> None:
    """Collect and analyze message samples."""
    console.print(f"\n[bold cyan]Collecting Message Samples ({duration}s)...[/bold cyan]")
    
    ws_url = f"{EODHD_WS_URL}?api_token={api_token}"
    samples: List[Dict[str, Any]] = []
    
    # SSL context
    ssl_context = None
    if not verify_ssl:
        try:
            ssl_context = ssl._create_unverified_context()
        except AttributeError:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
    
    try:
        if ssl_context:
            websocket_conn = websockets.connect(ws_url, ssl=ssl_context)
        else:
            websocket_conn = websockets.connect(ws_url)
        
        async with websocket_conn as websocket:
            # Subscribe (using official format: comma-separated string)
            symbols_str = ",".join(symbols)
            subscribe_msg = {"action": "subscribe", "symbols": symbols_str}
            await websocket.send(json.dumps(subscribe_msg))
            console.print(f"[cyan]Subscribed to {len(symbols)} symbols[/cyan]")
            
            start_time = time.time()
            while time.time() - start_time < duration:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(message)
                    
                    # Collect unique message structures
                    msg_keys = set(data.keys())
                    sample = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "keys": sorted(msg_keys),
                        "data": data,
                    }
                    
                    # Check if we've seen this structure before
                    is_new_structure = True
                    for existing in samples:
                        if existing["keys"] == sample["keys"]:
                            is_new_structure = False
                            break
                    
                    if is_new_structure:
                        samples.append(sample)
                        console.print(f"[green]✓[/green] New message structure: {sample['keys']}")
                        console.print(f"[dim]{json.dumps(data, indent=2)}[/dim]")
                    
                except asyncio.TimeoutError:
                    continue
                except json.JSONDecodeError:
                    console.print(f"[red]✗[/red] Invalid JSON: {message[:200]}")
                    
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]", exc_info=True)
    
    # Analyze samples
    console.print(f"\n[bold]Message Structure Analysis:[/bold]")
    console.print(f"Found {len(samples)} unique message structures\n")
    
    for i, sample in enumerate(samples, 1):
        console.print(f"[bold]Structure #{i}:[/bold]")
        console.print(f"  Keys: {', '.join(sample['keys'])}")
        console.print(f"  Sample: {json.dumps(sample['data'], indent=2)}\n")


def save_message_log(output_file: Path) -> None:
    """Save message log to file for analysis."""
    if not message_log:
        console.print("[yellow]No messages to save[/yellow]")
        return
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w") as f:
        json.dump(message_log, f, indent=2)
    
    console.print(f"[green]✓[/green] Saved {len(message_log)} messages to {output_file}")


def print_field_analysis() -> None:
    """Analyze message fields to determine EODHD format."""
    if not message_log:
        console.print("[yellow]No messages to analyze[/yellow]")
        return
    
    console.print("\n[bold cyan]Field Analysis:[/bold cyan]")
    
    # Collect all unique fields
    all_fields = set()
    price_fields = set()
    volume_fields = set()
    timestamp_fields = set()
    symbol_fields = set()
    
    for entry in message_log:
        if "parsed" in entry:
            data = entry["parsed"]
            all_fields.update(data.keys())
            
            # Check for price-like fields
            for key in data.keys():
                if any(term in key.lower() for term in ["price", "last", "close", "trade", "p"]):
                    price_fields.add(key)
                if any(term in key.lower() for term in ["volume", "vol", "v"]):
                    volume_fields.add(key)
                if any(term in key.lower() for term in ["time", "timestamp", "datetime", "t", "date"]):
                    timestamp_fields.add(key)
                if any(term in key.lower() for term in ["symbol", "code", "ticker", "s"]):
                    symbol_fields.add(key)
    
    console.print(f"\n[bold]All Fields Found:[/bold] {', '.join(sorted(all_fields))}")
    console.print(f"\n[bold]Price Fields:[/bold] {', '.join(sorted(price_fields)) if price_fields else 'None found'}")
    console.print(f"[bold]Volume Fields:[/bold] {', '.join(sorted(volume_fields)) if volume_fields else 'None found'}")
    console.print(f"[bold]Timestamp Fields:[/bold] {', '.join(sorted(timestamp_fields)) if timestamp_fields else 'None found'}")
    console.print(f"[bold]Symbol Fields:[/bold] {', '.join(sorted(symbol_fields)) if symbol_fields else 'None found'}")


async def main():
    """Main test function."""
    parser = argparse.ArgumentParser(description="Test EODHD WebSocket format")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["AAPL", "MSFT", "GOOGL"],
        help="Symbols to test (default: AAPL MSFT GOOGL)",
    )
    parser.add_argument(
        "--test-subscription",
        action="store_true",
        help="Test different subscription formats",
    )
    parser.add_argument(
        "--collect-samples",
        type=int,
        metavar="SECONDS",
        help="Collect message samples for specified duration",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("websocket_message_log.json"),
        help="Output file for message log (default: websocket_message_log.json)",
    )
    parser.add_argument(
        "--no-ssl-verify",
        action="store_true",
        help="Disable SSL certificate verification (for testing only)",
    )
    
    args = parser.parse_args()
    
    settings = get_settings()
    if not settings.eodhd_api_token:
        console.print("[bold red]Error: EODHD_API_TOKEN not configured[/bold red]")
        return 1
    
    console.print("[bold blue]EODHD WebSocket Format Verification[/bold blue]")
    console.print(f"Symbols: {', '.join(args.symbols)}")
    console.print(f"WebSocket URL: {EODHD_WS_URL}/us (for US exchange)\n")
    
    # Test 1: Basic connection
    success = await test_connection_basic(settings.eodhd_api_token, args.symbols)
    
    if not success:
        console.print("\n[bold red]Basic connection test failed![/bold red]")
        console.print("[yellow]Check API token and network connectivity[/yellow]")
        return 1
    
    # Test 2: Subscription formats
    if args.test_subscription:
        results = await test_subscription_formats(settings.eodhd_api_token, args.symbols)
        
        console.print("\n[bold]Subscription Format Results:[/bold]")
        table = Table()
        table.add_column("Format", style="cyan")
        table.add_column("Status", justify="center")
        
        for name, result in results.items():
            status = "[green]✓[/green] Accepted" if result else "[red]✗[/red] Rejected"
            table.add_row(name, status)
        
        console.print(table)
    
    # Test 3: Collect samples
    if args.collect_samples:
        await test_message_parsing(
            settings.eodhd_api_token, 
            args.symbols, 
            args.collect_samples,
            verify_ssl=not args.no_ssl_verify
        )
    
    # Analyze and save
    print_field_analysis()
    save_message_log(args.output)
    
    console.print("\n[bold green]✓ Verification complete![/bold green]")
    console.print(f"[yellow]Review {args.output} for detailed message analysis[/yellow]")
    console.print("[yellow]Update websocket_client.py with verified field names[/yellow]")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
