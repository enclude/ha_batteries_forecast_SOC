"""Battery charging optimizer using forecast data, prices, and AI recommendations."""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Configuration constants
CRITICAL_SOC_MULTIPLIER = 2  # Multiplier for critical battery threshold
LOW_SOLAR_THRESHOLD_KWH = 5.0  # Threshold for low solar production forecast
LOW_SOLAR_SOC_MULTIPLIER = 4  # Consider charging if below 4x threshold when solar is low
HOURS_TO_THRESHOLD_URGENT = 12  # Hours to threshold for high priority
HOURS_TO_THRESHOLD_MEDIUM = 24  # Hours to threshold for medium priority


class ChargingOptimizer:
    """Optimize battery charging based on multiple data sources."""
    
    def __init__(self, ha_client, pstryk_client, openai_advisor=None):
        """Initialize charging optimizer.
        
        Args:
            ha_client: HomeAssistantClient instance
            pstryk_client: PstrykApiClient instance
            openai_advisor: OpenAIChargingAdvisor instance (optional)
        """
        self.ha_client = ha_client
        self.pstryk_client = pstryk_client
        self.openai_advisor = openai_advisor
    
    def get_solar_forecast(self, sensor_names):
        """Fetch solar production forecast from Home Assistant sensors.
        
        Args:
            sensor_names: List of sensor entity IDs for solar production forecast
        
        Returns:
            dict: Solar production forecast with sensor names as keys
        """
        solar_data = {}
        
        for sensor_name in sensor_names:
            try:
                value = self.ha_client.get_current_state(sensor_name)
                solar_data[sensor_name] = value
                logger.info(f"Solar forecast from {sensor_name}: {value} kWh")
            except Exception as e:
                logger.warning(f"Failed to fetch solar forecast from {sensor_name}: {e}")
                solar_data[sensor_name] = 0.0
        
        return solar_data
    
    def calculate_total_solar_forecast(self, solar_data):
        """Calculate total expected solar production.
        
        Args:
            solar_data: Dictionary of solar sensor readings
        
        Returns:
            float: Total expected solar production in kWh
        """
        return sum(solar_data.values())
    
    def optimize_charging(self, forecast_data, solar_sensors, hours_needed=4):
        """Optimize battery charging schedule.
        
        Args:
            forecast_data: Battery SOC forecast data from BatteryForecast
            solar_sensors: List of solar production forecast sensor IDs
            hours_needed: Number of consecutive hours needed for charging
        
        Returns:
            dict: Comprehensive charging recommendation:
                {
                    'should_charge': bool,
                    'recommended_hours': list of int,
                    'start_hour': int or None,
                    'end_hour': int or None,
                    'reasoning': str,
                    'price_analysis': dict,
                    'solar_forecast': dict,
                    'ai_recommendation': dict or None,
                    'priority': str
                }
        """
        try:
            # Get electricity prices
            logger.info("Fetching electricity prices...")
            prices_today = self.pstryk_client.get_electricity_prices()
            cheapest_window = self.pstryk_client.get_cheapest_hours(hours_needed)
            
            # Get solar forecast
            logger.info("Fetching solar production forecast...")
            solar_data = self.get_solar_forecast(solar_sensors)
            total_solar = self.calculate_total_solar_forecast(solar_data)
            
            # Prepare result structure
            result = {
                'should_charge': False,
                'recommended_hours': [],
                'start_hour': None,
                'end_hour': None,
                'reasoning': '',
                'price_analysis': {
                    'cheapest_window': cheapest_window,
                    'prices': prices_today
                },
                'solar_forecast': {
                    'sensors': solar_data,
                    'total_expected': total_solar
                },
                'ai_recommendation': None,
                'priority': 'low'
            }
            
            # Rule-based analysis
            rule_based_decision = self._rule_based_recommendation(
                forecast_data, 
                cheapest_window, 
                total_solar
            )
            
            # Get AI recommendation if available
            if self.openai_advisor:
                logger.info("Getting AI-powered recommendation...")
                try:
                    ai_recommendation = self.openai_advisor.analyze_charging_strategy(
                        forecast_data,
                        prices_today,
                        solar_data
                    )
                    result['ai_recommendation'] = ai_recommendation
                    
                    # Use AI recommendation
                    result['should_charge'] = ai_recommendation['should_charge']
                    result['recommended_hours'] = ai_recommendation['recommended_hours']
                    result['reasoning'] = ai_recommendation['reasoning']
                    result['priority'] = ai_recommendation['priority']
                    
                    if result['recommended_hours']:
                        result['start_hour'] = min(result['recommended_hours'])
                        result['end_hour'] = max(result['recommended_hours'])
                    
                except Exception as e:
                    logger.warning(f"AI recommendation failed, using rule-based: {e}")
                    # Fall back to rule-based
                    result.update(rule_based_decision)
            else:
                # Use rule-based recommendation
                result.update(rule_based_decision)
            
            return result
            
        except Exception as e:
            logger.error(f"Error during charging optimization: {e}")
            return {
                'should_charge': False,
                'recommended_hours': [],
                'start_hour': None,
                'end_hour': None,
                'reasoning': f"Error: {str(e)}",
                'price_analysis': {},
                'solar_forecast': {},
                'ai_recommendation': None,
                'priority': 'low'
            }
    
    def _rule_based_recommendation(self, forecast_data, cheapest_window, total_solar, current_time=None):
        """Generate rule-based charging recommendation.
        
        Args:
            forecast_data: Battery SOC forecast data
            cheapest_window: Cheapest price window from pstryk.pl
            total_solar: Total expected solar production
            current_time: Current datetime (for testing), defaults to datetime.now()
        
        Returns:
            dict: Rule-based charging decision
        """
        if current_time is None:
            current_time = datetime.now()
            
        current_soc = forecast_data['current_soc']
        threshold = forecast_data['threshold']
        is_declining = forecast_data['is_declining']
        
        # Decision logic
        should_charge = False
        priority = 'low'
        reasoning_parts = []
        
        # Check if battery is critically low
        if current_soc <= threshold * CRITICAL_SOC_MULTIPLIER:
            should_charge = True
            priority = 'high'
            reasoning_parts.append(f"Battery is critically low at {current_soc:.1f}%")
        
        # Check if battery is declining and will reach threshold soon
        elif is_declining and forecast_data.get('eta'):
            eta = forecast_data['eta']
            hours_to_threshold = (eta - current_time).total_seconds() / 3600
            
            if hours_to_threshold < HOURS_TO_THRESHOLD_URGENT:
                should_charge = True
                priority = 'high'
                reasoning_parts.append(f"Battery will reach threshold in {hours_to_threshold:.1f} hours")
            elif hours_to_threshold < HOURS_TO_THRESHOLD_MEDIUM:
                should_charge = True
                priority = 'medium'
                reasoning_parts.append(f"Battery forecast shows decline reaching threshold in {hours_to_threshold:.1f} hours")
        
        # Check solar forecast - if low, consider charging
        if total_solar < LOW_SOLAR_THRESHOLD_KWH:
            reasoning_parts.append(f"Low solar forecast: {total_solar:.1f} kWh expected")
            if not should_charge and current_soc < threshold * LOW_SOLAR_SOC_MULTIPLIER:
                should_charge = True
                priority = 'medium'
        else:
            reasoning_parts.append(f"Good solar forecast: {total_solar:.1f} kWh expected")
        
        # Add price information
        if cheapest_window:
            reasoning_parts.append(
                f"Cheapest charging window: {cheapest_window['start_hour']:02d}:00-{cheapest_window['end_hour']:02d}:00 "
                f"at avg {cheapest_window['avg_price']:.4f} PLN/kWh"
            )
        
        # Determine recommended hours
        recommended_hours = []
        start_hour = None
        end_hour = None
        
        if should_charge and cheapest_window:
            recommended_hours = list(range(
                cheapest_window['start_hour'],
                cheapest_window['end_hour'] + 1
            ))
            start_hour = cheapest_window['start_hour']
            end_hour = cheapest_window['end_hour']
        
        reasoning = " | ".join(reasoning_parts) if reasoning_parts else "No charging needed"
        
        return {
            'should_charge': should_charge,
            'recommended_hours': recommended_hours,
            'start_hour': start_hour,
            'end_hour': end_hour,
            'reasoning': reasoning,
            'priority': priority
        }
    
    def format_recommendation(self, recommendation):
        """Format charging recommendation as human-readable string.
        
        Args:
            recommendation: Recommendation dict from optimize_charging()
        
        Returns:
            str: Formatted recommendation
        """
        lines = []
        lines.append("=" * 60)
        lines.append("Battery Charging Recommendation")
        lines.append("=" * 60)
        
        # Charging decision
        if recommendation['should_charge']:
            lines.append(f"✓ Charging RECOMMENDED (Priority: {recommendation['priority'].upper()})")
            if recommendation['start_hour'] is not None:
                lines.append(f"  Recommended window: {recommendation['start_hour']:02d}:00 - {recommendation['end_hour']:02d}:00")
            if recommendation['recommended_hours']:
                lines.append(f"  Hours: {', '.join(f'{h:02d}:00' for h in recommendation['recommended_hours'])}")
        else:
            lines.append("○ Charging NOT recommended at this time")
        
        lines.append(f"\nReasoning:")
        lines.append(f"  {recommendation['reasoning']}")
        
        # Solar forecast
        if recommendation['solar_forecast']:
            lines.append(f"\nSolar Production Forecast:")
            total = recommendation['solar_forecast'].get('total_expected', 0)
            lines.append(f"  Total expected: {total:.2f} kWh")
            for sensor, value in recommendation['solar_forecast'].get('sensors', {}).items():
                sensor_short = sensor.replace('sensor.energy_production_today_', '').replace('sensor.energy_production_today', 'main')
                lines.append(f"  {sensor_short}: {value:.2f} kWh")
        
        # Price analysis
        if recommendation['price_analysis'].get('cheapest_window'):
            window = recommendation['price_analysis']['cheapest_window']
            lines.append(f"\nElectricity Price Analysis:")
            lines.append(f"  Cheapest {window['hours']}h window: {window['start_hour']:02d}:00 - {window['end_hour']:02d}:00")
            lines.append(f"  Average price: {window['avg_price']:.4f} PLN/kWh")
        
        # AI analysis if available
        if recommendation.get('ai_recommendation'):
            ai_rec = recommendation['ai_recommendation']
            if ai_rec.get('estimated_savings'):
                lines.append(f"\nEstimated savings: {ai_rec['estimated_savings']:.4f} PLN/kWh vs. average")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
