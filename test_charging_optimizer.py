#!/usr/bin/env python3
"""Test script for charging optimizer functionality."""
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock
from forecast import BatteryForecast
from charging_optimizer import ChargingOptimizer
from pstryk_api_client import PstrykApiClient


# Test configuration constants
SOC_CHANGE_RANGE = 10.0  # SOC change range for test data
DATA_POINTS = 19  # Number of data points in test history
TEST_INTERVAL_MINUTES = 5  # Interval between test data points


def create_mock_forecast_data(soc=50.0, declining=True):
    """Create mock forecast data for testing."""
    forecaster = BatteryForecast(threshold_percent=5)
    
    # Create declining or charging battery data
    start_time = datetime.now() - timedelta(minutes=90)
    history_data = []
    for i in range(DATA_POINTS):
        time = start_time + timedelta(minutes=i * TEST_INTERVAL_MINUTES)
        # Calculate value based on whether battery is declining or charging
        if declining:
            value = soc - (SOC_CHANGE_RANGE * i / (DATA_POINTS - 1))
        else:
            value = soc + (SOC_CHANGE_RANGE * i / (DATA_POINTS - 1))
        history_data.append((time, value))
    
    return forecaster.forecast_threshold_time(history_data)


def create_mock_price_data():
    """Create mock electricity price data."""
    today = datetime.now().date()
    prices = []
    for hour in range(24):
        # Simulate varying prices - cheaper at night
        if 2 <= hour <= 5:
            price = 0.50  # Cheap night rates
        elif 6 <= hour <= 9:
            price = 0.75  # Morning increase
        elif 10 <= hour <= 20:
            price = 0.85  # Day rates
        else:
            price = 0.70  # Evening
        
        prices.append({
            'hour': hour,
            'price': price,
            'timestamp': datetime.combine(today, datetime.min.time()).replace(hour=hour)
        })
    return prices


def create_mock_cheapest_window():
    """Create mock cheapest window data."""
    return {
        'start_hour': 2,
        'end_hour': 5,
        'hours': 4,
        'avg_price': 0.50,
        'total_cost_per_kwh': 2.00,
        'timestamps': []
    }


def test_optimizer_initialization():
    """Test charging optimizer initialization."""
    print("\n" + "="*60)
    print("Test 1: Optimizer Initialization")
    print("="*60)
    
    # Create mocks
    ha_client = Mock()
    pstryk_client = Mock()
    
    optimizer = ChargingOptimizer(ha_client, pstryk_client, None)
    
    assert optimizer.ha_client is not None
    assert optimizer.pstryk_client is not None
    assert optimizer.openai_advisor is None
    
    print("✓ Optimizer initialized successfully")


def test_solar_forecast_fetching():
    """Test solar forecast data fetching."""
    print("\n" + "="*60)
    print("Test 2: Solar Forecast Fetching")
    print("="*60)
    
    # Create mock HA client
    ha_client = Mock()
    ha_client.get_current_state = Mock(side_effect=[10.5, 8.3, 9.1, 7.2])
    
    pstryk_client = Mock()
    optimizer = ChargingOptimizer(ha_client, pstryk_client, None)
    
    solar_sensors = [
        'sensor.energy_production_today',
        'sensor.energy_production_today_2',
        'sensor.energy_production_today_3',
        'sensor.energy_production_today_4'
    ]
    
    solar_data = optimizer.get_solar_forecast(solar_sensors)
    
    assert len(solar_data) == 4
    assert solar_data['sensor.energy_production_today'] == 10.5
    
    total = optimizer.calculate_total_solar_forecast(solar_data)
    assert total == 35.1
    
    print(f"  Total solar forecast: {total} kWh")
    print("✓ Solar forecast fetching works correctly")


def test_rule_based_recommendation_critical_battery():
    """Test rule-based recommendation with critical battery."""
    print("\n" + "="*60)
    print("Test 3: Rule-Based Recommendation - Critical Battery")
    print("="*60)
    
    # Create mocks
    ha_client = Mock()
    pstryk_client = Mock()
    optimizer = ChargingOptimizer(ha_client, pstryk_client, None)
    
    # Critical battery forecast (8% SOC)
    forecast_data = create_mock_forecast_data(soc=8.0, declining=True)
    cheapest_window = create_mock_cheapest_window()
    cheapest_periods = [cheapest_window]
    total_solar = 5.0
    
    recommendation = optimizer._rule_based_recommendation(
        forecast_data,
        cheapest_periods,
        total_solar
    )
    
    print(f"  Should charge: {recommendation['should_charge']}")
    print(f"  Priority: {recommendation['priority']}")
    print(f"  Reasoning: {recommendation['reasoning']}")
    
    assert recommendation['should_charge'] == True
    assert recommendation['priority'] == 'high'
    assert len(recommendation['recommended_hours']) > 0
    
    print("✓ Critical battery correctly triggers charging recommendation")


def test_rule_based_recommendation_healthy_battery():
    """Test rule-based recommendation with healthy battery."""
    print("\n" + "="*60)
    print("Test 4: Rule-Based Recommendation - Healthy Battery")
    print("="*60)
    
    # Create mocks
    ha_client = Mock()
    pstryk_client = Mock()
    optimizer = ChargingOptimizer(ha_client, pstryk_client, None)
    
    # Healthy battery forecast (80% SOC, not declining)
    forecast_data = create_mock_forecast_data(soc=80.0, declining=False)
    cheapest_window = create_mock_cheapest_window()
    cheapest_periods = [cheapest_window]
    total_solar = 25.0  # Good solar forecast
    
    recommendation = optimizer._rule_based_recommendation(
        forecast_data,
        cheapest_periods,
        total_solar
    )
    
    print(f"  Should charge: {recommendation['should_charge']}")
    print(f"  Priority: {recommendation['priority']}")
    print(f"  Reasoning: {recommendation['reasoning']}")
    
    assert recommendation['should_charge'] == False
    
    print("✓ Healthy battery correctly does not trigger charging")


def test_cheapest_hours_calculation():
    """Test pstryk.pl cheapest hours calculation."""
    print("\n" + "="*60)
    print("Test 5: Cheapest Hours Calculation")
    print("="*60)
    
    client = PstrykApiClient()
    
    # Create mock price data
    prices = create_mock_price_data()
    
    # Mock the get_electricity_prices method
    client.get_electricity_prices = Mock(return_value=prices)
    
    # Get cheapest 4-hour window
    cheapest = client.get_cheapest_hours(hours_needed=4)
    
    print(f"  Cheapest window: {cheapest['start_hour']:02d}:00 - {cheapest['end_hour']:02d}:00")
    print(f"  Average price: {cheapest['avg_price']:.4f} PLN/kWh")
    print(f"  Number of hours: {cheapest['hours']}")
    
    assert cheapest is not None
    assert cheapest['hours'] == 4
    assert cheapest['start_hour'] is not None
    assert cheapest['end_hour'] is not None
    assert cheapest['avg_price'] > 0
    
    # Should be in the cheap night period (2-5)
    assert cheapest['start_hour'] == 2
    assert cheapest['end_hour'] == 5
    
    print("✓ Cheapest hours calculation works correctly")


def test_format_recommendation():
    """Test recommendation formatting."""
    print("\n" + "="*60)
    print("Test 6: Recommendation Formatting")
    print("="*60)
    
    # Create mocks
    ha_client = Mock()
    pstryk_client = Mock()
    optimizer = ChargingOptimizer(ha_client, pstryk_client, None)
    
    # Create sample recommendation
    recommendation = {
        'should_charge': True,
        'recommended_hours': [2, 3, 4, 5],
        'charging_periods': [create_mock_cheapest_window()],
        'hours_needed': 4,
        'start_hour': 2,
        'end_hour': 5,
        'reasoning': 'Battery is critically low | Cheapest rates at night',
        'priority': 'high',
        'price_analysis': {
            'cheapest_window': create_mock_cheapest_window(),
            'cheapest_periods': [create_mock_cheapest_window()],
            'prices': create_mock_price_data()
        },
        'solar_forecast': {
            'sensors': {
                'sensor.energy_production_today': 10.5,
                'sensor.energy_production_today_2': 8.3
            },
            'total_expected': 18.8
        },
        'ai_recommendation': None,
        'battery_info': {
            'capacity_kwh': 10,
            'max_charging_power_kw': 5,
            'current_soc': 8.0,
            'target_soc': 100
        }
    }
    
    formatted = optimizer.format_recommendation(recommendation)
    
    print("\n" + formatted)
    
    assert "Charging RECOMMENDED" in formatted
    assert "02:00 - 05:00" in formatted
    assert "HIGH" in formatted
    
    print("\n✓ Recommendation formatting works correctly")


def test_optimization_with_low_solar():
    """Test optimization decision with low solar forecast."""
    print("\n" + "="*60)
    print("Test 7: Optimization with Low Solar Forecast")
    print("="*60)
    
    # Create mocks
    ha_client = Mock()
    ha_client.get_current_state = Mock(side_effect=[1.0, 0.5, 0.8, 0.3])
    
    pstryk_client = Mock()
    pstryk_client.get_electricity_prices = Mock(return_value=create_mock_price_data())
    cheapest_window = create_mock_cheapest_window()
    pstryk_client.get_cheapest_hours = Mock(return_value=cheapest_window)
    pstryk_client.get_cheapest_hours_multiple_periods = Mock(return_value=[cheapest_window])
    
    optimizer = ChargingOptimizer(ha_client, pstryk_client, None)
    
    # Medium battery but low solar
    forecast_data = create_mock_forecast_data(soc=25.0, declining=True)
    solar_sensors = [
        'sensor.energy_production_today',
        'sensor.energy_production_today_2',
        'sensor.energy_production_today_3',
        'sensor.energy_production_today_4'
    ]
    
    # Use new parameters: battery_capacity_kwh, max_charging_power_kw, allow_multiple_periods
    recommendation = optimizer.optimize_charging(forecast_data, solar_sensors, 10, 5, True)
    
    print(f"  Should charge: {recommendation['should_charge']}")
    print(f"  Solar forecast: {recommendation['solar_forecast']['total_expected']} kWh")
    print(f"  Reasoning: {recommendation['reasoning']}")
    
    # With low solar (2.6 kWh) and declining battery at 25%, should recommend charging
    assert recommendation['should_charge'] == True
    assert recommendation['solar_forecast']['total_expected'] < 5.0
    
    print("✓ Low solar forecast correctly influences charging decision")


def test_multiple_charging_periods():
    """Test multiple non-consecutive charging periods."""
    print("\n" + "="*60)
    print("Test 8: Multiple Charging Periods")
    print("="*60)
    
    client = PstrykApiClient()
    
    # Create mock price data
    prices = create_mock_price_data()
    
    # Mock the get_electricity_prices method
    client.get_electricity_prices = Mock(return_value=prices)
    
    # Get cheapest 6 hours which should result in multiple periods
    periods = client.get_cheapest_hours_multiple_periods(total_hours_needed=6)
    
    print(f"  Number of periods: {len(periods)}")
    print(f"  Total hours: {sum(p['hours'] for p in periods)}")
    for i, period in enumerate(periods, 1):
        print(f"  Period {i}: {period['start_hour']:02d}:00 - {period['end_hour']:02d}:00 ({period['hours']}h at {period['avg_price']:.4f} PLN/kWh)")
    
    assert len(periods) > 0
    assert sum(p['hours'] for p in periods) == 6
    
    print("✓ Multiple charging periods calculation works correctly")


def test_charging_hours_calculation():
    """Test calculation of charging hours needed."""
    print("\n" + "="*60)
    print("Test 9: Charging Hours Calculation")
    print("="*60)
    
    ha_client = Mock()
    pstryk_client = Mock()
    optimizer = ChargingOptimizer(ha_client, pstryk_client, None)
    
    # Test case 1: 50% SOC, 10kWh battery, 5kW charging
    hours = optimizer.calculate_charging_hours_needed(50, 100, 10, 5)
    print(f"  50% -> 100% with 10kWh battery and 5kW charging: {hours}h")
    assert hours == 1  # (50% * 10kWh) / 5kW = 1h
    
    # Test case 2: 20% SOC, 10kWh battery, 5kW charging
    hours = optimizer.calculate_charging_hours_needed(20, 100, 10, 5)
    print(f"  20% -> 100% with 10kWh battery and 5kW charging: {hours}h")
    assert hours == 2  # (80% * 10kWh) / 5kW = 1.6h, rounded up to 2h
    
    # Test case 3: Already at 100%
    hours = optimizer.calculate_charging_hours_needed(100, 100, 10, 5)
    print(f"  100% -> 100%: {hours}h (no charging needed)")
    assert hours == 0
    
    print("✓ Charging hours calculation works correctly")


if __name__ == '__main__':
    print("\n" + "="*60)
    print("Charging Optimizer Test Suite")
    print("="*60)
    
    try:
        test_optimizer_initialization()
        test_solar_forecast_fetching()
        test_rule_based_recommendation_critical_battery()
        test_rule_based_recommendation_healthy_battery()
        test_cheapest_hours_calculation()
        test_format_recommendation()
        test_optimization_with_low_solar()
        test_multiple_charging_periods()
        test_charging_hours_calculation()
        
        print("\n" + "="*60)
        print("✅ All charging optimizer tests passed successfully!")
        print("="*60)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
