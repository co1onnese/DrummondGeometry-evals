# EODHD.com API Integration Architecture
## Drummond Geometry Analysis System

**Version:** 1.0  
**Date:** 2025-11-05  
**Status:** Technical Design Document  
**Author:** System Architecture Team

---

## Executive Summary

This document outlines the comprehensive integration architecture for EODHD.com's ALL-IN-ONE package API within the Drummond Geometry Analysis System. The integration provides high-quality, low-latency access to 30-minute US stock intervals, supporting the sophisticated calculations required for Drummond Geometry methodology including PL Dot calculations, multiple timeframe coordination, and real-time market analysis.

The architecture ensures robust, scalable, and fault-tolerant data ingestion with advanced caching, rate limiting, and data validation mechanisms to maintain the high standards required for professional trading analysis.

---

## 1. API Authentication and Connection Management

### 1.1 Authentication Strategy

**EODHD.com ALL-IN-ONE Package Authentication:**
```python
# Authentication Configuration
EODHD_CONFIG = {
    'base_url': 'https://eodhd.com/api',
    'token': os.getenv('EODHD_API_TOKEN'),
    'package': 'ALL-IN-ONE',
    'session_timeout': 300,  # 5 minutes
    'max_retries': 3
}
```

**Connection Management:**
- **Token Management:** Secure token storage with automatic refresh mechanisms
- **Session Pool:** Reusable connection pools with health monitoring
- **Connection Validation:** Pre-flight connection checks before data requests
- **Timeout Handling:** Configurable timeouts with graceful degradation

### 1.2 Connection Manager Implementation

```python
class EODHDConnectionManager:
    def __init__(self):
        self.session = requests.Session()
        self.token = self._get_valid_token()
        self.connection_pool = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3,
            pool_block=True
        )
        self.session.mount('https://', self.connection_pool)
    
    def _get_valid_token(self) -> str:
        """Validate and refresh API token if needed"""
        # Implement token validation logic
        pass
    
    async def create_connection(self) -> Connection:
        """Create and validate new connection"""
        # Connection creation logic
        pass
    
    async def health_check(self) -> bool:
        """Perform connection health check"""
        try:
            response = await self.session.get(f"{self.base_url}/ping")
            return response.status_code == 200
        except Exception:
            return False
```

### 1.3 Security Implementation

- **Token Encryption:** AES-256 encryption for stored tokens
- **Environment Variables:** Secure token injection via environment
- **Connection Logging:** Audit trail for all API interactions
- **Rate Limit Compliance:** Automatic adherence to API limits

---

## 2. Data Retrieval Strategies for 30-Minute US Stock Intervals

### 2.1 Data Structure Specifications

**30-Minute Interval Data Format:**
```json
{
    "code": "AAPL.US",
    "exchange_short_name": "US",
    "date": "2025-11-05",
    "open": 150.25,
    "high": 152.10,
    "low": 149.80,
    "close": 151.95,
    "adjusted_close": 151.75,
    "volume": 45678923,
    "timestamp": 1730889600000
}
```

### 2.2 Data Retrieval Implementation

```python
class EODHDDataRetriever:
    def __init__(self, connection_manager: EODHDConnectionManager):
        self.conn_mgr = connection_manager
        self.symbols = self._load_watchlist()
        self.batch_size = 50  # Process 50 symbols at a time
    
    async def fetch_30min_intervals(
        self, 
        symbols: List[str], 
        start_date: str, 
        end_date: str,
        timeout: int = 30
    ) -> Dict[str, List[IntervalData]]:
        """Fetch 30-minute intervals for multiple symbols"""
        
        results = {}
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests
        
        async def fetch_symbol(symbol: str) -> Tuple[str, List[IntervalData]]:
            async with semaphore:
                return symbol, await self._fetch_single_symbol(
                    symbol, start_date, end_date, timeout
                )
        
        tasks = [fetch_symbol(symbol) for symbol in symbols]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        for response in responses:
            if isinstance(response, tuple):
                symbol, data = response
                results[symbol] = data
        
        return results
    
    async def _fetch_single_symbol(
        self, 
        symbol: str, 
        start_date: str, 
        end_date: str, 
        timeout: int
    ) -> List[IntervalData]:
        """Fetch data for a single symbol with retry logic"""
        
        url = f"{self.base_url}/intraday/{symbol}"
        params = {
            'api_token': self.conn_mgr.token,
            'fmt': 'json',
            'start': start_date,
            'end': end_date,
            'interval': '30m',
            'limit': 50000
        }
        
        for attempt in range(self.max_retries):
            try:
                async with self.conn_mgr.session.get(url, params=params, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_interval_data(data)
                    elif response.status == 429:  # Rate limited
                        await self._handle_rate_limit(attempt)
                        continue
                    else:
                        raise EODHDAPIError(f"HTTP {response.status}")
                        
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return []
```

### 2.3 Data Transformation Pipeline

```python
class DataTransformer:
    def __init__(self):
        self.validator = DataValidator()
        self.enricher = DataEnricher()
    
    def transform_raw_data(self, raw_data: List[Dict]) -> List[IntervalData]:
        """Transform raw API response to standardized format"""
        
        transformed = []
        for record in raw_data:
            try:
                # Validate data integrity
                if not self.validator.validate_interval(record):
                    continue
                
                # Standardize format
                interval = IntervalData(
                    symbol=self._normalize_symbol(record['code']),
                    timestamp=self._parse_timestamp(record['date']),
                    open_price=float(record['open']),
                    high_price=float(record['high']),
                    low_price=float(record['low']),
                    close_price=float(record['close']),
                    adjusted_close=float(record.get('adjusted_close', record['close'])),
                    volume=int(record['volume']),
                    exchange=record.get('exchange_short_name', 'US')
                )
                
                # Enrich with calculated fields
                interval = self.enricher.enrich_interval(interval)
                transformed.append(interval)
                
            except Exception as e:
                logger.warning(f"Failed to transform record: {e}")
                continue
        
        return transformed
```

---

## 3. Rate Limiting and Error Handling Mechanisms

### 3.1 Rate Limiting Strategy

**Rate Limit Configuration:**
- **API Limits:** 100 requests/minute for ALL-IN-ONE package
- **Burst Limit:** 10 requests/second maximum
- **Daily Limit:** 50,000 requests/day
- **Rate Buffer:** 20% safety margin (80 requests/minute practical limit)

### 3.2 Rate Limiter Implementation

```python
import asyncio
from datetime import datetime, timedelta
from collections import deque

class EODHDRateLimiter:
    def __init__(self, max_requests: int = 80, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window  # seconds
        self.requests = deque()
        self.semaphore = asyncio.Semaphore(max_requests)
    
    async def acquire(self):
        """Acquire permission to make API request"""
        async with self.semaphore:
            now = datetime.now()
            
            # Remove old requests outside time window
            while self.requests and self.requests[0] < now - timedelta(seconds=self.time_window):
                self.requests.popleft()
            
            # Check if we can make a request
            if len(self.requests) >= self.max_requests:
                sleep_time = self.time_window - (now - self.requests[0]).total_seconds()
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    return await self.acquire()
            
            # Record this request
            self.requests.append(now)
    
    async def make_request(self, request_func, *args, **kwargs):
        """Make a rate-limited API request"""
        await self.acquire()
        return await request_func(*args, **kwargs)
```

### 3.3 Comprehensive Error Handling

```python
class EODHDErrorHandler:
    def __init__(self):
        self.retry_strategies = {
            429: self._handle_rate_limit,
            500: self._handle_server_error,
            502: self._handle_bad_gateway,
            503: self._handle_service_unavailable,
            504: self._handle_gateway_timeout
        }
    
    async def handle_request_error(self, response, attempt: int, max_attempts: int):
        """Handle API request errors with appropriate strategies"""
        
        status_code = response.status
        
        if status_code in self.retry_strategies:
            return await self.retry_strategies[status_code](response, attempt, max_attempts)
        
        elif 500 <= status_code < 600:
            return await self._handle_server_error(response, attempt, max_attempts)
        
        elif status_code == 404:
            raise EODHDNotFoundError(f"Symbol not found: {response.url}")
        
        elif status_code == 401:
            raise EODHDAuthenticationError("Invalid API token")
        
        else:
            raise EODHDAPIError(f"Unexpected error: {status_code}")
    
    async def _handle_rate_limit(self, response, attempt: int, max_attempts: int):
        """Handle rate limit with exponential backoff"""
        retry_after = int(response.headers.get('Retry-After', 60))
        sleep_time = min(retry_after, 2 ** attempt * 5)  # Max 5 minutes
        
        logger.warning(f"Rate limited. Sleeping for {sleep_time} seconds")
        await asyncio.sleep(sleep_time)
        
        if attempt < max_attempts - 1:
            return True  # Retry
        
        raise EODHDRateLimitError("Maximum retry attempts reached for rate limiting")
```

---

## 4. Data Validation and Transformation Pipelines

### 4.1 Data Quality Validation

```python
class DataValidator:
    def __init__(self):
        self.volume_threshold = 1000  # Minimum volume for validity
        self.price_tolerance = 0.001  # 0.1% price variation tolerance
    
    def validate_interval(self, data: Dict) -> bool:
        """Validate data quality and integrity"""
        
        required_fields = ['code', 'open', 'high', 'low', 'close', 'volume']
        
        # Check required fields
        if not all(field in data for field in required_fields):
            return False
        
        # Validate price relationships
        if not self._validate_price_relationships(data):
            return False
        
        # Validate volume
        if data['volume'] < self.volume_threshold:
            return False
        
        # Validate timestamp
        if not self._validate_timestamp(data.get('date')):
            return False
        
        return True
    
    def _validate_price_relationships(self, data: Dict) -> bool:
        """Validate OHLC relationships"""
        open_price = float(data['open'])
        high_price = float(data['high'])
        low_price = float(data['low'])
        close_price = float(data['close'])
        
        # High must be >= all other prices
        # Low must be <= all other prices
        return (
            high_price >= open_price and
            high_price >= close_price and
            low_price <= open_price and
            low_price <= close_price
        )
```

### 4.2 Data Transformation Pipeline

```python
class DataPipeline:
    def __init__(self):
        self.validators = [
            DataValidator(),
            VolumeValidator(),
            PriceValidator(),
            TimestampValidator()
        ]
        self.transformers = [
            PriceAdjuster(),
            VolumeNormalizer(),
            TimezoneConverter()
        ]
        self.enrichers = [
            TechnicalIndicatorCalculator(),
            MovingAverageCalculator(),
            SupportResistanceCalculator()
        ]
    
    async def process_batch(self, raw_data: List[Dict]) -> List[EnrichedInterval]:
        """Complete pipeline for data processing"""
        
        # Stage 1: Validation
        valid_data = []
        for record in raw_data:
            if self._validate_all(record):
                valid_data.append(record)
            else:
                logger.warning(f"Invalid record skipped: {record}")
        
        # Stage 2: Transformation
        transformed_data = []
        for record in valid_data:
            try:
                transformed = self._transform_record(record)
                transformed_data.append(transformed)
            except Exception as e:
                logger.error(f"Failed to transform record: {e}")
        
        # Stage 3: Enrichment
        enriched_data = []
        for record in transformed_data:
            try:
                enriched = self._enrich_record(record)
                enriched_data.append(enriched)
            except Exception as e:
                logger.error(f"Failed to enrich record: {e}")
        
        return enriched_data
```

---

## 5. Batch Processing for Multiple Symbols

### 5.1 Batch Processing Architecture

```python
class BatchProcessor:
    def __init__(self, connection_manager: EODHDConnectionManager):
        self.conn_mgr = connection_manager
        self.batch_size = 50
        self.concurrency_limit = 10
        self.semaphore = asyncio.Semaphore(self.concurrency_limit)
    
    async def process_symbols_batch(
        self, 
        symbols: List[str], 
        start_date: str, 
        end_date: str
    ) -> Dict[str, List[EnrichedInterval]]:
        """Process symbols in optimized batches"""
        
        # Split symbols into batches
        batches = self._create_batches(symbols, self.batch_size)
        results = {}
        
        for batch in batches:
            batch_results = await self._process_single_batch(
                batch, start_date, end_date
            )
            results.update(batch_results)
        
        return results
    
    def _create_batches(self, symbols: List[str], batch_size: int) -> List[List[str]]:
        """Create batches for processing"""
        return [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
    
    async def _process_single_batch(
        self, 
        symbols: List[str], 
        start_date: str, 
        end_date: str
    ) -> Dict[str, List[EnrichedInterval]]:
        """Process a single batch of symbols"""
        
        async def process_symbol(symbol: str) -> Tuple[str, List[EnrichedInterval]]:
            async with self.semaphore:
                try:
                    data = await self.conn_mgr.fetch_30min_intervals(
                        [symbol], start_date, end_date
                    )
                    return symbol, data.get(symbol, [])
                except Exception as e:
                    logger.error(f"Failed to process {symbol}: {e}")
                    return symbol, []
        
        tasks = [process_symbol(symbol) for symbol in symbols]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = {}
        for response in responses:
            if isinstance(response, tuple):
                symbol, data = response
                results[symbol] = data
        
        return results
```

### 5.2 Progress Tracking and Monitoring

```python
class BatchProgressTracker:
    def __init__(self, total_symbols: int):
        self.total_symbols = total_symbols
        self.processed_symbols = 0
        self.failed_symbols = 0
        self.start_time = datetime.now()
        self.progress_callback = None
    
    def update_progress(self, symbol: str, success: bool):
        """Update processing progress"""
        if success:
            self.processed_symbols += 1
        else:
            self.failed_symbols += 1
        
        self._notify_progress()
    
    def _notify_progress(self):
        """Notify progress to callbacks"""
        if self.progress_callback:
            progress = {
                'processed': self.processed_symbols,
                'failed': self.failed_symbols,
                'total': self.total_symbols,
                'percentage': (self.processed_symbols + self.failed_symbols) / self.total_symbols * 100,
                'eta': self._calculate_eta()
            }
            self.progress_callback(progress)
    
    def _calculate_eta(self) -> timedelta:
        """Calculate estimated time to completion"""
        elapsed = datetime.now() - self.start_time
        completed = self.processed_symbols + self.failed_symbols
        
        if completed == 0:
            return timedelta(0)
        
        avg_time_per_symbol = elapsed / completed
        remaining_symbols = self.total_symbols - completed
        
        return timedelta(seconds=avg_time_per_symbol * remaining_symbols)
```

---

## 6. Historical Data Backfill Procedures

### 6.1 Backfill Strategy

```python
class HistoricalBackfill:
    def __init__(self, connection_manager: EODHDConnectionManager):
        self.conn_mgr = connection_manager
        self.max_date_range = 365  # Days per request
        self.backfill_chunk_size = 100  # Symbols per chunk
    
    async def backfill_symbols(
        self, 
        symbols: List[str], 
        start_date: str, 
        end_date: str,
        callback: Optional[Callable] = None
    ) -> Dict[str, List[EnrichedInterval]]:
        """Perform historical data backfill for multiple symbols"""
        
        results = {}
        total_symbols = len(symbols)
        processed = 0
        
        # Process symbols in chunks
        for i in range(0, len(symbols), self.backfill_chunk_size):
            chunk = symbols[i:i + self.backfill_chunk_size]
            
            logger.info(f"Processing backfill chunk {i//self.backfill_chunk_size + 1}, "
                       f"symbols {i+1}-{min(i+self.backfill_chunk_size, total_symbols)}")
            
            try:
                # Split date range if needed
                date_chunks = self._split_date_range(start_date, end_date, self.max_date_range)
                
                for date_chunk in date_chunks:
                    chunk_results = await self._process_backfill_chunk(
                        chunk, date_chunk['start'], date_chunk['end']
                    )
                    
                    # Merge results
                    for symbol, data in chunk_results.items():
                        if symbol not in results:
                            results[symbol] = []
                        results[symbol].extend(data)
                
                processed += len(chunk)
                
                if callback:
                    callback({
                        'processed': processed,
                        'total': total_symbols,
                        'percentage': processed / total_symbols * 100
                    })
                
                # Rate limiting delay between chunks
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Failed to process chunk: {e}")
                continue
        
        return results
    
    def _split_date_range(self, start_date: str, end_date: str, max_days: int) -> List[Dict]:
        """Split date range into chunks not exceeding max_days"""
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        current = start
        
        chunks = []
        while current < end:
            chunk_end = min(current + timedelta(days=max_days), end)
            
            chunks.append({
                'start': current.strftime('%Y-%m-%d'),
                'end': chunk_end.strftime('%Y-%m-%d')
            })
            
            current = chunk_end + timedelta(days=1)
        
        return chunks
```

### 6.2 Data Integrity Verification

```python
class BackfillIntegrityChecker:
    def __init__(self):
        self.expected_intervals_per_day = 26.5  # For 30-min intervals, accounting for market hours
        self.missing_data_threshold = 0.05  # 5% missing data acceptable
    
    def verify_symbol_integrity(
        self, 
        symbol: str, 
        data: List[EnrichedInterval], 
        start_date: str, 
        end_date: str
    ) -> Dict[str, any]:
        """Verify data integrity for a backfilled symbol"""
        
        # Sort data by timestamp
        sorted_data = sorted(data, key=lambda x: x.timestamp)
        
        # Check for gaps
        gaps = self._detect_gaps(sorted_data, start_date, end_date)
        
        # Check data completeness
        total_days = (datetime.strptime(end_date, '%Y-%m-%d') - 
                     datetime.strptime(start_date, '%Y-%m-%d')).days + 1
        expected_intervals = int(total_days * self.expected_intervals_per_day)
        actual_intervals = len(data)
        completeness = actual_intervals / expected_intervals
        
        # Check for duplicate timestamps
        duplicates = self._detect_duplicates(sorted_data)
        
        return {
            'symbol': symbol,
            'completeness': completeness,
            'missing_intervals': expected_intervals - actual_intervals,
            'gaps': gaps,
            'duplicates': len(duplicates),
            'is_acceptable': completeness >= (1 - self.missing_data_threshold) and len(gaps) == 0
        }
    
    def _detect_gaps(self, data: List[EnrichedInterval], start_date: str, end_date: str) -> List[Dict]:
        """Detect gaps in the data timeline"""
        if not data:
            return []
        
        gaps = []
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        # Check for market opening gaps (weekends, holidays)
        current_date = start_dt
        data_dates = {dt.date() for dt in [d.timestamp for d in data]}
        
        while current_date <= end_dt:
            if current_date.weekday() < 5 and current_date.date() not in data_dates:  # Weekday
                gaps.append({
                    'date': current_date.strftime('%Y-%m-%d'),
                    'type': 'missing_market_day',
                    'severity': 'high'
                })
            current_date += timedelta(days=1)
        
        return gaps
```

---

## 7. Real-Time Data Streaming for Today's Data

### 7.1 Real-Time Streaming Implementation

```python
import asyncio
import websockets
from datetime import datetime, timedelta

class EODHDRealTimeStreamer:
    def __init__(self, connection_manager: EODHDConnectionManager):
        self.conn_mgr = connection_manager
        self.subscribers = {}
        self.stream_active = False
        self.update_interval = 30  # seconds for 30-minute intervals
    
    async def start_streaming(
        self, 
        symbols: List[str], 
        callback: Callable[[str, EnrichedInterval], None]
    ) -> None:
        """Start real-time data streaming"""
        
        self.stream_active = True
        
        # Subscribe to symbols
        for symbol in symbols:
            self.subscribers[symbol] = callback
        
        # Start streaming loop
        try:
            await self._streaming_loop(symbols)
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            await self._handle_stream_error(e)
        finally:
            self.stream_active = False
    
    async def _streaming_loop(self, symbols: List[str]):
        """Main streaming loop"""
        
        while self.stream_active:
            try:
                # Fetch latest data for all symbols
                today = datetime.now().strftime('%Y-%m-%d')
                
                for symbol in symbols:
                    try:
                        latest_data = await self._fetch_latest_interval(symbol, today)
                        
                        if latest_data:
                            # Notify subscribers
                            callback = self.subscribers.get(symbol)
                            if callback:
                                await callback(symbol, latest_data)
                        
                    except Exception as e:
                        logger.error(f"Error fetching latest data for {symbol}: {e}")
                
                # Wait for next update cycle
                await asyncio.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"Streaming loop error: {e}")
                await asyncio.sleep(5)  # Brief pause before retry
    
    async def _fetch_latest_interval(self, symbol: str, date: str) -> Optional[EnrichedInterval]:
        """Fetch the latest interval data for a symbol"""
        
        try:
            # Try real-time endpoint first
            url = f"{self.base_url}/real-time/{symbol}"
            params = {
                'api_token': self.conn_mgr.token,
                'fmt': 'json'
            }
            
            response = await self.conn_mgr.session.get(url, params=params)
            
            if response.status == 200:
                data = await response.json()
                return self._parse_realtime_data(data)
            
            # Fallback to intraday endpoint for today's date
            return await self._fetch_from_intraday(symbol, date)
            
        except Exception as e:
            logger.error(f"Failed to fetch latest data for {symbol}: {e}")
            return None
    
    async def _fetch_from_intraday(self, symbol: str, date: str) -> Optional[EnrichedInterval]:
        """Fallback to intraday endpoint"""
        
        url = f"{self.base_url}/intraday/{symbol}"
        params = {
            'api_token': self.conn_mgr.token,
            'fmt': 'json',
            'start': date,
            'end': date,
            'interval': '30m'
        }
        
        response = await self.conn_mgr.session.get(url, params=params)
        
        if response.status == 200:
            data = await response.json()
            if data:
                return self._transform_single_record(data[-1])  # Latest record
        
        return None
```

### 7.2 Data Quality for Real-Time

```python
class RealTimeDataQualityMonitor:
    def __init__(self):
        self.quality_thresholds = {
            'max_price_change_rate': 0.10,  # 10% change per interval
            'min_volume': 1000,
            'max_volume_spike': 10.0  # 10x normal volume
        }
    
    def validate_realtime_data(self, previous_data: EnrichedInterval, new_data: EnrichedInterval) -> bool:
        """Validate real-time data quality"""
        
        # Check price change rate
        if previous_data:
            price_change = abs(new_data.close_price - previous_data.close_price) / previous_data.close_price
            if price_change > self.quality_thresholds['max_price_change_rate']:
                logger.warning(f"Large price change detected: {price_change:.2%}")
                return False
        
        # Check volume reasonableness
        if new_data.volume < self.quality_thresholds['min_volume']:
            logger.warning(f"Low volume: {new_data.volume}")
            return False
        
        # Check for volume spikes
        if previous_data and new_data.volume > previous_data.volume * self.quality_thresholds['max_volume_spike']:
            logger.warning(f"Volume spike detected: {new_data.volume} vs {previous_data.volume}")
        
        return True
    
    def detect_anomalies(self, data_stream: List[EnrichedInterval]) -> List[Anomaly]:
        """Detect anomalies in real-time data stream"""
        
        anomalies = []
        
        if len(data_stream) < 2:
            return anomalies
        
        # Calculate moving averages for anomaly detection
        ma_20 = self._calculate_moving_average(data_stream, 20)
        ma_50 = self._calculate_moving_average(data_stream, 50)
        
        for i, interval in enumerate(data_stream):
            # Price anomalies
            if ma_20 and i >= len(ma_20):
                deviation = abs(interval.close_price - ma_20[i]) / ma_20[i]
                if deviation > 0.02:  # 2% deviation
                    anomalies.append(Anomaly(
                        timestamp=interval.timestamp,
                        type='price_anomaly',
                        symbol=interval.symbol,
                        severity='medium',
                        details={'deviation': deviation, 'expected': ma_20[i], 'actual': interval.close_price}
                    ))
            
            # Volume anomalies
            if ma_50 and i >= len(ma_50):
                volume_ratio = interval.volume / ma_50[i] if ma_50[i] > 0 else 0
                if volume_ratio > 5.0:  # 5x normal volume
                    anomalies.append(Anomaly(
                        timestamp=interval.timestamp,
                        type='volume_anomaly',
                        symbol=interval.symbol,
                        severity='high',
                        details={'volume_ratio': volume_ratio}
                    ))
        
        return anomalies
```

---

## 8. Data Quality Checks and Anomaly Detection

### 8.1 Comprehensive Data Quality Framework

```python
class DataQualityFramework:
    def __init__(self):
        self.checks = [
            DataCompletenessCheck(),
            DataAccuracyCheck(),
            DataConsistencyCheck(),
            DataTimelinessCheck(),
            DataUniquenessCheck()
        ]
        self.anomaly_detectors = [
            PriceAnomalyDetector(),
            VolumeAnomalyDetector(),
            TimeAnomalyDetector(),
            GapAnomalyDetector()
        ]
    
    async def run_quality_assessment(
        self, 
        data: Dict[str, List[EnrichedInterval]]
    ) -> DataQualityReport:
        """Run comprehensive quality assessment"""
        
        report = DataQualityReport()
        
        for symbol, intervals in data.items():
            symbol_report = SymbolQualityReport(symbol=symbol)
            
            # Run quality checks
            for check in self.checks:
                check_result = await check.run(intervals)
                symbol_report.add_check_result(check_result)
            
            # Detect anomalies
            anomalies = []
            for detector in self.anomaly_detectors:
                detected = detector.detect(intervals)
                anomalies.extend(detected)
            
            symbol_report.anomalies = anomalies
            report.add_symbol_report(symbol_report)
        
        return report
    
    def generate_quality_metrics(self, report: DataQualityReport) -> Dict[str, float]:
        """Generate quality metrics"""
        
        metrics = {
            'overall_completeness': report.average_completeness,
            'overall_accuracy': report.average_accuracy,
            'anomaly_rate': report.total_anomalies / report.total_intervals,
            'data_freshness': report.average_freshness,
            'symbol_coverage': report.covered_symbols / report.total_symbols
        }
        
        return metrics
```

### 8.2 Specific Anomaly Detection

```python
class PriceAnomalyDetector:
    def __init__(self):
        self.volatility_threshold = 3.0  # 3 standard deviations
        self.min_history = 20  # Minimum data points for statistical analysis
    
    def detect(self, intervals: List[EnrichedInterval]) -> List[Anomaly]:
        """Detect price-related anomalies"""
        
        if len(intervals) < self.min_history:
            return []
        
        anomalies = []
        
        # Calculate returns
        returns = []
        for i in range(1, len(intervals)):
            prev_close = intervals[i-1].close_price
            curr_close = intervals[i].close_price
            return_rate = (curr_close - prev_close) / prev_close
            returns.append(return_rate)
        
        # Statistical analysis
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        for i, interval in enumerate(intervals[1:], 1):
            if std_return > 0:  # Avoid division by zero
                z_score = abs(interval.close_price - intervals[i-1].close_price) / std_return
                
                if z_score > self.volatility_threshold:
                    anomalies.append(Anomaly(
                        timestamp=interval.timestamp,
                        type='price_anomaly',
                        symbol=interval.symbol,
                        severity='high' if z_score > 5.0 else 'medium',
                        details={
                            'z_score': z_score,
                            'expected_range': (mean_return - 2*std_return, mean_return + 2*std_return),
                            'actual_change': (interval.close_price - intervals[i-1].close_price) / intervals[i-1].close_price
                        }
                    ))
        
        return anomalies

class VolumeAnomalyDetector:
    def __init__(self):
        self.volume_spike_threshold = 5.0  # 5x average volume
        self.volume_drop_threshold = 0.1   # Less than 10% of average
    
    def detect(self, intervals: List[EnrichedInterval]) -> List[Anomaly]:
        """Detect volume-related anomalies"""
        
        if len(intervals) < 20:
            return []
        
        anomalies = []
        volumes = [interval.volume for interval in intervals]
        avg_volume = np.mean(volumes)
        
        for interval in intervals:
            volume_ratio = interval.volume / avg_volume if avg_volume > 0 else 0
            
            if volume_ratio > self.volume_spike_threshold:
                anomalies.append(Anomaly(
                    timestamp=interval.timestamp,
                    type='volume_spike',
                    symbol=interval.symbol,
                    severity='medium',
                    details={
                        'volume_ratio': volume_ratio,
                        'current_volume': interval.volume,
                        'average_volume': avg_volume
                    }
                ))
            elif volume_ratio < self.volume_drop_threshold:
                anomalies.append(Anomaly(
                    timestamp=interval.timestamp,
                    type='volume_drop',
                    symbol=interval.symbol,
                    severity='medium',
                    details={
                        'volume_ratio': volume_ratio,
                        'current_volume': interval.volume,
                        'average_volume': avg_volume
                    }
                ))
        
        return anomalies
```

---

## 9. Caching Strategies for Performance Optimization

### 9.1 Multi-Level Caching Architecture

```python
import redis
from typing import Optional
import pickle
import hashlib

class EODHDCacheManager:
    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
        self.memory_cache = {}
        self.cache_tiers = {
            'l1_memory': {
                'max_size': 1000,  # Maximum items
                'ttl': 300,        # 5 minutes
                'strategy': 'LRU'
            },
            'l2_redis': {
                'max_size': 10000, # Maximum items
                'ttl': 3600,       # 1 hour
                'strategy': 'TTL'
            },
            'l3_persistent': {
                'max_size': 100000, # Maximum items
                'ttl': 86400,      # 24 hours
                'strategy': 'TTL'
            }
        }
    
    async def get(self, key: str) -> Optional[bytes]:
        """Get data from cache with multi-tier lookup"""
        
        # L1: Memory cache
        if key in self.memory_cache:
            item, timestamp = self.memory_cache[key]
            if self._is_valid(item['ttl'], timestamp):
                return item['data']
            else:
                del self.memory_cache[key]
        
        # L2: Redis cache
        try:
            data = self.redis_client.get(key)
            if data:
                # Promote to memory cache
                await self._promote_to_memory(key, data)
                return data
        except Exception as e:
            logger.warning(f"Redis cache error: {e}")
        
        # L3: Persistent storage (if implemented)
        return None
    
    async def set(self, key: str, data: bytes, ttl: int = 3600):
        """Set data in cache across multiple tiers"""
        
        # L1: Memory cache
        await self._set_memory_cache(key, data, ttl)
        
        # L2: Redis cache
        try:
            await asyncio.to_thread(self.redis_client.setex, key, ttl, data)
        except Exception as e:
            logger.warning(f"Redis cache set error: {e}")
        
        # L3: Persistent storage (if needed)
        if ttl > 3600:  # Only for longer TTL data
            await self._set_persistent_cache(key, data, ttl)
    
    async def _set_memory_cache(self, key: str, data: bytes, ttl: int):
        """Set data in L1 memory cache"""
        
        # Implement LRU eviction if needed
        if len(self.memory_cache) >= self.cache_tiers['l1_memory']['max_size']:
            self._evict_lru()
        
        self.memory_cache[key] = {
            'data': data,
            'ttl': ttl,
            'timestamp': datetime.now()
        }
    
    def _evict_lru(self):
        """Evict least recently used item from memory cache"""
        if not self.memory_cache:
            return
        
        # Find LRU item
        lru_key = min(self.memory_cache.keys(), 
                     key=lambda k: self.memory_cache[k]['timestamp'])
        del self.memory_cache[lru_key]
    
    def _is_valid(self, ttl: int, timestamp: datetime) -> bool:
        """Check if cache item is still valid"""
        return (datetime.now() - timestamp).total_seconds() < ttl
```

### 9.2 Smart Caching Strategies

```python
class SmartCacheStrategy:
    def __init__(self, cache_manager: EODHDCacheManager):
        self.cache_mgr = cache_manager
        self.prefetch_patterns = {
            'market_hours': ('08:00', '17:00'),
            'pre_market': ('04:00', '08:00'),
            'after_hours': ('17:00', '20:00')
        }
    
    async def get_with_smart_caching(
        self, 
        symbol: str, 
        date: str, 
        interval_type: str = '30m'
    ) -> Optional[bytes]:
        """Get data with intelligent caching logic"""
        
        cache_key = self._generate_cache_key(symbol, date, interval_type)
        
        # Check cache first
        data = await self.cache_mgr.get(cache_key)
        if data:
            return data
        
        # Check if we should prefetch related data
        if self._should_prefetch(symbol, date):
            await self._prefetch_related_data(symbol, date)
        
        # Return None to indicate cache miss
        return None
    
    def _should_prefetch(self, symbol: str, date: str) -> bool:
        """Determine if we should prefetch related data"""
        
        current_time = datetime.now().time()
        market_open = datetime.strptime('08:00', '%H:%M').time()
        market_close = datetime.strptime('17:00', '%H:%M').time()
        
        # Prefetch during market hours for active symbols
        if market_open <= current_time <= market_close:
            return True
        
        # Prefetch end-of-day data after market close
        if current_time > market_close:
            return True
        
        return False
    
    async def _prefetch_related_data(self, symbol: str, date: str):
        """Prefetch related data based on usage patterns"""
        
        # Prefetch adjacent trading days
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        
        # Previous trading day
        prev_date = self._get_previous_trading_day(date_obj).strftime('%Y-%m-%d')
        await self._prefetch_symbol_date(symbol, prev_date)
        
        # Next trading day (if it's a trading day)
        next_date = self._get_next_trading_day(date_obj).strftime('%Y-%m-%d')
        await self._prefetch_symbol_date(symbol, next_date)
        
        # Prefetch related symbols (similar tickers, sector ETFs, etc.)
        related_symbols = self._get_related_symbols(symbol)
        for related_symbol in related_symbols[:5]:  # Limit to top 5
            await self._prefetch_symbol_date(related_symbol, date)
    
    async def _prefetch_symbol_date(self, symbol: str, date: str):
        """Prefetch data for a specific symbol and date"""
        
        cache_key = self._generate_cache_key(symbol, date, '30m')
        
        # Check if already cached
        if await self.cache_mgr.get(cache_key):
            return
        
        try:
            # Fetch data in background
            data = await self._fetch_data_async(symbol, date)
            if data:
                await self.cache_mgr.set(cache_key, data, ttl=7200)  # 2 hours
        except Exception as e:
            logger.warning(f"Prefetch failed for {symbol} {date}: {e}")
```

### 9.3 Cache Invalidation and Updates

```python
class CacheInvalidationManager:
    def __init__(self, cache_manager: EODHDCacheManager):
        self.cache_mgr = cache_manager
        self.invalidation_rules = {
            'real_time_update': self._invalidate_realtime_updates,
            'market_close': self._invalidate_daily_cache,
            'symbol_change': self._invalidate_symbol_cache
        }
    
    async def invalidate_on_update(self, symbol: str, update_type: str, timestamp: datetime):
        """Invalidate cache based on update events"""
        
        if update_type in self.invalidation_rules:
            await self.invalidation_rules[update_type](symbol, timestamp)
    
    async def _invalidate_realtime_updates(self, symbol: str, timestamp: datetime):
        """Invalidate cache for real-time updates"""
        
        # Invalidate today's cache for the symbol
        today = timestamp.strftime('%Y-%m-%d')
        cache_key = self._generate_cache_key(symbol, today, '30m')
        await self.cache_mgr.delete(cache_key)
        
        # Invalidate cached moving averages that include this data
        ma_keys = self._generate_ma_cache_keys(symbol, today)
        for key in ma_keys:
            await self.cache_mgr.delete(key)
    
    async def _invalidate_daily_cache(self, symbol: str, timestamp: datetime):
        """Invalidate cache after market close"""
        
        # Invalidate all cache entries for the day
        date = timestamp.strftime('%Y-%m-%d')
        pattern = f"*{symbol}*{date}*"
        
        # Get all matching keys from Redis
        matching_keys = await self._get_matching_keys(pattern)
        
        for key in matching_keys:
            await self.cache_mgr.delete(key)
    
    async def _invalidate_symbol_cache(self, symbol: str, timestamp: datetime):
        """Invalidate all cache for a symbol (e.g., due to symbol changes)"""
        
        pattern = f"*{symbol}*"
        matching_keys = await self._get_matching_keys(pattern)
        
        for key in matching_keys:
            await self.cache_mgr.delete(key)
```

---

## 10. Logging and Monitoring Specifications

### 10.1 Comprehensive Logging Architecture

```python
import logging
import structlog
from pythonjsonlogger import jsonlogger

class EODHDLoggingSystem:
    def __init__(self):
        self.logger = self._setup_structured_logging()
        self.performance_logger = self._setup_performance_logging()
        self.error_logger = self._setup_error_logging()
    
    def _setup_structured_logging(self):
        """Setup structured logging with JSON output"""
        
        # Configure structlog
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        return structlog.get_logger("eodhd")
    
    def log_api_request(self, method: str, url: str, status_code: int, 
                       response_time: float, symbol: str = None):
        """Log API request details"""
        
        self.logger.info(
            "api_request",
            method=method,
            url=url,
            status_code=status_code,
            response_time_ms=response_time * 1000,
            symbol=symbol,
            event_type="api_call"
        )
    
    def log_data_quality_issue(self, symbol: str, issue_type: str, 
                              details: Dict, severity: str = "warning"):
        """Log data quality issues"""
        
        self.logger.warning(
            "data_quality_issue",
            symbol=symbol,
            issue_type=issue_type,
            details=details,
            severity=severity,
            event_type="data_quality"
        )
    
    def log_batch_operation(self, operation: str, batch_size: int, 
                           success_count: int, error_count: int, duration: float):
        """Log batch operation results"""
        
        self.logger.info(
            "batch_operation",
            operation=operation,
            batch_size=batch_size,
            success_count=success_count,
            error_count=error_count,
            duration_seconds=duration,
            success_rate=success_count / batch_size if batch_size > 0 else 0,
            event_type="batch_processing"
        )
```

### 10.2 Performance Monitoring

```python
import time
import psutil
from dataclasses import dataclass
from typing import Dict, List
from datetime import datetime, timedelta

@dataclass
class PerformanceMetrics:
    timestamp: datetime
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    network_requests_per_second: float
    cache_hit_rate: float
    api_response_time_avg: float
    error_rate: float

class PerformanceMonitor:
    def __init__(self):
        self.metrics_buffer = []
        self.max_buffer_size = 1000
        self.alert_thresholds = {
            'cpu_usage': 80.0,
            'memory_usage': 85.0,
            'api_response_time': 5.0,  # seconds
            'error_rate': 0.05,        # 5%
            'cache_hit_rate_min': 0.70 # 70%
        }
    
    async def collect_metrics(self) -> PerformanceMetrics:
        """Collect current performance metrics"""
        
        # System metrics
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Application metrics
        api_stats = self._get_api_statistics()
        cache_stats = self._get_cache_statistics()
        
        metrics = PerformanceMetrics(
            timestamp=datetime.now(),
            cpu_usage=cpu_usage,
            memory_usage=memory.percent,
            disk_usage=disk.percent,
            network_requests_per_second=api_stats.get('requests_per_second', 0),
            cache_hit_rate=cache_stats.get('hit_rate', 0),
            api_response_time_avg=api_stats.get('avg_response_time', 0),
            error_rate=api_stats.get('error_rate', 0)
        )
        
        self.metrics_buffer.append(metrics)
        
        # Maintain buffer size
        if len(self.metrics_buffer) > self.max_buffer_size:
            self.metrics_buffer.pop(0)
        
        # Check for alerts
        self._check_performance_alerts(metrics)
        
        return metrics
    
    def _check_performance_alerts(self, metrics: PerformanceMetrics):
        """Check metrics against thresholds and generate alerts"""
        
        alerts = []
        
        if metrics.cpu_usage > self.alert_thresholds['cpu_usage']:
            alerts.append(Alert(
                level="warning",
                message=f"High CPU usage: {metrics.cpu_usage:.1f}%",
                metric="cpu_usage",
                value=metrics.cpu_usage,
                threshold=self.alert_thresholds['cpu_usage']
            ))
        
        if metrics.memory_usage > self.alert_thresholds['memory_usage']:
            alerts.append(Alert(
                level="critical",
                message=f"High memory usage: {metrics.memory_usage:.1f}%",
                metric="memory_usage",
                value=metrics.memory_usage,
                threshold=self.alert_thresholds['memory_usage']
            ))
        
        if metrics.api_response_time_avg > self.alert_thresholds['api_response_time']:
            alerts.append(Alert(
                level="warning",
                message=f"High API response time: {metrics.api_response_time_avg:.2f}s",
                metric="api_response_time",
                value=metrics.api_response_time_avg,
                threshold=self.alert_thresholds['api_response_time']
            ))
        
        # Emit alerts
        for alert in alerts:
            self._emit_alert(alert)
    
    def generate_performance_report(self, time_window: timedelta) -> Dict:
        """Generate performance report for time window"""
        
        cutoff_time = datetime.now() - time_window
        relevant_metrics = [
            m for m in self.metrics_buffer 
            if m.timestamp >= cutoff_time
        ]
        
        if not relevant_metrics:
            return {}
        
        report = {
            'time_window': str(time_window),
            'data_points': len(relevant_metrics),
            'averages': {
                'cpu_usage': sum(m.cpu_usage for m in relevant_metrics) / len(relevant_metrics),
                'memory_usage': sum(m.memory_usage for m in relevant_metrics) / len(relevant_metrics),
                'api_response_time': sum(m.api_response_time_avg for m in relevant_metrics) / len(relevant_metrics),
                'error_rate': sum(m.error_rate for m in relevant_metrics) / len(relevant_metrics),
                'cache_hit_rate': sum(m.cache_hit_rate for m in relevant_metrics) / len(relevant_metrics)
            },
            'peaks': {
                'max_cpu': max(m.cpu_usage for m in relevant_metrics),
                'max_memory': max(m.memory_usage for m in relevant_metrics),
                'max_api_response_time': max(m.api_response_time_avg for m in relevant_metrics),
                'max_error_rate': max(m.error_rate for m in relevant_metrics)
            },
            'trends': self._calculate_trends(relevant_metrics)
        }
        
        return report
```

### 10.3 Health Check and Monitoring

```python
class EODHDHealthCheck:
    def __init__(self, connection_manager: EODHDConnectionManager, 
                 cache_manager: EODHDCacheManager):
        self.conn_mgr = connection_manager
        self.cache_mgr = cache_manager
        self.checks = [
            self._check_api_connectivity,
            self._check_cache_performance,
            self._check_data_quality,
            self._check_system_resources
        ]
    
    async def run_health_check(self) -> HealthStatus:
        """Run comprehensive health check"""
        
        status = HealthStatus(timestamp=datetime.now())
        
        for check in self.checks:
            try:
                result = await check()
                status.add_check_result(result)
            except Exception as e:
                status.add_check_result(HealthCheckResult(
                    name=check.__name__,
                    status='error',
                    message=str(e),
                    timestamp=datetime.now()
                ))
        
        status.overall_status = status.determine_overall_status()
        
        return status
    
    async def _check_api_connectivity(self) -> HealthCheckResult:
        """Check API connectivity and response time"""
        
        start_time = time.time()
        
        try:
            # Test API ping
            is_healthy = await self.conn_mgr.health_check()
            
            response_time = time.time() - start_time
            
            if is_healthy:
                return HealthCheckResult(
                    name='api_connectivity',
                    status='healthy',
                    message=f'API responsive in {response_time:.2f}s',
                    timestamp=datetime.now(),
                    metadata={'response_time': response_time}
                )
            else:
                return HealthCheckResult(
                    name='api_connectivity',
                    status='unhealthy',
                    message='API not responding',
                    timestamp=datetime.now(),
                    metadata={'response_time': response_time}
                )
        except Exception as e:
            return HealthCheckResult(
                name='api_connectivity',
                status='error',
                message=f'API check failed: {str(e)}',
                timestamp=datetime.now()
            )
    
    async def _check_cache_performance(self) -> HealthCheckResult:
        """Check cache hit rates and performance"""
        
        try:
            # Test cache operations
            test_key = f"health_check_{int(time.time())}"
            test_data = b"health_check_data"
            
            # Test write
            await self.cache_mgr.set(test_key, test_data, ttl=60)
            
            # Test read
            cached_data = await self.cache_mgr.get(test_key)
            
            # Clean up
            await self.cache_mgr.delete(test_key)
            
            if cached_data == test_data:
                return HealthCheckResult(
                    name='cache_performance',
                    status='healthy',
                    message='Cache operations working correctly',
                    timestamp=datetime.now()
                )
            else:
                return HealthCheckResult(
                    name='cache_performance',
                    status='unhealthy',
                    message='Cache data corruption detected',
                    timestamp=datetime.now()
                )
        except Exception as e:
            return HealthCheckResult(
                name='cache_performance',
                status='error',
                message=f'Cache check failed: {str(e)}',
                timestamp=datetime.now()
            )
    
    async def _check_data_quality(self) -> HealthCheckResult:
        """Check recent data quality metrics"""
        
        try:
            # Check for recent anomalies or quality issues
            quality_issues = await self._get_recent_quality_issues()
            
            if len(quality_issues) == 0:
                return HealthCheckResult(
                    name='data_quality',
                    status='healthy',
                    message='No recent data quality issues',
                    timestamp=datetime.now()
                )
            elif len(quality_issues) < 5:
                return HealthCheckResult(
                    name='data_quality',
                    status='warning',
                    message=f'{len(quality_issues)} minor data quality issues',
                    timestamp=datetime.now(),
                    metadata={'issues': quality_issues}
                )
            else:
                return HealthCheckResult(
                    name='data_quality',
                    status='unhealthy',
                    message=f'{len(quality_issues)} data quality issues detected',
                    timestamp=datetime.now(),
                    metadata={'issues': quality_issues}
                )
        except Exception as e:
            return HealthCheckResult(
                name='data_quality',
                status='error',
                message=f'Data quality check failed: {str(e)}',
                timestamp=datetime.now()
            )
```

---

## API Call Examples and Implementation Details

### 11.1 Basic API Usage Examples

```python
# Example 1: Single Symbol Data Retrieval
async def example_single_symbol():
    """Example: Retrieve 30-minute intervals for a single symbol"""
    
    connection_manager = EODHDConnectionManager()
    retriever = EODHDDataRetriever(connection_manager)
    
    try:
        # Fetch data for Apple stock
        data = await retriever.fetch_30min_intervals(
            symbols=['AAPL.US'],
            start_date='2025-11-01',
            end_date='2025-11-05'
        )
        
        print(f"Retrieved {len(data['AAPL.US'])} intervals for AAPL")
        
        # Process data for Drummond calculations
        for interval in data['AAPL.US']:
            print(f"Timestamp: {interval.timestamp}, Close: {interval.close_price}")
            
    except EODHDAPIError as e:
        print(f"API Error: {e}")
    except Exception as e:
        print(f"General Error: {e}")

# Example 2: Batch Processing Multiple Symbols
async def example_batch_processing():
    """Example: Process multiple symbols in batch"""
    
    connection_manager = EODHDConnectionManager()
    batch_processor = BatchProcessor(connection_manager)
    
    # Define symbols to process
    symbols = ['AAPL.US', 'GOOGL.US', 'MSFT.US', 'TSLA.US', 'AMZN.US']
    
    try:
        # Process all symbols
        results = await batch_processor.process_symbols_batch(
            symbols=symbols,
            start_date='2025-11-01',
            end_date='2025-11-05'
        )
        
        print(f"Successfully processed {len(results)} symbols")
        
        for symbol, data in results.items():
            print(f"{symbol}: {len(data)} intervals")
            
    except Exception as e:
        print(f"Batch processing failed: {e}")

# Example 3: Real-Time Data Streaming
async def example_realtime_streaming():
    """Example: Real-time data streaming with callbacks"""
    
    connection_manager = EODHDConnectionManager()
    streamer = EODHDRealTimeStreamer(connection_manager)
    
    async def data_callback(symbol: str, interval: EnrichedInterval):
        """Callback function for real-time data"""
        print(f"Real-time update: {symbol} - Close: {interval.close_price}")
        
        # Perform Drummond calculations
        pl_dot = calculate_pl_dot([interval])
        print(f"PL Dot: {pl_dot}")
    
    try:
        # Start streaming for multiple symbols
        await streamer.start_streaming(
            symbols=['AAPL.US', 'GOOGL.US', 'MSFT.US'],
            callback=data_callback
        )
        
    except Exception as e:
        print(f"Streaming error: {e}")
```

### 12. Retry Logic and Fallback Mechanisms

```python
class RobustDataRetriever:
    def __init__(self):
        self.connection_manager = EODHDConnectionManager()
        self.cache_manager = EODHDCacheManager()
        self.retry_config = {
            'max_retries': 3,
            'base_delay': 1.0,
            'max_delay': 60.0,
            'backoff_multiplier': 2.0
        }
    
    async def fetch_with_fallback(self, symbol: str, date: str) -> Optional[EnrichedInterval]:
        """Fetch data with comprehensive retry and fallback logic"""
        
        strategies = [
            self._try_primary_api,
            self._try_cached_data,
            self._try_alternative_endpoint,
            self._try_delayed_retry
        ]
        
        for strategy in strategies:
            try:
                result = await strategy(symbol, date)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"Strategy {strategy.__name__} failed: {e}")
                continue
        
        logger.error(f"All strategies failed for {symbol} on {date}")
        return None
    
    async def _try_primary_api(self, symbol: str, date: str) -> Optional[EnrichedInterval]:
        """Primary API call with retry logic"""
        
        for attempt in range(self.retry_config['max_retries']):
            try:
                return await self._make_api_request(symbol, date)
                
            except EODHDRateLimitError:
                if attempt < self.retry_config['max_retries'] - 1:
                    delay = min(
                        self.retry_config['base_delay'] * (self.retry_config['backoff_multiplier'] ** attempt),
                        self.retry_config['max_delay']
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
            
            except EODHDAPIError as e:
                if e.status_code >= 500 and attempt < self.retry_config['max_retries'] - 1:
                    delay = self.retry_config['base_delay'] * (2 ** attempt)
                    await asyncio.sleep(delay)
                else:
                    raise
        
        return None
    
    async def _try_cached_data(self, symbol: str, date: str) -> Optional[EnrichedInterval]:
        """Try to get data from cache"""
        
        cache_key = f"fallback_{symbol}_{date}"
        cached_data = await self.cache_manager.get(cache_key)
        
        if cached_data:
            return pickle.loads(cached_data)
        
        return None
    
    async def _try_alternative_endpoint(self, symbol: str, date: str) -> Optional[EnrichedInterval]:
        """Try alternative API endpoint"""
        
        try:
            # Try historical data endpoint instead of intraday
            url = f"{self.base_url}/eod/{symbol}"
            params = {
                'api_token': self.connection_manager.token,
                'fmt': 'json',
                'date': date
            }
            
            response = await self.connection_manager.session.get(url, params=params)
            
            if response.status == 200:
                data = await response.json()
                return self._transform_record(data)
            
        except Exception as e:
            logger.warning(f"Alternative endpoint failed: {e}")
        
        return None
    
    async def _try_delayed_retry(self, symbol: str, date: str) -> Optional[EnrichedInterval]:
        """Final retry with extended delay"""
        
        logger.info(f"Attempting delayed retry for {symbol} on {date}")
        await asyncio.sleep(30)  # Wait 30 seconds
        
        try:
            return await self._make_api_request(symbol, date)
        except Exception as e:
            logger.error(f"Delayed retry failed: {e}")
            return None
```

---

## Configuration and Deployment

### 13. Environment Configuration

```yaml
# config/eodhd_config.yaml
eodhd:
  api:
    base_url: "https://eodhd.com/api"
    token_env_var: "EODHD_API_TOKEN"
    timeout: 30
    max_retries: 3
    rate_limit:
      requests_per_minute: 80
      burst_limit: 10
      daily_limit: 50000
  
  cache:
    redis:
      host: "localhost"
      port: 6379
      db: 0
      password: null
    tiers:
      l1_memory:
        max_size: 1000
        ttl: 300
      l2_redis:
        max_size: 10000
        ttl: 3600
  
  monitoring:
    log_level: "INFO"
    performance_monitoring: true
    health_check_interval: 60  # seconds
    alert_thresholds:
      cpu_usage: 80
      memory_usage: 85
      api_response_time: 5
      error_rate: 0.05
  
  batch_processing:
    batch_size: 50
    concurrency_limit: 10
    backfill_chunk_size: 100
    max_date_range: 365
  
  data_quality:
    volume_threshold: 1000
    price_tolerance: 0.001
    missing_data_threshold: 0.05
    anomaly_thresholds:
      price_change_rate: 0.10
      volume_spike: 5.0
      volatility_z_score: 3.0
```

### 14. Deployment Considerations

**Docker Configuration:**
```dockerfile
# Dockerfile for EODHD Integration Service
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -m eodhd.health_check

EXPOSE 8000

CMD ["python", "-m", "eodhd.main"]
```

**Kubernetes Deployment:**
```yaml
# k8s/eodhd-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eodhd-integration
spec:
  replicas: 3
  selector:
    matchLabels:
      app: eodhd-integration
  template:
    metadata:
      labels:
        app: eodhd-integration
    spec:
      containers:
      - name: eodhd-integration
        image: eodhd-integration:latest
        ports:
        - containerPort: 8000
        env:
        - name: EODHD_API_TOKEN
          valueFrom:
            secretKeyRef:
              name: eodhd-secrets
              key: api-token
        - name: REDIS_HOST
          value: "redis-service"
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 60
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
```

---

## Conclusion

This comprehensive EODHD.com API integration architecture provides a robust, scalable, and fault-tolerant foundation for the Drummond Geometry Analysis System. The design ensures:

1. **High Availability:** Multi-tier caching, retry mechanisms, and fallback strategies
2. **Data Quality:** Comprehensive validation, anomaly detection, and quality monitoring
3. **Performance:** Optimized batch processing, smart caching, and resource management
4. **Monitoring:** Detailed logging, performance metrics, and health checks
5. **Scalability:** Horizontal scaling support and efficient resource utilization

The architecture supports all requirements for Drummond Geometry calculations including PL Dot analysis, multiple timeframe coordination, and real-time market data processing while maintaining the high standards required for professional trading analysis.

**Key Benefits:**
- Robust handling of API limitations and errors
- Intelligent caching strategies for optimal performance
- Comprehensive data quality assurance
- Real-time monitoring and alerting
- Scalable architecture for growth

**Next Steps:**
1. Implement the core connection manager and data retriever components
2. Set up monitoring and alerting infrastructure
3. Configure caching layers and performance optimization
4. Deploy to staging environment for testing
5. Conduct load testing and performance optimization
6. Deploy to production with full monitoring

This architecture provides the foundation for reliable, high-quality market data integration essential for the Drummond Geometry Analysis System's sophisticated trading calculations.
