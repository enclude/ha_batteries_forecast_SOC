"""Home Assistant API client for fetching sensor data."""
import requests
import logging
from datetime import datetime, timedelta
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


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
    
    def get_sensor_history(self, entity_id, minutes, include_current_state=True):
        """Fetch historical data for a sensor.
        
        Args:
            entity_id: Sensor entity ID (e.g., 'sensor.batteries_stan_pojemnosci')
            minutes: Number of minutes of history to fetch
            include_current_state: If True and history is insufficient, add current state
        
        Returns:
            list: List of tuples (timestamp, value) sorted by time
        
        Raises:
            requests.RequestException: If API request fails
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=minutes)
        
        # Format timestamp for Home Assistant API (ISO 8601)
        start_timestamp = start_time.isoformat()
        end_timestamp = end_time.isoformat()
        
        # Build API endpoint
        endpoint = f"{self.url}/api/history/period/{start_timestamp}"
        params = {
            'filter_entity_id': entity_id,
            'end_time': end_timestamp,
            'no_attributes': 'true'
        }
        
        try:
            logger.debug(f"Fetching history from {start_timestamp} to {end_timestamp} for {entity_id}")
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"API returned {len(data)} entity groups")
            
            if not data or not data[0]:
                logger.warning(f"No history data returned for {entity_id}")
                history_data = []
            else:
                logger.debug(f"Entity group contains {len(data[0])} state records")
                
                # Extract state changes
                history_data = []
                skipped_count = 0
                for state in data[0]:
                    try:
                        # Parse timestamp
                        timestamp = date_parser.parse(state['last_updated'])
                        
                        # Parse state value
                        state_value = state['state']
                        
                        # Skip non-numeric states
                        if state_value in ['unknown', 'unavailable', 'None', None]:
                            skipped_count += 1
                            logger.debug(f"Skipped non-numeric state: {state_value}")
                            continue
                        
                        value = float(state_value)
                        history_data.append((timestamp, value))
                    except (ValueError, KeyError) as e:
                        # Skip invalid entries
                        skipped_count += 1
                        logger.debug(f"Skipped invalid entry: {e}")
                        continue
                
                if skipped_count > 0:
                    logger.info(f"Skipped {skipped_count} invalid/non-numeric entries")
            
            # If we don't have enough historical data, try to get the current state
            if include_current_state and len(history_data) < 3:
                logger.info(f"Only {len(history_data)} historical points found, fetching current state")
                try:
                    current_value = self.get_current_state(entity_id)
                    current_time = datetime.now()
                    
                    # Check if current state is not already in history
                    if not history_data or (current_time - history_data[-1][0]).total_seconds() > 1:
                        history_data.append((current_time, current_value))
                        logger.info(f"Added current state: {current_value}% at {current_time}")
                except Exception as e:
                    logger.warning(f"Could not fetch current state: {e}")
            
            logger.info(f"Successfully parsed {len(history_data)} valid data points")
            
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
