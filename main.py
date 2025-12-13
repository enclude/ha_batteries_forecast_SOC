#!/usr/bin/env python3
"""Main script for battery SOC forecasting."""
import sys
import argparse
from config_loader import Config
from ha_api_client import HomeAssistantClient
from forecast import BatteryForecast


def main():
    """Main function to run battery forecast."""
    parser = argparse.ArgumentParser(
        description='Forecast battery State of Charge (SOC) using Home Assistant data'
    )
    parser.add_argument(
        '-c', '--config',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        if args.verbose:
            print(f"Loading configuration from: {args.config}")
        
        config = Config(args.config)
        
        if args.verbose:
            print(f"Sensor: {config.sensor_name}")
            print(f"History window: {config.history_minutes} minutes")
            print(f"Threshold: {config.threshold_percent}%")
            print(f"Home Assistant URL: {config.ha_url}")
        
        # Initialize Home Assistant client
        if args.verbose:
            print("\nConnecting to Home Assistant...")
        
        ha_client = HomeAssistantClient(config.ha_url, config.ha_token)
        
        # Fetch sensor history
        if args.verbose:
            print(f"Fetching history for {config.sensor_name}...")
        
        history_data = ha_client.get_sensor_history(
            config.sensor_name,
            config.history_minutes
        )
        
        if not history_data:
            print(f"Error: No historical data available for sensor {config.sensor_name}")
            print("Please check:")
            print("  1. The sensor name is correct")
            print("  2. The sensor has recorded data in the specified time window")
            print("  3. Home Assistant is accessible")
            sys.exit(1)
        
        if args.verbose:
            print(f"Retrieved {len(history_data)} data points")
        
        # Initialize forecaster
        forecaster = BatteryForecast(config.threshold_percent)
        
        # Calculate forecast
        if args.verbose:
            print("Calculating forecast...\n")
        
        forecast_result = forecaster.forecast_threshold_time(history_data)
        
        # Display results
        formatted_output = forecaster.format_forecast_result(forecast_result)
        print(formatted_output)
        
        # Return exit code based on result
        if forecast_result['current_soc'] <= config.threshold_percent:
            sys.exit(2)  # Critical - already below threshold
        elif forecast_result['eta']:
            sys.exit(1)  # Warning - will reach threshold
        else:
            sys.exit(0)  # OK - stable or increasing
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
