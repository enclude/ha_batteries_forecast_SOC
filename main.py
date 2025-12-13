#!/usr/bin/env python3
"""Main script for battery SOC forecasting and charging optimization."""
import sys
import argparse
import logging
from config_loader import Config
from ha_api_client import HomeAssistantClient
from forecast import BatteryForecast
from pstryk_api_client import PstrykApiClient
from openai_api_client import OpenAIChargingAdvisor
from charging_optimizer import ChargingOptimizer

# Exit codes
EXIT_OK = 0  # Battery is stable or increasing
EXIT_WARNING = 1  # Battery will reach threshold based on forecast
EXIT_CRITICAL = 2  # Battery is already at or below threshold


def main():
    """Main function to run battery forecast and charging optimization."""
    parser = argparse.ArgumentParser(
        description='Forecast battery State of Charge (SOC) and optimize charging'
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
    parser.add_argument(
        '--forecast-only',
        action='store_true',
        help='Only run SOC forecast, skip charging optimization'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    else:
        logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    
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
        
        # Run charging optimization if enabled and not skipped
        if config.charging_enabled and not args.forecast_only:
            try:
                if args.verbose:
                    print("\n" + "="*60)
                    print("Running charging optimization...")
                    print("="*60)
                
                # Initialize pstryk.pl client with configuration
                pstryk_client = PstrykApiClient(
                    api_key=config.pstryk_api_key if config.pstryk_api_key else None,
                    timeout=config.pstryk_timeout,
                    base_url=config.pstryk_base_url
                )
                
                # Initialize OpenAI advisor if API key is provided
                openai_advisor = None
                if config.openai_api_key and config.openai_api_key.strip():
                    if args.verbose:
                        print("Initializing OpenAI advisor...")
                    openai_advisor = OpenAIChargingAdvisor(config.openai_api_key)
                elif args.verbose:
                    print("OpenAI API key not configured, using rule-based optimization")
                
                # Initialize charging optimizer
                optimizer = ChargingOptimizer(ha_client, pstryk_client, openai_advisor)
                
                # Get charging recommendation
                if args.verbose:
                    print("Calculating optimal charging strategy...")
                    print(f"Battery: {config.battery_capacity_kwh}kWh, Max charging: {config.max_charging_power_kw}kW")
                
                recommendation = optimizer.optimize_charging(
                    forecast_result,
                    config.solar_sensors,
                    config.battery_capacity_kwh,
                    config.max_charging_power_kw,
                    config.allow_multiple_periods
                )
                
                # Display recommendation
                print("\n" + optimizer.format_recommendation(recommendation))
                
            except Exception as e:
                print(f"\nWarning: Charging optimization failed: {e}", file=sys.stderr)
                if args.verbose:
                    import traceback
                    traceback.print_exc()
        elif args.verbose and not config.charging_enabled:
            print("\nCharging optimization is disabled in configuration")
        
        # Return exit code based on result
        if forecast_result['current_soc'] <= config.threshold_percent:
            sys.exit(EXIT_CRITICAL)
        elif forecast_result['eta']:
            sys.exit(EXIT_WARNING)
        else:
            sys.exit(EXIT_OK)
        
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
