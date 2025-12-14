"""Battery charging optimizer using forecast data, prices, and AI recommendations."""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Configuration constants
CRITICAL_SOC_MULTIPLIER = 2  # Multiplier for critical battery threshold
HOURS_TO_THRESHOLD_URGENT = 12  # Hours to threshold for high priority
HOURS_TO_THRESHOLD_MEDIUM = 24  # Hours to threshold for medium priority


class ChargingOptimizer:
    """Optimize battery charging based on multiple data sources."""
    
    def __init__(self, ha_client, pstryk_client, openai_advisor=None, power_sensors=None, soc_sensor_name=None):
        """Initialize charging optimizer.
        
        Args:
            ha_client: HomeAssistantClient instance
            pstryk_client: PstrykApiClient instance
            openai_advisor: OpenAIChargingAdvisor instance (optional)
            power_sensors: List of power consumption sensor IDs (optional)
            soc_sensor_name: Battery SOC sensor entity ID (optional)
        """
        self.ha_client = ha_client
        self.pstryk_client = pstryk_client
        self.openai_advisor = openai_advisor
        self._price_cache = None  # Cache for electricity prices
        self._power_sensors = power_sensors or []
        self._soc_sensor_name = soc_sensor_name
    
    def get_soc_history(self, sensor_name, history_hours=72):
        """Fetch SOC history for better predictions.
        
        Args:
            sensor_name: Battery SOC sensor entity ID
            history_hours: Hours of historical SOC data to fetch
        
        Returns:
            list: List of tuples (timestamp, soc_value) representing SOC history
        """
        try:
            history_minutes = history_hours * 60
            logger.info(f"Fetching {history_hours}h SOC history for predictions...")
            
            history_data = self.ha_client.get_sensor_history(
                sensor_name,
                history_minutes,
                include_current_state=True
            )
            
            if history_data:
                logger.info(f"Retrieved {len(history_data)} SOC data points over {history_hours}h")
                # Calculate some statistics for logging
                soc_values = [soc for _, soc in history_data]
                avg_soc = sum(soc_values) / len(soc_values)
                min_soc = min(soc_values)
                max_soc = max(soc_values)
                logger.info(f"SOC history stats: avg={avg_soc:.1f}%, min={min_soc:.1f}%, max={max_soc:.1f}%")
                return history_data
            else:
                logger.warning("No SOC history data available")
                return []
        except Exception as e:
            logger.error(f"Failed to fetch SOC history: {e}")
            return []
    
    def get_power_consumption_forecast(self, sensor_names, history_hours=72):
        """Fetch and analyze power consumption to forecast future usage.
        
        Args:
            sensor_names: List of power sensor entity IDs.
                          Can be instantaneous power sensors (Watts) or cumulative energy sensors (kWh).
                          For cumulative sensors (total_forward_active_energy), calculates power from deltas.
            history_hours: Hours of historical data to analyze (default: 72)
        
        Returns:
            dict: Power consumption forecast with statistics:
                {
                    'average_power_w': float,  # Average power consumption in Watts
                    'peak_power_w': float,     # Peak power consumption in Watts
                    'hourly_average_kwh': float,  # Average kWh per hour
                    'daily_forecast_kwh': float,  # Forecasted daily consumption
                    'next_hour_forecast_kwh': float  # Forecasted consumption for next hour
                }
        """
        try:
            history_minutes = history_hours * 60
            power_history = []  # Will store (timestamp, power_in_watts) tuples
            
            logger.info(f"Fetching {history_hours}h power consumption history from {len(sensor_names)} sensors...")
            
            # Fetch history for all power sensors
            for sensor_name in sensor_names:
                try:
                    history = self.ha_client.get_sensor_history(
                        sensor_name,
                        history_minutes,
                        include_current_state=True
                    )
                    
                    if not history:
                        logger.warning(f"No history data for {sensor_name}")
                        continue
                    
                    logger.info(f"Power sensor {sensor_name}: {len(history)} readings")
                    
                    # Check if this is a cumulative energy sensor (kWh) or instantaneous power sensor (W)
                    # Cumulative sensors have "energy" or "total" in their name
                    is_cumulative = 'energy' in sensor_name.lower() or 'total' in sensor_name.lower()
                    
                    if is_cumulative:
                        logger.info(f"Detected cumulative energy sensor: {sensor_name}, resampling to 15-minute intervals")
                        
                        # Resample to 15-minute intervals for consistent data points
                        # This gives us 4 readings per hour, 96 per day, ~288 for 72 hours
                        interval_minutes = 15
                        
                        if len(history) < 2:
                            logger.warning(f"Not enough data points for resampling: {len(history)}")
                            continue
                        
                        # Sort history by timestamp
                        history.sort(key=lambda x: x[0])
                        
                        # Get start and end times
                        start_time = history[0][0]
                        end_time = history[-1][0]
                        
                        # Create 15-minute interval timestamps
                        current_time = start_time
                        interval_delta = timedelta(minutes=interval_minutes)
                        
                        while current_time <= end_time:
                            # Find the next timestamp after current_time
                            next_time = current_time + interval_delta
                            
                            # Find readings around this interval
                            prev_reading = None
                            next_reading = None
                            
                            for ts, kwh in history:
                                if ts <= current_time:
                                    prev_reading = (ts, kwh)
                                elif ts <= next_time:
                                    next_reading = (ts, kwh)
                                    break
                            
                            # If we have both readings, calculate power for this interval
                            if prev_reading and next_reading:
                                prev_ts, prev_kwh = prev_reading
                                next_ts, next_kwh = next_reading
                                
                                # Calculate time difference in hours
                                time_delta_hours = (next_ts - prev_ts).total_seconds() / 3600
                                
                                if time_delta_hours > 0 and next_kwh >= prev_kwh:
                                    # Calculate energy consumed in this period (kWh)
                                    energy_delta_kwh = next_kwh - prev_kwh
                                    
                                    # Calculate average power during this period (W)
                                    power_w = (energy_delta_kwh / time_delta_hours) * 1000
                                    
                                    # Use the interval midpoint as timestamp
                                    interval_midpoint = current_time + timedelta(minutes=interval_minutes/2)
                                    power_history.append((interval_midpoint, power_w))
                            
                            current_time = next_time
                        
                        logger.info(f"Resampled to {len([p for p in power_history if p[0] >= start_time])} 15-minute intervals")
                    else:
                        logger.info(f"Detected instantaneous power sensor: {sensor_name}")
                        # Direct power readings in Watts
                        power_history.extend([(ts, value) for ts, value in history])
                    
                except Exception as e:
                    logger.warning(f"Failed to fetch power data from {sensor_name}: {e}")
                    continue
            
            if not power_history:
                logger.warning("No power consumption data available")
                return {
                    'average_power_w': 0,
                    'peak_power_w': 0,
                    'hourly_average_kwh': 0,
                    'daily_forecast_kwh': 0,
                    'next_hour_forecast_kwh': 0,
                    'data_points': 0,
                    'raw_history': []
                }
            
            # Sort by timestamp
            power_history.sort(key=lambda x: x[0])
            
            # Calculate statistics
            power_values = [value for _, value in power_history]
            average_power_w = sum(power_values) / len(power_values)
            peak_power_w = max(power_values)
            
            # Convert to kWh
            hourly_average_kwh = average_power_w / 1000
            daily_forecast_kwh = hourly_average_kwh * 24
            
            # Forecast next hour: use average of last 3 hours or overall average
            recent_cutoff = power_history[-1][0] - timedelta(hours=3)
            recent_values = [value for ts, value in power_history if ts >= recent_cutoff]
            
            if recent_values:
                next_hour_power_w = sum(recent_values) / len(recent_values)
            else:
                next_hour_power_w = average_power_w
            
            next_hour_forecast_kwh = next_hour_power_w / 1000
            
            logger.info(f"Power consumption analysis: avg={average_power_w:.0f}W, peak={peak_power_w:.0f}W")
            logger.info(f"Daily forecast: {daily_forecast_kwh:.2f} kWh, Next hour: {next_hour_forecast_kwh:.2f} kWh")
            
            return {
                'average_power_w': average_power_w,
                'peak_power_w': peak_power_w,
                'hourly_average_kwh': hourly_average_kwh,
                'daily_forecast_kwh': daily_forecast_kwh,
                'next_hour_forecast_kwh': next_hour_forecast_kwh,
                'data_points': len(power_history),
                'raw_history': power_history
            }
            
        except Exception as e:
            logger.error(f"Error calculating power consumption forecast: {e}")
            return {
                'average_power_w': 0,
                'peak_power_w': 0,
                'hourly_average_kwh': 0,
                'daily_forecast_kwh': 0,
                'next_hour_forecast_kwh': 0,
                'data_points': 0,
                'raw_history': []
            }
    
    def calculate_charging_hours_needed(self, current_soc, target_soc, battery_capacity_kwh, max_charging_power_kw):
        """Calculate hours needed to charge battery from current to target SOC.
        
        Args:
            current_soc: Current state of charge (percentage)
            target_soc: Target state of charge (percentage)
            battery_capacity_kwh: Battery capacity in kWh
            max_charging_power_kw: Maximum charging power in kW
        
        Returns:
            int: Number of hours needed (rounded up)
        """
        import math
        
        # Calculate energy needed
        soc_deficit = target_soc - current_soc
        if soc_deficit <= 0:
            return 0
        
        energy_needed_kwh = (soc_deficit / 100) * battery_capacity_kwh
        
        # Calculate hours needed
        hours_needed = energy_needed_kwh / max_charging_power_kw
        
        # Round up to nearest hour
        return math.ceil(hours_needed)
    
    def optimize_charging(self, forecast_data, battery_capacity_kwh=10, 
                         max_charging_power_kw=5, allow_multiple_periods=True):
        """Optimize battery charging schedule.
        
        Args:
            forecast_data: Battery SOC forecast data from BatteryForecast
            battery_capacity_kwh: Battery capacity in kWh
            max_charging_power_kw: Maximum charging power from grid in kW
            allow_multiple_periods: Allow multiple non-consecutive charging periods
        
        Returns:
            dict: Comprehensive charging recommendation:
                {
                    'should_charge': bool,
                    'recommended_hours': list of int,
                    'charging_periods': list of dicts (multiple periods),
                    'hours_needed': int,
                    'reasoning': str,
                    'price_analysis': dict,
                    'ai_recommendation': dict or None,
                    'priority': str
                }
        """
        try:
            # Calculate hours needed based on current SOC
            current_soc = forecast_data['current_soc']
            target_soc = 100  # Assume we want to charge to 100%
            hours_needed = self.calculate_charging_hours_needed(
                current_soc, target_soc, battery_capacity_kwh, max_charging_power_kw
            )
            
            logger.info(f"Calculated charging hours needed: {hours_needed}h (SOC: {current_soc:.1f}% -> {target_soc}%)")
            
            # Get electricity prices (with caching to avoid rate limiting)
            if self._price_cache is None:
                logger.info("Fetching electricity prices...")
                self._price_cache = self.pstryk_client.get_electricity_prices()
            else:
                logger.info("Using cached electricity prices")
            prices_today = self._price_cache
            
            # Get cheapest charging windows/periods (using cached data)
            if allow_multiple_periods and hours_needed > 0:
                cheapest_periods = self.pstryk_client.get_cheapest_hours_multiple_periods(hours_needed, use_cached_prices=prices_today)
                # Also get single window for comparison
                try:
                    cheapest_window = self.pstryk_client.get_cheapest_hours(hours_needed, use_cached_prices=prices_today)
                except:
                    cheapest_window = None
            else:
                if hours_needed > 0:
                    cheapest_window = self.pstryk_client.get_cheapest_hours(hours_needed, use_cached_prices=prices_today)
                    cheapest_periods = [cheapest_window]
                else:
                    cheapest_window = None
                    cheapest_periods = []
            

            
            # Get power consumption forecast (if sensors configured)
            power_forecast = {'daily_forecast_kwh': 0, 'next_hour_forecast_kwh': 0}
            if hasattr(self, '_power_sensors') and self._power_sensors:
                power_forecast = self.get_power_consumption_forecast(
                    self._power_sensors,
                    history_hours=72
                )
            else:
                logger.debug("No power consumption sensors configured, skipping power forecast")
            
            # Get SOC history for better predictions (if sensor name available)
            soc_history = []
            if hasattr(self, '_soc_sensor_name') and self._soc_sensor_name:
                soc_history = self.get_soc_history(self._soc_sensor_name, history_hours=72)
            else:
                logger.debug("No SOC sensor configured, skipping SOC history")
            
            # Prepare result structure
            result = {
                'should_charge': False,
                'recommended_hours': [],
                'charging_periods': cheapest_periods,
                'hours_needed': hours_needed,
                'start_hour': None,
                'end_hour': None,
                'reasoning': '',
                'price_analysis': {
                    'cheapest_window': cheapest_window,
                    'cheapest_periods': cheapest_periods,
                    'prices': prices_today
                },
                'ai_recommendation': None,
                'priority': 'low',
                'battery_info': {
                    'capacity_kwh': battery_capacity_kwh,
                    'max_charging_power_kw': max_charging_power_kw,
                    'current_soc': current_soc,
                    'target_soc': target_soc
                }
            }
            
            # Rule-based analysis
            rule_based_decision = self._rule_based_recommendation(
                forecast_data, 
                cheapest_periods
            )
            
            # Get AI recommendation if available
            if self.openai_advisor:
                logger.info("Getting AI-powered recommendation...")
                try:
                    ai_recommendation = self.openai_advisor.analyze_charging_strategy(
                        forecast_data,
                        prices_today,
                        power_forecast=power_forecast,
                        soc_history=soc_history
                    )
                    result['ai_recommendation'] = ai_recommendation
                    
                    # Use AI recommendation, but filter to only future hours
                    from datetime import datetime
                    current_hour = datetime.now().hour
                    
                    # Filter recommended hours to only include current and future hours
                    recommended_hours = ai_recommendation['recommended_hours']
                    future_hours = [h for h in recommended_hours if h >= current_hour]
                    
                    result['should_charge'] = ai_recommendation['should_charge'] and len(future_hours) > 0
                    result['recommended_hours'] = future_hours
                    result['reasoning'] = ai_recommendation['reasoning']
                    if future_hours != recommended_hours:
                        removed_count = len(recommended_hours) - len(future_hours)
                        result['reasoning'] += f" | Note: {removed_count} past hour(s) excluded from recommendation"
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
                'ai_recommendation': None,
                'priority': 'low'
            }
    
    def _rule_based_recommendation(self, forecast_data, cheapest_periods, current_time=None):
        """Generate rule-based charging recommendation.
        
        Args:
            forecast_data: Battery SOC forecast data
            cheapest_periods: List of cheapest price periods from pstryk.pl
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
            # Ensure both datetimes are comparable (remove timezone info if present)
            eta_naive = eta.replace(tzinfo=None) if hasattr(eta, 'tzinfo') and eta.tzinfo else eta
            current_time_naive = current_time.replace(tzinfo=None) if hasattr(current_time, 'tzinfo') and current_time.tzinfo else current_time
            hours_to_threshold = (eta_naive - current_time_naive).total_seconds() / 3600
            
            if hours_to_threshold < HOURS_TO_THRESHOLD_URGENT:
                should_charge = True
                priority = 'high'
                reasoning_parts.append(f"Battery will reach threshold in {hours_to_threshold:.1f} hours")
            elif hours_to_threshold < HOURS_TO_THRESHOLD_MEDIUM:
                should_charge = True
                priority = 'medium'
                reasoning_parts.append(f"Battery forecast shows decline reaching threshold in {hours_to_threshold:.1f} hours")
        
        # Add price information
        if cheapest_periods:
            if len(cheapest_periods) == 1:
                period = cheapest_periods[0]
                reasoning_parts.append(
                    f"Cheapest charging window: {period['start_hour']:02d}:00-{period['end_hour']:02d}:00 "
                    f"({period['hours']}h at avg {period['avg_price']:.4f} PLN/kWh)"
                )
            else:
                total_hours = sum(p['hours'] for p in cheapest_periods)
                avg_price = sum(p['total_cost_per_kwh'] for p in cheapest_periods) / total_hours
                reasoning_parts.append(
                    f"Cheapest charging: {len(cheapest_periods)} period(s), {total_hours}h total "
                    f"at avg {avg_price:.4f} PLN/kWh"
                )
        
        # Determine recommended hours
        recommended_hours = []
        start_hour = None
        end_hour = None
        
        if should_charge and cheapest_periods:
            # Collect all hours from all periods
            for period in cheapest_periods:
                recommended_hours.extend(list(range(
                    period['start_hour'],
                    period['end_hour'] + 1
                )))
            recommended_hours.sort()
            start_hour = min(recommended_hours) if recommended_hours else None
            end_hour = max(recommended_hours) if recommended_hours else None
        
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
        
        # Battery info
        if recommendation.get('battery_info'):
            battery = recommendation['battery_info']
            lines.append(f"Battery: {battery['capacity_kwh']}kWh capacity, {battery['max_charging_power_kw']}kW max charging power")
            lines.append(f"Current SOC: {battery['current_soc']:.1f}%")
        
        if recommendation.get('hours_needed'):
            lines.append(f"Charging hours needed: {recommendation['hours_needed']}h")
        
        # Charging decision
        if recommendation['should_charge']:
            lines.append(f"\n✓ Charging RECOMMENDED (Priority: {recommendation['priority'].upper()})")
            
            # Show charging periods
            if recommendation.get('charging_periods'):
                periods = recommendation['charging_periods']
                if len(periods) == 1:
                    period = periods[0]
                    lines.append(f"  Recommended period: {period['start_hour']:02d}:00 - {period['end_hour']:02d}:00 ({period['hours']}h)")
                else:
                    lines.append(f"  Recommended periods ({len(periods)} periods):")
                    for i, period in enumerate(periods, 1):
                        lines.append(f"    {i}. {period['start_hour']:02d}:00 - {period['end_hour']:02d}:00 ({period['hours']}h at {period['avg_price']:.4f} PLN/kWh)")
            elif recommendation['start_hour'] is not None:
                lines.append(f"  Recommended window: {recommendation['start_hour']:02d}:00 - {recommendation['end_hour']:02d}:00")
            
            if recommendation['recommended_hours'] and len(recommendation['recommended_hours']) <= 10:
                lines.append(f"  All hours: {', '.join(f'{h:02d}:00' for h in recommendation['recommended_hours'])}")
        else:
            lines.append("\n○ Charging NOT recommended at this time")
        
        lines.append(f"\nReasoning:")
        lines.append(f"  {recommendation['reasoning']}")
        
        # Price analysis
        if recommendation['price_analysis'].get('cheapest_periods'):
            periods = recommendation['price_analysis']['cheapest_periods']
            lines.append(f"\nElectricity Price Analysis:")
            if len(periods) == 1:
                period = periods[0]
                lines.append(f"  Cheapest period: {period['start_hour']:02d}:00 - {period['end_hour']:02d}:00 ({period['hours']}h)")
                lines.append(f"  Average price: {period['avg_price']:.4f} PLN/kWh")
            else:
                total_hours = sum(p['hours'] for p in periods)
                avg_price = sum(p['total_cost_per_kwh'] for p in periods) / total_hours if total_hours > 0 else 0
                lines.append(f"  {len(periods)} period(s) totaling {total_hours}h")
                lines.append(f"  Average price: {avg_price:.4f} PLN/kWh")
        
        # AI analysis if available
        if recommendation.get('ai_recommendation'):
            ai_rec = recommendation['ai_recommendation']
            if ai_rec.get('estimated_savings'):
                lines.append(f"\nEstimated savings: {ai_rec['estimated_savings']:.4f} PLN/kWh vs. average")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
