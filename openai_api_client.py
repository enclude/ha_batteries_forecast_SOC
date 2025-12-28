"""OpenAI API client for intelligent charging recommendations."""
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

# Default model for cost-effective recommendations
DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIChargingAdvisor:
    """OpenAI-powered charging advisor for battery optimization."""
    
    def __init__(self, api_key, model=None, verbose=False):
        """Initialize OpenAI API client.
        
        Args:
            api_key: OpenAI API key
            model: OpenAI model to use (default: gpt-4o-mini)
            verbose: Enable verbose logging of raw data sent to API
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model or DEFAULT_MODEL
        self.verbose = verbose
    
    def analyze_charging_strategy(self, forecast_data, price_data, power_forecast=None, soc_history=None):
        """Analyze data and recommend optimal charging strategy.
        
        Args:
            forecast_data: Battery SOC forecast data (dict from BatteryForecast)
            price_data: Electricity price data from pstryk.pl (list of dicts)
            power_forecast: Power consumption forecast (optional)
            soc_history: Historical SOC data for pattern analysis (optional)
        
        Returns:
            dict: Charging recommendations with structure:
                {
                    'should_charge': bool,
                    'recommended_hours': list of int (hours 0-23),
                    'reasoning': str,
                    'estimated_savings': float or None,
                    'priority': str ('high', 'medium', 'low')
                }
        """
        try:
            # Build context for GPT
            context = self._build_context(forecast_data, price_data, power_forecast, soc_history)
            
            # Create system prompt
            system_prompt = """You are an expert energy management advisor for home battery systems.
Your task is to analyze battery state of charge forecasts, electricity prices,
and power consumption patterns to recommend optimal charging times from the grid.

Consider:
1. Battery discharge rate and forecast SOC levels
2. Hourly electricity prices
3. Historical power consumption patterns to predict future usage
4. Battery SOC history to understand usage patterns
5. Balance between cost savings and ensuring adequate battery charge

Use the power consumption data to:
- Predict when the battery will be most needed
- Estimate how much energy will be consumed
- Recommend charging before high-consumption periods
- Avoid charging during peak usage times

Provide practical, cost-effective recommendations based on all available data."""

            # Create user prompt
            user_prompt = f"""Analyze the following data and recommend charging strategy:

Battery Status:
- Current SOC: {forecast_data['current_soc']:.1f}%
- Threshold: {forecast_data['threshold']}%
- Declining: {forecast_data['is_declining']}
- Rate of change: {forecast_data['trend']['slope'] * 3600:.2f}% per hour
{f"- ETA to threshold: {forecast_data['eta'].strftime('%Y-%m-%d %H:%M')}" if forecast_data.get('eta') else ""}

Electricity Prices (PLN/kWh):
{self._format_prices(price_data)}
{self._format_power_forecast(power_forecast) if power_forecast else ""}
{self._format_soc_history(soc_history) if soc_history else ""}

Based on this data:
1. Should the battery be charged from the grid?
2. What are the optimal hours to charge (provide specific hours 0-23)?
   - If tomorrow's prices are available, consider both days for optimal planning
   - Prioritize cheapest hours across both days
3. Explain your reasoning considering:
   - Cost optimization (electricity prices for today and tomorrow if available)
   - SOC forecast and battery decline rate
   - Power consumption patterns (daily average, peak times, next hour forecast)
   - SOC history patterns to predict future behavior
4. What's the priority level (high/medium/low)?

Respond in JSON format:
{{
    "should_charge": true/false,
    "recommended_hours": [list of hours 0-23 for today, considering tomorrow's prices if available],
    "reasoning": "explanation",
    "priority": "high/medium/low"
}}"""

            # Log raw data if verbose mode is enabled
            if self.verbose:
                logger.info("="*80)
                logger.info("RAW DATA SENT TO OPENAI API:")
                logger.info("="*80)
                logger.info("\nSYSTEM PROMPT:")
                logger.info(system_prompt)
                logger.info("\n" + "-"*80)
                logger.info("USER PROMPT:")
                logger.info(user_prompt)
                logger.info("="*80)

            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,  # Lower temperature for more consistent recommendations
                max_tokens=1000
            )
            
            # Parse response
            import json
            result = json.loads(response.choices[0].message.content)
            
            # Validate and enhance result
            if 'should_charge' not in result:
                result['should_charge'] = False
            if 'recommended_hours' not in result:
                result['recommended_hours'] = []
            if 'reasoning' not in result:
                result['reasoning'] = "No specific reasoning provided"
            if 'priority' not in result:
                result['priority'] = 'medium'
            
            # Calculate estimated savings if charging is recommended
            if result['should_charge'] and result['recommended_hours']:
                result['estimated_savings'] = self._calculate_savings(
                    result['recommended_hours'], 
                    price_data
                )
            else:
                result['estimated_savings'] = None
            
            logger.info(f"OpenAI recommendation: charge={result['should_charge']}, hours={result['recommended_hours']}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get OpenAI recommendation: {e}")
            # Return safe fallback
            return {
                'should_charge': False,
                'recommended_hours': [],
                'reasoning': f"Error during analysis: {str(e)}",
                'estimated_savings': None,
                'priority': 'low'
            }
    
    def _build_context(self, forecast_data, price_data, power_forecast=None, soc_history=None):
        """Build context string from input data."""
        context = {
            'forecast': forecast_data,
            'prices': price_data
        }
        
        if power_forecast:
            context['power_consumption'] = power_forecast
        
        if soc_history:
            # Include summary of SOC history for pattern analysis
            soc_values = [soc for _, soc in soc_history[-24:]]  # Last 24 data points
            if soc_values:
                context['soc_history'] = {
                    'recent_average': sum(soc_values) / len(soc_values),
                    'recent_min': min(soc_values),
                    'recent_max': max(soc_values),
                    'data_points': len(soc_history),
                    'hours_covered': len(soc_history) / 12  # Assuming ~5min intervals
                }
        
        return context
    
    def _format_prices(self, price_data):
        """Format price data for prompt, including today and tomorrow if available."""
        if not price_data:
            return "No price data available"
        
        # Separate today and tomorrow prices
        today_prices = []
        tomorrow_prices = []
        
        for price in price_data:
            if price.get('day_label') == 'tomorrow':
                tomorrow_prices.append(price)
            else:
                today_prices.append(price)
        
        lines = []
        
        # Format today's prices
        if today_prices:
            lines.append("Today's prices:")
            for price in sorted(today_prices, key=lambda x: x['hour'])[:24]:
                lines.append(f"  {price['hour']:02d}:00 - {price['price']:.4f} PLN/kWh")
        
        # Format tomorrow's prices if available
        if tomorrow_prices:
            lines.append("\nTomorrow's prices (available after 14:00):")
            for price in sorted(tomorrow_prices, key=lambda x: x['hour'])[:24]:
                # Show original hour (0-23) for tomorrow
                original_hour = price['hour'] - 24 if price['hour'] >= 24 else price['hour']
                lines.append(f"  {original_hour:02d}:00 - {price['price']:.4f} PLN/kWh")
        
        return "\n".join(lines)
    
    def _format_power_forecast(self, power_forecast):
        """Format power consumption forecast for prompt."""
        if not power_forecast or power_forecast.get('daily_forecast_kwh', 0) == 0:
            return ""
        
        result = f"""
Power Consumption Forecast:
  Average power: {power_forecast.get('average_power_w', 0):.0f}W
  Hourly average: {power_forecast.get('hourly_average_kwh', 0):.2f} kWh/h
  Daily forecast: {power_forecast.get('daily_forecast_kwh', 0):.2f} kWh
  Next hour forecast: {power_forecast.get('next_hour_forecast_kwh', 0):.2f} kWh
"""
        
        # Include sampled historical data if available (to avoid token limits)
        if power_forecast.get('raw_history'):
            history = power_forecast['raw_history']
            total_points = len(history)
            
            # Sample data intelligently to stay within token limits
            # Target: ~100-150 data points max (one per ~30 minutes for 72h history)
            max_samples = 150
            
            if total_points <= max_samples:
                sampled_history = history
            else:
                # Sample evenly across the time period
                step = total_points // max_samples
                sampled_history = history[::step][:max_samples]
            
            result += f"\nPower Consumption History (sampled {len(sampled_history)} of {total_points} points):\n"
            result += "Timestamp, Power (W)\n"
            for timestamp, power_w in sampled_history:
                result += f"{timestamp.strftime('%Y-%m-%d %H:%M')}, {power_w:.0f}\n"
        
        return result
    
    def _format_soc_history(self, soc_history):
        """Format SOC history for prompt."""
        if not soc_history:
            return ""
        
        # Get recent SOC values for pattern analysis
        soc_values = [soc for _, soc in soc_history]  # All data points
        if not soc_values:
            return ""
        
        avg_soc = sum(soc_values) / len(soc_values)
        min_soc = min(soc_values)
        max_soc = max(soc_values)
        
        total_points = len(soc_history)
        
        # Sample data intelligently to stay within token limits
        # Target: ~100-150 data points max (one per ~30 minutes for 72h history)
        max_samples = 150
        
        if total_points <= max_samples:
            sampled_history = soc_history
        else:
            # Sample evenly across the time period
            step = total_points // max_samples
            sampled_history = soc_history[::step][:max_samples]
        
        result = f"""
Battery SOC History ({len(sampled_history)} of {total_points} readings over ~{total_points/12:.0f}h):
  Average: {avg_soc:.1f}%
  Minimum: {min_soc:.1f}%
  Maximum: {max_soc:.1f}%

Sampled SOC History:
Timestamp, SOC %
"""
        
        # Include sampled historical data points
        for timestamp, soc in sampled_history:
            result += f"{timestamp.strftime('%Y-%m-%d %H:%M')}, {soc:.1f}\n"
        
        return result    
    def _calculate_savings(self, recommended_hours, price_data):
        """Calculate estimated savings based on recommended hours.
        
        This is a simplified calculation comparing average price vs. recommended hours price.
        """
        if not price_data or not recommended_hours:
            return None
        
        # Get prices for recommended hours
        recommended_prices = [
            p['price'] for p in price_data 
            if p['hour'] in recommended_hours
        ]
        
        # Validate we have data before division
        if not recommended_prices:
            return None
        
        if not price_data:
            return None
        
        # Calculate average recommended price vs overall average
        avg_recommended = sum(recommended_prices) / len(recommended_prices)
        avg_overall = sum(p['price'] for p in price_data) / len(price_data)
        
        # Savings per kWh
        savings_per_kwh = avg_overall - avg_recommended
        
        return max(0, savings_per_kwh)  # Don't return negative savings
