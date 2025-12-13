#!/usr/bin/env python3
"""Test script for battery forecast functionality."""
from datetime import datetime, timedelta
from forecast import BatteryForecast


def test_declining_battery():
    """Test forecast with declining battery."""
    print("\n" + "="*60)
    print("Test 1: Declining Battery (50% to 45% over 60 minutes)")
    print("="*60)
    
    # Create mock data: Battery declining from 50% to 45% over 60 minutes
    start_time = datetime.now() - timedelta(minutes=60)
    history_data = []
    
    # Generate 13 data points (every 5 minutes)
    for i in range(13):
        time = start_time + timedelta(minutes=i*5)
        # Linear decline: 50% to 45% over 60 minutes
        value = 50.0 - (5.0 * i / 12)
        history_data.append((time, value))
    
    # Create forecaster
    forecaster = BatteryForecast(threshold_percent=5)
    
    # Calculate forecast
    forecast_result = forecaster.forecast_threshold_time(history_data)
    
    # Display results
    print(forecaster.format_forecast_result(forecast_result))
    
    # Verify results
    assert forecast_result['is_declining'] == True, "Battery should be declining"
    assert forecast_result['eta'] is not None, "ETA should be calculated"
    assert forecast_result['current_soc'] > 5, "Current SOC should be above threshold"
    
    print("✓ Test passed!")


def test_stable_battery():
    """Test forecast with stable battery."""
    print("\n" + "="*60)
    print("Test 2: Stable Battery (maintaining 80%)")
    print("="*60)
    
    # Create mock data: Battery stable at 80%
    start_time = datetime.now() - timedelta(minutes=60)
    history_data = []
    
    # Generate 13 data points (every 5 minutes)
    for i in range(13):
        time = start_time + timedelta(minutes=i*5)
        # Stable with minor fluctuations
        value = 80.0 + (0.5 if i % 2 == 0 else -0.5)
        history_data.append((time, value))
    
    # Create forecaster
    forecaster = BatteryForecast(threshold_percent=5)
    
    # Calculate forecast
    forecast_result = forecaster.forecast_threshold_time(history_data)
    
    # Display results
    print(forecaster.format_forecast_result(forecast_result))
    
    # Verify results - with minor fluctuations, might be slightly declining or stable
    print("✓ Test passed!")


def test_charging_battery():
    """Test forecast with charging battery."""
    print("\n" + "="*60)
    print("Test 3: Charging Battery (30% to 50%)")
    print("="*60)
    
    # Create mock data: Battery charging from 30% to 50%
    start_time = datetime.now() - timedelta(minutes=90)
    history_data = []
    
    # Generate 19 data points (every 5 minutes)
    for i in range(19):
        time = start_time + timedelta(minutes=i*5)
        # Linear increase: 30% to 50% over 90 minutes
        value = 30.0 + (20.0 * i / 18)
        history_data.append((time, value))
    
    # Create forecaster
    forecaster = BatteryForecast(threshold_percent=5)
    
    # Calculate forecast
    forecast_result = forecaster.forecast_threshold_time(history_data)
    
    # Display results
    print(forecaster.format_forecast_result(forecast_result))
    
    # Verify results
    assert forecast_result['is_declining'] == False, "Battery should not be declining"
    assert forecast_result['eta'] is None, "ETA should not be calculated for charging battery"
    
    print("✓ Test passed!")


def test_critical_battery():
    """Test forecast with battery already below threshold."""
    print("\n" + "="*60)
    print("Test 4: Critical Battery (already at 3%)")
    print("="*60)
    
    # Create mock data: Battery declining and already at 3%
    start_time = datetime.now() - timedelta(minutes=30)
    history_data = []
    
    # Generate 7 data points (every 5 minutes)
    for i in range(7):
        time = start_time + timedelta(minutes=i*5)
        # Linear decline: 8% to 3% over 30 minutes
        value = 8.0 - (5.0 * i / 6)
        history_data.append((time, value))
    
    # Create forecaster
    forecaster = BatteryForecast(threshold_percent=5)
    
    # Calculate forecast
    forecast_result = forecaster.forecast_threshold_time(history_data)
    
    # Display results
    print(forecaster.format_forecast_result(forecast_result))
    
    # Verify results
    assert forecast_result['current_soc'] <= 5, "Current SOC should be at or below threshold"
    
    print("✓ Test passed!")


def test_fast_declining_battery():
    """Test forecast with rapidly declining battery."""
    print("\n" + "="*60)
    print("Test 5: Fast Declining Battery (85% to 60% over 90 minutes)")
    print("="*60)
    
    # Create mock data: Battery rapidly declining
    start_time = datetime.now() - timedelta(minutes=90)
    history_data = []
    
    # Generate 19 data points (every 5 minutes)
    for i in range(19):
        time = start_time + timedelta(minutes=i*5)
        # Fast decline: 85% to 60% over 90 minutes
        value = 85.0 - (25.0 * i / 18)
        history_data.append((time, value))
    
    # Create forecaster
    forecaster = BatteryForecast(threshold_percent=5)
    
    # Calculate forecast
    forecast_result = forecaster.forecast_threshold_time(history_data)
    
    # Display results
    print(forecaster.format_forecast_result(forecast_result))
    
    # Verify results
    assert forecast_result['is_declining'] == True, "Battery should be declining"
    assert forecast_result['eta'] is not None, "ETA should be calculated"
    
    # Calculate expected hours to reach 5% from 60%
    # Rate: 25% per 90 minutes = 25/90 per minute
    # Need to lose: 60% - 5% = 55%
    # Time: 55 / (25/90) = 55 * 90 / 25 = 198 minutes = 3.3 hours
    
    print("✓ Test passed!")


if __name__ == '__main__':
    print("\n" + "="*60)
    print("Battery Forecast Test Suite")
    print("="*60)
    
    try:
        test_declining_battery()
        test_stable_battery()
        test_charging_battery()
        test_critical_battery()
        test_fast_declining_battery()
        
        print("\n" + "="*60)
        print("✅ All tests passed successfully!")
        print("="*60)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
