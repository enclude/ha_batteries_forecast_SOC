"""OpenAI API client for intelligent charging recommendations."""
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAIChargingAdvisor:
    """OpenAI-powered charging advisor for battery optimization."""
    
    def __init__(self, api_key):
        """Initialize OpenAI API client.
        
        Args:
            api_key: OpenAI API key
        """
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"  # Cost-effective model for this task
    
    def analyze_charging_strategy(self, forecast_data, price_data, solar_forecast):
        """Analyze data and recommend optimal charging strategy.
        
        Args:
            forecast_data: Battery SOC forecast data (dict from BatteryForecast)
            price_data: Electricity price data from pstryk.pl (list of dicts)
            solar_forecast: Solar production forecast data (dict with production values)
        
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
            context = self._build_context(forecast_data, price_data, solar_forecast)
            
            # Create system prompt
            system_prompt = """You are an expert energy management advisor for home battery systems.
Your task is to analyze battery state of charge forecasts, electricity prices, and solar production
forecasts to recommend optimal charging times from the grid.

Consider:
1. Battery discharge rate and forecast SOC levels
2. Hourly electricity prices
3. Expected solar production
4. Balance between cost savings and ensuring adequate battery charge

Provide practical, cost-effective recommendations."""

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

Solar Production Forecast (kWh):
{self._format_solar_forecast(solar_forecast)}

Based on this data:
1. Should the battery be charged from the grid?
2. What are the optimal hours to charge (provide specific hours 0-23)?
3. Explain your reasoning considering cost, SOC forecast, and solar production.
4. What's the priority level (high/medium/low)?

Respond in JSON format:
{{
    "should_charge": true/false,
    "recommended_hours": [list of hours],
    "reasoning": "explanation",
    "priority": "high/medium/low"
}}"""

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
    
    def _build_context(self, forecast_data, price_data, solar_forecast):
        """Build context string from input data."""
        return {
            'forecast': forecast_data,
            'prices': price_data,
            'solar': solar_forecast
        }
    
    def _format_prices(self, price_data):
        """Format price data for prompt."""
        if not price_data:
            return "No price data available"
        
        lines = []
        for price in price_data[:24]:  # Show up to 24 hours
            lines.append(f"  {price['hour']:02d}:00 - {price['price']:.4f} PLN/kWh")
        return "\n".join(lines)
    
    def _format_solar_forecast(self, solar_forecast):
        """Format solar forecast data for prompt."""
        if not solar_forecast:
            return "No solar forecast available"
        
        lines = []
        for key, value in solar_forecast.items():
            lines.append(f"  {key}: {value:.2f} kWh")
        return "\n".join(lines)
    
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
        
        if not recommended_prices:
            return None
        
        # Calculate average recommended price vs overall average
        avg_recommended = sum(recommended_prices) / len(recommended_prices)
        avg_overall = sum(p['price'] for p in price_data) / len(price_data)
        
        # Savings per kWh
        savings_per_kwh = avg_overall - avg_recommended
        
        return max(0, savings_per_kwh)  # Don't return negative savings
