"""Home Assistant API client for fetching sensor data."""
import requests
from datetime import datetime, timedelta
from dateutil import parser as date_parser


class HomeAssistantClient:
    """Client for interacting with Home Assistant API."""
    
    def __init__(self, url, token):
        """Initialize Home Assistant client.
        
        Args:
            url: Home Assistant URL
            token: Long-lived access token
        """
        self.url = url.rstrip('/')
        self.token = token
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }
    
    def get_sensor_history(self, entity_id, minutes):
        """Fetch historical data for a sensor.
        
        Args:
            entity_id: Sensor entity ID (e.g., 'sensor.batteries_stan_pojemnosci')
            minutes: Number of minutes of history to fetch
        
        Returns:
            list: List of tuples (timestamp, value) sorted by time
        
        Raises:
            requests.RequestException: If API request fails
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=minutes)
        
        # Format timestamp for Home Assistant API (ISO 8601)
        timestamp = start_time.isoformat()
        
        # Build API endpoint
        endpoint = f"{self.url}/api/history/period/{timestamp}"
        params = {
            'filter_entity_id': entity_id,
            'minimal_response': 'true',
            'no_attributes': 'true'
        }
        
        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if not data or not data[0]:
                return []
            
            # Extract state changes
            history_data = []
            for state in data[0]:
                try:
                    # Parse timestamp
                    timestamp = date_parser.parse(state['last_updated'])
                    
                    # Parse state value
                    state_value = state['state']
                    
                    # Skip non-numeric states
                    if state_value in ['unknown', 'unavailable', 'None', None]:
                        continue
                    
                    value = float(state_value)
                    history_data.append((timestamp, value))
                except (ValueError, KeyError) as e:
                    # Skip invalid entries
                    continue
            
            # Sort by timestamp
            history_data.sort(key=lambda x: x[0])
            
            return history_data
            
        except requests.RequestException as e:
            raise Exception(f"Failed to fetch sensor history: {e}")
    
    def get_current_state(self, entity_id):
        """Get current state of a sensor.
        
        Args:
            entity_id: Sensor entity ID
        
        Returns:
            float: Current sensor value
        
        Raises:
            requests.RequestException: If API request fails
        """
        endpoint = f"{self.url}/api/states/{entity_id}"
        
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            state_value = data['state']
            
            if state_value in ['unknown', 'unavailable', 'None', None]:
                raise ValueError(f"Sensor {entity_id} has invalid state: {state_value}")
            
            return float(state_value)
            
        except requests.RequestException as e:
            raise Exception(f"Failed to fetch current state: {e}")
