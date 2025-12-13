"""Forecast module for predicting battery SOC."""
import numpy as np
from datetime import datetime, timedelta
from scipy import stats


class BatteryForecast:
    """Battery State of Charge (SOC) forecaster."""
    
    def __init__(self, threshold_percent=5):
        """Initialize battery forecast.
        
        Args:
            threshold_percent: SOC threshold percentage for alert
        """
        self.threshold_percent = threshold_percent
    
    def calculate_trend(self, history_data):
        """Calculate trend from historical data using linear regression.
        
        Args:
            history_data: List of tuples (timestamp, value)
        
        Returns:
            dict: Dictionary containing trend information:
                - slope: Rate of change (% per second)
                - intercept: Y-intercept
                - r_value: Correlation coefficient
                - std_err: Standard error
        """
        if len(history_data) < 2:
            raise ValueError("Not enough data points for trend analysis (minimum 2 required)")
        
        # Convert timestamps to seconds since first measurement
        first_time = history_data[0][0]
        x_data = np.array([(ts - first_time).total_seconds() for ts, _ in history_data])
        y_data = np.array([value for _, value in history_data])
        
        # Perform linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(x_data, y_data)
        
        return {
            'slope': slope,
            'intercept': intercept,
            'r_value': r_value,
            'p_value': p_value,
            'std_err': std_err,
            'first_time': first_time
        }
    
    def forecast_threshold_time(self, history_data):
        """Forecast when SOC will drop below threshold.
        
        Args:
            history_data: List of tuples (timestamp, value)
        
        Returns:
            dict: Forecast information containing:
                - eta: Estimated time when threshold will be reached (datetime or None)
                - current_soc: Current SOC percentage
                - threshold: Threshold percentage
                - trend: Trend information
                - time_to_threshold: Time delta to threshold (timedelta or None)
                - is_declining: Whether SOC is declining
        """
        if not history_data:
            raise ValueError("No historical data available")
        
        # Get current SOC (last data point)
        current_time, current_soc = history_data[-1]
        
        # Calculate trend
        trend = self.calculate_trend(history_data)
        
        # Check if battery is declining
        is_declining = trend['slope'] < 0
        
        # Initialize result
        result = {
            'current_soc': current_soc,
            'threshold': self.threshold_percent,
            'trend': trend,
            'is_declining': is_declining,
            'eta': None,
            'time_to_threshold': None
        }
        
        # If SOC is already below threshold
        if current_soc <= self.threshold_percent:
            result['eta'] = current_time
            result['time_to_threshold'] = timedelta(0)
            return result
        
        # If battery is not declining, no threshold crossing expected
        if not is_declining:
            return result
        
        # Calculate time when SOC will reach threshold
        # Using linear equation: y = mx + b
        # Solve for x when y = threshold: x = (threshold - b) / m
        time_offset_from_start = (current_time - trend['first_time']).total_seconds()
        current_intercept = current_soc - (trend['slope'] * time_offset_from_start)
        
        # Calculate seconds until threshold from current time
        seconds_to_threshold = (self.threshold_percent - current_soc) / trend['slope']
        
        # Calculate ETA
        eta = current_time + timedelta(seconds=seconds_to_threshold)
        time_to_threshold = timedelta(seconds=seconds_to_threshold)
        
        result['eta'] = eta
        result['time_to_threshold'] = time_to_threshold
        
        return result
    
    def format_forecast_result(self, forecast_result):
        """Format forecast result as human-readable string.
        
        Args:
            forecast_result: Result from forecast_threshold_time()
        
        Returns:
            str: Formatted forecast information
        """
        lines = []
        lines.append("=" * 60)
        lines.append("Battery SOC Forecast")
        lines.append("=" * 60)
        
        lines.append(f"Current SOC: {forecast_result['current_soc']:.2f}%")
        lines.append(f"Threshold: {forecast_result['threshold']}%")
        
        trend = forecast_result['trend']
        lines.append(f"\nTrend Analysis:")
        lines.append(f"  Rate of change: {trend['slope'] * 3600:.4f}% per hour")
        lines.append(f"  Correlation (R): {trend['r_value']:.4f}")
        lines.append(f"  Declining: {'Yes' if forecast_result['is_declining'] else 'No'}")
        
        if forecast_result['current_soc'] <= forecast_result['threshold']:
            lines.append(f"\n⚠️  WARNING: SOC is already at or below threshold!")
        elif forecast_result['eta']:
            lines.append(f"\nForecast:")
            lines.append(f"  ETA to {forecast_result['threshold']}%: {forecast_result['eta'].strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Format time to threshold
            time_delta = forecast_result['time_to_threshold']
            hours = time_delta.total_seconds() // 3600
            minutes = (time_delta.total_seconds() % 3600) // 60
            
            if hours > 0:
                lines.append(f"  Time remaining: {int(hours)} hours {int(minutes)} minutes")
            else:
                lines.append(f"  Time remaining: {int(minutes)} minutes")
        else:
            lines.append(f"\n✓ SOC is stable or increasing - no threshold crossing expected")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
