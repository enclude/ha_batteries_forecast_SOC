"""pstryk.pl API client for fetching electricity prices."""
import requests
import logging
import os
import json
import tempfile
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)

# Default timeout for API requests (seconds)
DEFAULT_TIMEOUT = 30

# Cache configuration (matches ha_pstryk.sh approach)
CACHE_DIR = tempfile.gettempdir()
CACHE_FILE = os.path.join(CACHE_DIR, 'pstryk_cache.json')
CACHE_TIMESTAMP_FILE = os.path.join(CACHE_DIR, 'pstryk_cache_timestamps.json')
CACHE_MAX_AGE_MINUTES = 55  # Cache expires after 55 minutes (3 API calls/hour limit)


class PstrykApiClient:
    """Client for interacting with pstryk.pl API."""
    
    def __init__(self, api_key=None, timeout=None, base_url=None):
        """Initialize pstryk.pl API client.
        
        Args:
            api_key: API key for authentication (optional)
            timeout: Request timeout in seconds (default: 30)
            base_url: Base URL for API (default: https://api.pstryk.pl)
        """
        self.api_key = api_key
        self.base_url = base_url or "https://api.pstryk.pl"
        self.timeout = timeout or DEFAULT_TIMEOUT
        self._ensure_cache_files()
    
    def _ensure_cache_files(self):
        """Ensure cache files exist."""
        for cache_file in [CACHE_FILE, CACHE_TIMESTAMP_FILE]:
            if not os.path.exists(cache_file):
                try:
                    with open(cache_file, 'w') as f:
                        json.dump({}, f)
                except Exception as e:
                    logger.warning(f"Could not create cache file {cache_file}: {e}")
    
    def _get_cache_key(self, date):
        """Generate cache key for a given date (day-based since we fetch 24h+ of data).
        
        Uses date only (not hour) because we fetch from yesterday 22:00 to today 23:59
        to cover the full Warsaw local day including tomorrow's hour 0 (23:00 UTC today).
        """
        if isinstance(date, datetime):
            cache_date = date
        else:
            cache_date = datetime.combine(date, datetime.min.time())
        # Use date-only key since we're fetching a full day's data (yesterday 22:00 to today 23:59)
        return cache_date.strftime('%Y-%m-%d')
    
    def _is_cache_fresh(self, cache_key):
        """Check if cache is less than 55 minutes old."""
        try:
            if not os.path.exists(CACHE_TIMESTAMP_FILE):
                return False
            
            with open(CACHE_TIMESTAMP_FILE, 'r') as f:
                timestamps = json.load(f)
            
            if cache_key not in timestamps:
                logger.debug(f"No cache timestamp found for {cache_key}")
                return False
            
            cache_timestamp = timestamps[cache_key]
            current_timestamp = datetime.now().timestamp()
            cache_age_minutes = (current_timestamp - cache_timestamp) / 60
            
            logger.debug(f"Cache age for {cache_key}: {cache_age_minutes:.1f} minutes")
            
            if cache_age_minutes < CACHE_MAX_AGE_MINUTES:
                logger.info(f"Cache is fresh (< {CACHE_MAX_AGE_MINUTES} minutes)")
                return True
            else:
                logger.info(f"Cache is stale (>= {CACHE_MAX_AGE_MINUTES} minutes)")
                return False
        except Exception as e:
            logger.warning(f"Error checking cache freshness: {e}")
            return False
    
    def _get_from_cache(self, cache_key):
        """Get data from cache if available."""
        try:
            if not os.path.exists(CACHE_FILE):
                return None
            
            with open(CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
            
            if cache_key in cache_data:
                # Convert ISO strings back to datetime objects
                data = cache_data[cache_key]
                for item in data:
                    if 'timestamp' in item and isinstance(item['timestamp'], str):
                        # Parse as timezone-naive datetime for consistency
                        item['timestamp'] = datetime.fromisoformat(item['timestamp'].replace('+00:00', ''))
                
                logger.info(f"Using cached PSTRYK data (cache key: {cache_key}, {len(data)} prices)")
                return data
            
            logger.debug(f"No cached data found for {cache_key}")
            return None
        except Exception as e:
            logger.warning(f"Error reading from cache: {e}")
            return None
    
    def _save_to_cache(self, cache_key, data):
        """Save data to cache with timestamp."""
        try:
            # Convert datetime objects to ISO strings for JSON serialization
            serializable_data = []
            for item in data:
                serializable_item = item.copy()
                if 'timestamp' in serializable_item and isinstance(serializable_item['timestamp'], datetime):
                    serializable_item['timestamp'] = serializable_item['timestamp'].isoformat()
                serializable_data.append(serializable_item)
            
            # Save data
            cache_data = {}
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r') as f:
                    try:
                        cache_data = json.load(f)
                    except:
                        cache_data = {}
            
            cache_data[cache_key] = serializable_data
            
            with open(CACHE_FILE, 'w') as f:
                json.dump(cache_data, f)
            
            # Save timestamp
            timestamps = {}
            if os.path.exists(CACHE_TIMESTAMP_FILE):
                with open(CACHE_TIMESTAMP_FILE, 'r') as f:
                    try:
                        timestamps = json.load(f)
                    except:
                        timestamps = {}
            
            timestamps[cache_key] = datetime.now().timestamp()
            
            with open(CACHE_TIMESTAMP_FILE, 'w') as f:
                json.dump(timestamps, f)
            
            logger.info(f"Cached data and timestamp for {cache_key}")
        except Exception as e:
            logger.warning(f"Error saving to cache: {e}")
    
    def get_electricity_prices(self, date=None):
        """Fetch electricity prices for a specific date.
        
        After 14:00 Warsaw time, automatically fetches tomorrow's prices for better
        charging recommendations (pstryk.pl publishes next day prices at 14:00).
        
        Args:
            date: Date to fetch prices for (datetime object). Defaults to today,
                  or tomorrow if after 14:00 Warsaw time.
        
        Returns:
            list: List of dictionaries containing hourly prices with structure:
                [
                    {
                        'hour': 0-23,
                        'price': float (PLN/kWh),
                        'timestamp': datetime
                    },
                    ...
                ]
        
        Raises:
            Exception: If API request fails
        """
        warsaw_tz = pytz.timezone('Europe/Warsaw')
        
        if date is None:
            # Check current time in Warsaw timezone
            now_warsaw = datetime.now(warsaw_tz)
            
            # If it's after 14:00 Warsaw time, fetch tomorrow's prices
            if now_warsaw.hour >= 14:
                date = (now_warsaw + timedelta(days=1)).date()
                logger.info(f"After 14:00 Warsaw time ({now_warsaw.strftime('%H:%M')}), fetching tomorrow's prices: {date}")
            else:
                date = now_warsaw.date()
                logger.info(f"Before 14:00 Warsaw time ({now_warsaw.strftime('%H:%M')}), fetching today's prices: {date}")
        elif isinstance(date, datetime):
            date = date.date()
        
        # Generate cache key
        cache_key = self._get_cache_key(date)
        
        # Check if we have fresh cache first
        if self._is_cache_fresh(cache_key):
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                logger.info(f"Using cached PSTRYK data (cache key: {cache_key}, {len(cached_data)} prices)")
                return cached_data
            logger.info("Fresh cache found but data invalid, falling back to PSTRYK API")
        
        try:
            # pstryk.pl API endpoint for electricity prices
            # Using integrations API as documented at https://api.pstryk.pl/integrations/swagger/
            # This matches the working ha_pstryk.sh implementation
            
            # Calculate time window for the day (need 24 hours of data)
            # Request data from yesterday 22:00 UTC to cover Warsaw 00:00 in both CET and CEST
            # CET (winter): Warsaw 00:00 = yesterday 23:00 UTC
            # CEST (summer): Warsaw 00:00 = yesterday 22:00 UTC
            # This ensures we have data for Warsaw local day (00:00-23:59)
            
            # Convert date to datetime if needed
            if isinstance(date, datetime):
                target_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                target_date = datetime.combine(date, datetime.min.time())
            
            # Start from yesterday 22:00 UTC (covers both CET and CEST)
            yesterday = target_date - timedelta(days=1)
            start_time = yesterday.replace(hour=22, minute=0, second=0, microsecond=0)
            
            # End at today 23:59 UTC
            end_time = target_date.replace(hour=23, minute=59, second=59, microsecond=0)
            
            # Format timestamps for API (ISO 8601 with timezone)
            window_start = start_time.strftime('%Y-%m-%dT%H:%M:%S+00:00')
            window_end = end_time.strftime('%Y-%m-%dT%H:%M:%S+00:00')
            
            # API endpoint (matches ha_pstryk.sh)
            endpoint = f"{self.base_url}/integrations/pricing/"
            
            # Prepare headers with API key (note: NOT using "Bearer" prefix per ha_pstryk.sh)
            headers = {
                'accept': 'application/json'
            }
            if self.api_key:
                headers['Authorization'] = self.api_key
            else:
                raise Exception(
                    "API key is required for pstryk.pl API. "
                    "Please add your API key to config.yaml:\n"
                    "pstryk:\n"
                    "  api_key: \"YOUR_API_KEY\"\n"
                    "Visit https://api.pstryk.pl/ for more information."
                )
            
            # Query parameters (matches ha_pstryk.sh)
            params = {
                'resolution': 'hour',
                'window_start': window_start,
                'window_end': window_end
            }
            
            logger.info(f"Fetching prices from PSTRYK API: {endpoint}")
            logger.info(f"API request parameters: resolution=hour, window_start={window_start} (UTC), window_end={window_end} (UTC)")
            logger.info(f"Requesting prices for date: {date} (automatically selected based on Warsaw time)")
            
            response = requests.get(endpoint, headers=headers, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            logger.info(f"Successfully fetched data from PSTRYK API")
            data = response.json()
            
            # Parse the response from pstryk.pl API
            # The API returns: {"frames": [{"start": "2025-12-14T00:00:00+00:00", "price_gross": 0.50, ...}, ...]}
            prices = []
            
            if 'frames' in data and isinstance(data['frames'], list):
                # Parse frames format (actual pstryk.pl API format)
                for frame in data['frames']:
                    try:
                        # Extract hour from ISO 8601 timestamp
                        timestamp_str = frame.get('start', '')
                        # Parse timestamp and make it timezone-naive for consistency
                        # Remove all timezone indicators (+00:00, +01:00, Z, etc.)
                        clean_timestamp = timestamp_str.replace('+00:00', '').replace('Z', '')
                        if '+' in clean_timestamp:
                            clean_timestamp = clean_timestamp.split('+')[0]
                        if 'T' in clean_timestamp and len(clean_timestamp.split('T')) == 2:
                            timestamp = datetime.fromisoformat(clean_timestamp)
                        else:
                            continue
                        hour = timestamp.hour
                        
                        # Get price (use price_gross as it includes VAT)
                        price = float(frame.get('price_gross', 0))
                        
                        prices.append({
                            'hour': hour,
                            'price': price,
                            'timestamp': timestamp
                        })
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to parse frame: {frame}, error: {e}")
                        continue
                
                logger.info(f"Parsed {len(prices)} hourly prices from PSTRYK API frames format")
                if prices:
                    first_hour = min(p['hour'] for p in prices)
                    last_hour = max(p['hour'] for p in prices)
                    logger.info(f"Price data range: {first_hour:02d}:00 - {last_hour:02d}:00 UTC")
                    
                    # Check for zero prices (data not available)
                    zero_prices = [p for p in prices if p['price'] == 0.0]
                    if zero_prices:
                        zero_hours = [f"{p['hour']:02d}:00" for p in zero_prices]
                        logger.warning(f"Warning: {len(zero_prices)} hour(s) have 0.0000 PLN/kWh price: {', '.join(zero_hours)}")
                        logger.warning(f"Price data incomplete for requested date: {date}")
                        # Filter out zero prices to avoid incorrect recommendations
                        prices = [p for p in prices if p['price'] > 0.0]
                        logger.info(f"Filtered to {len(prices)} non-zero prices")
            else:
                # Fallback to old parsing logic for backwards compatibility
                if isinstance(data, dict):
                    if 'prices' in data:
                        price_data = data['prices']
                        if isinstance(price_data, list):
                            prices = self._parse_price_list(price_data, date)
                        elif isinstance(price_data, dict):
                            prices = self._parse_hour_dict(price_data, date)
                    else:
                        prices = self._parse_hour_dict(data, date)
                elif isinstance(data, list):
                    prices = self._parse_price_list(data, date)
                
                if prices:
                    logger.info(f"Fetched {len(prices)} hourly prices using legacy format")
            
            if not prices:
                logger.warning(f"No price data found in response")
                logger.debug(f"Response data structure: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            else:
                # Save successful response to cache
                self._save_to_cache(cache_key, prices)
            
            return prices
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch electricity prices from pstryk.pl: {e}")
            
            # Check for rate limiting (429) and try to use stale cache
            if '429' in str(e) or 'Too Many Requests' in str(e):
                logger.warning("Rate limit detected (429), attempting to use stale cache")
                cached_data = self._get_from_cache(cache_key)
                if cached_data:
                    logger.info("Using stale cached data due to rate limiting")
                    return cached_data
                else:
                    logger.error("No cached data available for fallback")
            
            raise Exception(f"Failed to fetch electricity prices: {e}")
    
    def get_cheapest_hours(self, hours_needed=4, date=None, use_cached_prices=None):
        """Find the cheapest consecutive hours to charge.
        
        Args:
            hours_needed: Number of consecutive hours needed for charging
            date: Date to analyze (datetime object). Defaults to today.
            use_cached_prices: Pre-fetched price data to avoid API calls
        
        Returns:
            dict: Information about cheapest charging window:
                {
                    'start_hour': int (0-23),
                    'end_hour': int (0-23),
                    'hours': int,
                    'avg_price': float,
                    'total_cost_per_kwh': float,
                    'timestamps': list of datetime objects
                }
        
        Raises:
            Exception: If API request fails or insufficient data
        """
        if use_cached_prices is not None:
            prices = use_cached_prices
        else:
            prices = self.get_electricity_prices(date)
        
        if len(prices) < hours_needed:
            raise Exception(f"Insufficient price data: need {hours_needed} hours, got {len(prices)}")
        
        # Find the cheapest consecutive window
        # Note: prices list contains consecutive hours (0-23), so window slicing
        # automatically gives us consecutive hours
        best_window = None
        best_avg_price = float('inf')
        
        for i in range(len(prices) - hours_needed + 1):
            window = prices[i:i + hours_needed]
            avg_price = sum(p['price'] for p in window) / len(window)
            
            if avg_price < best_avg_price:
                best_avg_price = avg_price
                # end_hour is the last hour in the window (e.g., for 4h starting at 2: 2,3,4,5)
                best_window = {
                    'start_hour': window[0]['hour'],
                    'end_hour': window[-1]['hour'],
                    'hours': hours_needed,
                    'avg_price': avg_price,
                    'total_cost_per_kwh': sum(p['price'] for p in window),
                    'timestamps': [p['timestamp'] for p in window]
                }
        
        logger.info(f"Found cheapest {hours_needed}h window: {best_window['start_hour']}:00 - {best_window['end_hour']}:00")
        return best_window
    
    def get_cheapest_hours_multiple_periods(self, total_hours_needed, date=None, use_cached_prices=None):
        """Find cheapest hours for charging, allowing multiple non-consecutive periods.
        
        Args:
            total_hours_needed: Total number of hours needed for charging
            date: Date to analyze (datetime object). Defaults to today.
            use_cached_prices: Pre-fetched price data to avoid API calls
        
        Returns:
            list: List of charging periods, each containing:
                {
                    'start_hour': int (0-23),
                    'end_hour': int (0-23),
                    'hours': int,
                    'avg_price': float,
                    'total_cost_per_kwh': float,
                    'timestamps': list of datetime objects
                }
                Sorted by start_hour.
        
        Raises:
            Exception: If API request fails or insufficient data
        """
        if use_cached_prices is not None:
            prices = use_cached_prices
        else:
            prices = self.get_electricity_prices(date)
        
        if len(prices) < total_hours_needed:
            raise Exception(f"Insufficient price data: need {total_hours_needed} hours, got {len(prices)}")
        
        # Sort prices by cost to find the cheapest hours
        sorted_prices = sorted(prices, key=lambda p: p['price'])
        
        # Select the cheapest N hours
        cheapest_hours = sorted(sorted_prices[:total_hours_needed], key=lambda p: p['hour'])
        
        # Group consecutive hours into periods
        periods = []
        if not cheapest_hours:
            return periods
        
        current_period = [cheapest_hours[0]]
        
        for i in range(1, len(cheapest_hours)):
            if cheapest_hours[i]['hour'] == current_period[-1]['hour'] + 1:
                # Consecutive hour, add to current period
                current_period.append(cheapest_hours[i])
            else:
                # Non-consecutive, start a new period
                periods.append(self._create_period_info(current_period))
                current_period = [cheapest_hours[i]]
        
        # Add the last period
        periods.append(self._create_period_info(current_period))
        
        logger.info(f"Found {len(periods)} charging period(s) totaling {total_hours_needed} hours")
        for period in periods:
            logger.info(f"  Period: {period['start_hour']:02d}:00 - {period['end_hour']:02d}:00 ({period['hours']}h at avg {period['avg_price']:.4f} PLN/kWh)")
        
        return periods
    
    def _parse_hour_dict(self, price_data, date):
        """Parse price data in hour:price dictionary format.
        
        Args:
            price_data: Dictionary with hour keys like {"00:00": 0.50, ...}
            date: Date for timestamp creation
        
        Returns:
            list: Parsed price entries
        """
        prices = []
        # Ensure date is timezone-naive
        if isinstance(date, datetime):
            parse_date = date.replace(tzinfo=None) if date.tzinfo else date
        else:
            parse_date = date
        
        for hour in range(24):
            hour_key = f"{hour:02d}:00"
            if hour_key in price_data:
                prices.append({
                    'hour': hour,
                    'price': float(price_data[hour_key]),
                    'timestamp': datetime(parse_date.year, parse_date.month, parse_date.day, hour)
                })
        return prices
    
    def _parse_price_list(self, price_data, date):
        """Parse price data in list of objects format.
        
        Args:
            price_data: List of dicts like [{"hour": 0, "price": 0.50}, ...]
            date: Date for timestamp creation
        
        Returns:
            list: Parsed price entries
        """
        prices = []
        # Ensure date is timezone-naive
        if isinstance(date, datetime):
            parse_date = date.replace(tzinfo=None) if date.tzinfo else date
        else:
            parse_date = date
        
        for item in price_data:
            if isinstance(item, dict) and 'hour' in item and 'price' in item:
                hour = int(item['hour'])
                prices.append({
                    'hour': hour,
                    'price': float(item['price']),
                    'timestamp': datetime(parse_date.year, parse_date.month, parse_date.day, hour)
                })
        return prices
    
    def _create_period_info(self, hours):
        """Create period information dictionary from a list of hours.
        
        Args:
            hours: List of price dictionaries for consecutive hours
        
        Returns:
            dict: Period information
        """
        return {
            'start_hour': hours[0]['hour'],
            'end_hour': hours[-1]['hour'],
            'hours': len(hours),
            'avg_price': sum(h['price'] for h in hours) / len(hours),
            'total_cost_per_kwh': sum(h['price'] for h in hours),
            'timestamps': [h['timestamp'] for h in hours]
        }
    
    def get_price_forecast_tomorrow(self):
        """Fetch electricity prices for tomorrow.
        
        Returns:
            list: List of dictionaries containing hourly prices for tomorrow
        """
        tomorrow = datetime.now() + timedelta(days=1)
        return self.get_electricity_prices(tomorrow)
