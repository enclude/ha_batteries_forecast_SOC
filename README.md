# Battery SOC Forecast for Home Assistant

A Python application that reads battery State of Charge (SOC) data from Home Assistant and forecasts when the battery will reach a critical threshold based on historical trends.

## Features

- 📊 Reads sensor data from local Home Assistant API
- ⏱️ Configurable time window for historical data analysis (default: 90 minutes)
- 🔮 Linear regression-based trend analysis and forecasting
- ⚠️ Configurable SOC threshold for alerts (default: 5%)
- 📈 Calculates ETA (Estimated Time of Arrival) to threshold
- 🎯 Easy configuration via YAML file

## Requirements

- Python 3.7 or higher
- Home Assistant instance with API access
- Long-lived access token from Home Assistant

## Installation

1. Clone the repository:
```bash
git clone https://github.com/enclude/ha_batteries_forecast_SOC.git
cd ha_batteries_forecast_SOC
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create configuration file:
```bash
cp config.yaml.example config.yaml
```

4. Edit `config.yaml` with your Home Assistant details:
```yaml
home_assistant:
  url: "http://your-ha-instance:8123"
  token: "YOUR_LONG_LIVED_ACCESS_TOKEN"

sensor:
  name: "sensor.batteries_stan_pojemnosci"  # Your sensor entity ID

time:
  history_minutes: 90  # Historical data window

forecast:
  threshold_percent: 5  # Alert threshold
```

## Configuration

### Home Assistant Setup

1. Go to your Home Assistant profile
2. Scroll down to "Long-Lived Access Tokens"
3. Click "Create Token"
4. Copy the token and add it to `config.yaml`

### Sensor Configuration

The sensor name should be the full entity ID from Home Assistant (e.g., `sensor.batteries_stan_pojemnosci`). You can find this in:
- Home Assistant → Developer Tools → States
- Look for your battery sensor in the entity list

### Time Window

The `history_minutes` parameter determines how much historical data is used for trend analysis. Recommended values:
- **30-60 minutes**: For fast-changing batteries
- **90 minutes**: Default, good for most use cases
- **120-180 minutes**: For slow-draining batteries

### Threshold

The `threshold_percent` is the SOC level that triggers the forecast alert. Common values:
- **5%**: Default, critical battery level
- **10%**: Early warning
- **20%**: Conservative warning

## Usage

Run the forecast script:

```bash
python main.py
```

With verbose output:
```bash
python main.py --verbose
```

With custom configuration file:
```bash
python main.py --config /path/to/config.yaml
```

### Output

The script will display:
- Current SOC percentage
- Trend analysis (rate of change, correlation)
- Whether the battery is declining
- ETA to threshold (if declining)
- Time remaining until threshold

Example output:
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

### Exit Codes

- `0`: OK - Battery is stable or increasing
- `1`: Warning - Battery will reach threshold based on forecast
- `2`: Critical - Battery is already at or below threshold

## Example Integration

### Cron Job

Run forecast every 15 minutes:
```bash
*/15 * * * * cd /path/to/ha_batteries_forecast_SOC && /usr/bin/python3 main.py >> /var/log/battery_forecast.log 2>&1
```

### Home Assistant Automation

You can call this script from Home Assistant using a shell command sensor or automation.

## Troubleshooting

### "No historical data available"

- Check that the sensor name is correct in `config.yaml`
- Verify the sensor exists in Home Assistant
- Ensure the sensor has recorded data in the specified time window
- Check that Home Assistant is accessible at the configured URL

### "Failed to fetch sensor history"

- Verify the Home Assistant URL is correct
- Check that the access token is valid
- Ensure Home Assistant API is accessible from your network

### "Not enough data points for trend analysis"

- Increase the `history_minutes` value
- Wait for the sensor to record more data points
- Check if the sensor is updating regularly

## License

MIT License - See [LICENSE](LICENSE) file for details

## Author

Created by enclude

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.