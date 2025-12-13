"""pstryk.pl API client for fetching electricity prices."""
import requests
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Default timeout for API requests (seconds)
DEFAULT_TIMEOUT = 30


class PstrykApiClient:
    """Client for interacting with pstryk.pl API."""
    
    def __init__(self, timeout=None):
        """Initialize pstryk.pl API client.
        
        Args:
            timeout: Request timeout in seconds (default: 30)
        """
        self.base_url = "https://api.pstryk.pl"
        self.timeout = timeout or DEFAULT_TIMEOUT
    
    def get_electricity_prices(self, date=None):
        """Fetch electricity prices for a specific date.
        
        Args:
            date: Date to fetch prices for (datetime object). Defaults to today.
        
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
        if date is None:
            date = datetime.now().date()
        elif isinstance(date, datetime):
            date = date.date()
        
        try:
            # pstryk.pl API endpoint for electricity prices
            # Using integrations API as documented at https://api.pstryk.pl/integrations/swagger/
            # Format: YYYY-MM-DD
            date_str = date.strftime('%Y-%m-%d')
            endpoint = f"{self.base_url}/integrations/api/prices/{date_str}"
            
            response = requests.get(endpoint, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            # Parse the response into structured format
            # The API may return different formats:
            # 1. {"00:00": 0.50, "01:00": 0.48, ...} - dict with hour keys
            # 2. [{"hour": 0, "price": 0.50}, ...] - list of objects
            # 3. {"prices": [{"hour": 0, "price": 0.50}, ...]} - nested list
            # 4. {"prices": {"00:00": 0.50, ...}} - nested dict
            prices = []
            
            # Handle different response formats
            if isinstance(data, dict):
                # Check if data has a 'prices' key with nested data
                if 'prices' in data:
                    price_data = data['prices']
                    if isinstance(price_data, list):
                        # Format: {"prices": [{"hour": 0, "price": 0.50}, ...]}
                        prices = self._parse_price_list(price_data, date)
                    elif isinstance(price_data, dict):
                        # Format: {"prices": {"00:00": 0.50, ...}}
                        prices = self._parse_hour_dict(price_data, date)
                else:
                    # Format: {"00:00": 0.50, "01:00": 0.48, ...}
                    prices = self._parse_hour_dict(data, date)
            elif isinstance(data, list):
                # Format: [{"hour": 0, "price": 0.50}, ...]
                prices = self._parse_price_list(data, date)
            
            if not prices:
                logger.warning(f"No price data found in response for {date_str}")
                logger.debug(f"Response data: {data}")
            
            logger.info(f"Fetched {len(prices)} hourly prices for {date_str}")
            return prices
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch electricity prices from pstryk.pl: {e}")
            raise Exception(f"Failed to fetch electricity prices: {e}")
    
    def get_cheapest_hours(self, hours_needed=4, date=None):
        """Find the cheapest consecutive hours to charge.
        
        Args:
            hours_needed: Number of consecutive hours needed for charging
            date: Date to analyze (datetime object). Defaults to today.
        
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
    
    def get_cheapest_hours_multiple_periods(self, total_hours_needed, date=None):
        """Find cheapest hours for charging, allowing multiple non-consecutive periods.
        
        Args:
            total_hours_needed: Total number of hours needed for charging
            date: Date to analyze (datetime object). Defaults to today.
        
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
        for hour in range(24):
            hour_key = f"{hour:02d}:00"
            if hour_key in price_data:
                prices.append({
                    'hour': hour,
                    'price': float(price_data[hour_key]),
                    'timestamp': datetime.combine(date, datetime.min.time()).replace(hour=hour)
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
        for item in price_data:
            if isinstance(item, dict) and 'hour' in item and 'price' in item:
                hour = int(item['hour'])
                prices.append({
                    'hour': hour,
                    'price': float(item['price']),
                    'timestamp': datetime.combine(date, datetime.min.time()).replace(hour=hour)
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
