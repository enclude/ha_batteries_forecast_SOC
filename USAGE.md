# Quick Start Guide

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create configuration:**
   ```bash
   cp config.yaml.example config.yaml
   ```

3. **Edit configuration:**
   - Set your Home Assistant URL
   - Add your long-lived access token
   - Configure sensor name (default: `sensor.batteries_stan_pojemnosci`)
   - Configure solar production sensors
   - Enable charging optimization (optional)
   - Add OpenAI API key for AI recommendations (optional)
   - Adjust time window and threshold as needed

## Usage

### Basic usage (forecast + charging optimization):
```bash
python main.py
```

### With verbose output:
```bash
python main.py --verbose
```

### Forecast only (skip charging optimization):
```bash
python main.py --forecast-only
```

### With custom config file:
```bash
python main.py --config /path/to/config.yaml
```

## Configuration Options

### Sensor Name
Change the sensor entity ID to match your Home Assistant sensor:
```yaml
sensor:
  name: "sensor.your_battery_sensor_name"
```

### Solar Sensors
Configure solar production forecast sensors:
```yaml
solar_sensors:
  - "sensor.energy_production_today"
  - "sensor.energy_production_today_2"
  - "sensor.energy_production_today_3"
  - "sensor.energy_production_today_4"
```

### Time Window
Adjust how much historical data to analyze (in minutes):
```yaml
time:
  history_minutes: 90  # 30-180 minutes recommended
```

### Threshold
Set the SOC percentage that triggers the alert:
```yaml
forecast:
  threshold_percent: 5  # 5-20% typical values
```

### Charging Optimization
Enable and configure charging optimization:
```yaml
charging:
  enabled: true  # true/false
  hours_needed: 4  # hours needed for full charge
```

### OpenAI Integration (Optional)
Add OpenAI API key for AI-powered recommendations:
```yaml
openai:
  api_key: "sk-..."  # Leave empty to use rule-based system
```

## Testing

Run the test suite to verify installation:
```bash
# Test battery forecasting
python test_forecast.py

# Test charging optimization
python test_charging_optimizer.py
```

## Exit Codes

- **0**: Battery is stable or increasing (OK)
- **1**: Battery will reach threshold (WARNING)
- **2**: Battery is already below threshold (CRITICAL)

## Example Output

### Forecast Only
```
============================================================
Battery SOC Forecast
============================================================
Current SOC: 45.30%
Threshold: 5%

Trend Analysis:
  Rate of change: -2.5000% per hour
  Correlation (R): -0.9850
  Declining: Yes

Forecast:
  ETA to 5%: 2025-12-14 13:45:30
  Time remaining: 16 hours 15 minutes
============================================================
```

### With Charging Optimization
```
============================================================
Battery SOC Forecast
============================================================
Current SOC: 45.30%
Threshold: 5%

Trend Analysis:
  Rate of change: -2.5000% per hour
  Correlation (R): -0.9850
  Declining: Yes

Forecast:
  ETA to 5%: 2025-12-14 13:45:30
  Time remaining: 16 hours 15 minutes
============================================================

============================================================
Battery Charging Recommendation
============================================================
✓ Charging RECOMMENDED (Priority: MEDIUM)
  Recommended window: 02:00 - 05:00
  Hours: 02:00, 03:00, 04:00, 05:00

Reasoning:
  Battery forecast shows decline reaching threshold in 16.3 hours | 
  Low solar forecast: 3.5 kWh expected | 
  Cheapest charging window: 02:00-05:00 at avg 0.4823 PLN/kWh

Solar Production Forecast:
  Total expected: 3.50 kWh

Electricity Price Analysis:
  Cheapest 4h window: 02:00 - 05:00
  Average price: 0.4823 PLN/kWh
============================================================
```

## Troubleshooting

### "Configuration file not found"
- Make sure `config.yaml` exists
- Copy from `config.yaml.example` if needed

### "No historical data available"
- Check sensor name is correct
- Verify sensor has data in the time window
- Ensure Home Assistant is accessible

### "Failed to fetch sensor history"
- Verify Home Assistant URL is correct
- Check access token is valid
- Ensure network connectivity

## Automation

### Cron Job (Linux/Mac)
```bash
# Run every 15 minutes
*/15 * * * * cd /path/to/ha_batteries_forecast_SOC && python main.py >> /var/log/battery_forecast.log 2>&1
```

### Scheduled Task (Windows)
Use Task Scheduler to run `python main.py` at desired intervals.

### Home Assistant Shell Command
```yaml
shell_command:
  battery_forecast: "python /path/to/ha_batteries_forecast_SOC/main.py"
```

Then call from automation:
```yaml
automation:
  - alias: "Battery Forecast Check"
    trigger:
      - platform: time_pattern
        minutes: "/15"
    action:
      - service: shell_command.battery_forecast
```
