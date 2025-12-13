"""Configuration loader for battery forecast application."""
import yaml
import os


class Config:
    """Configuration class for battery forecast."""
    
    def __init__(self, config_path='config.yaml'):
        """Initialize configuration from YAML file.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self):
        """Load configuration from YAML file.
        
        Returns:
            dict: Configuration dictionary
        
        Raises:
            FileNotFoundError: If config file doesn't exist
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Please create config.yaml based on config.yaml.example"
            )
        
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)
    
    @property
    def ha_url(self):
        """Get Home Assistant URL."""
        return self.config['home_assistant']['url']
    
    @property
    def ha_token(self):
        """Get Home Assistant access token."""
        return self.config['home_assistant']['token']
    
    @property
    def sensor_name(self):
        """Get sensor entity ID."""
        return self.config['sensor']['name']
    
    @property
    def history_minutes(self):
        """Get number of minutes of historical data to fetch."""
        return self.config['time']['history_minutes']
    
    @property
    def threshold_percent(self):
        """Get SOC threshold percentage for forecast alert."""
        return self.config['forecast']['threshold_percent']
