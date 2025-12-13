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
            # Format: YYYY-MM-DD
            date_str = date.strftime('%Y-%m-%d')
            endpoint = f"{self.base_url}/prices/{date_str}"
            
            response = requests.get(endpoint, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            # Parse the response into structured format
            prices = []
            for hour in range(24):
                hour_key = f"{hour:02d}:00"
                if hour_key in data:
                    prices.append({
                        'hour': hour,
                        'price': float(data[hour_key]),
                        'timestamp': datetime.combine(date, datetime.min.time()).replace(hour=hour)
                    })
            
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
        best_window = None
        best_avg_price = float('inf')
        
        for i in range(len(prices) - hours_needed + 1):
            window = prices[i:i + hours_needed]
            avg_price = sum(p['price'] for p in window) / len(window)
            
            if avg_price < best_avg_price:
                best_avg_price = avg_price
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
    
    def get_price_forecast_tomorrow(self):
        """Fetch electricity prices for tomorrow.
        
        Returns:
            list: List of dictionaries containing hourly prices for tomorrow
        """
        tomorrow = datetime.now() + timedelta(days=1)
        return self.get_electricity_prices(tomorrow)
