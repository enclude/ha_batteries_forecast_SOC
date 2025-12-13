# Prognoza SOC Baterii dla Home Assistant

Aplikacja w Pythonie, która odczytuje dane o stanie naładowania baterii (SOC) z Home Assistant i prognozuje, kiedy bateria osiągnie krytyczny próg na podstawie historycznych trendów.

## Funkcje

- 📊 Odczytuje dane z czujnika z lokalnego API Home Assistant
- ⏱️ Konfigurowalny okres czasu do analizy danych historycznych (domyślnie: 90 minut)
- 🔮 Analiza trendów i prognozowanie oparte na regresji liniowej
- ⚠️ Konfigurowalny próg SOC dla alertów (domyślnie: 5%)
- 📈 Oblicza ETA (szacowany czas dotarcia) do progu
- 🎯 Łatwa konfiguracja za pomocą pliku YAML

## Wymagania

- Python 3.7 lub nowszy
- Instancja Home Assistant z dostępem do API
- Token długoterminowego dostępu z Home Assistant

## Instalacja

1. Sklonuj repozytorium:
```bash
git clone https://github.com/enclude/ha_batteries_forecast_SOC.git
cd ha_batteries_forecast_SOC
```

2. Zainstaluj zależności:
```bash
pip install -r requirements.txt
```

3. Utwórz plik konfiguracyjny:
```bash
cp config.yaml.example config.yaml
```

4. Edytuj `config.yaml` swoimi danymi Home Assistant:
```yaml
home_assistant:
  url: "http://your-ha-instance:8123"
  token: "YOUR_LONG_LIVED_ACCESS_TOKEN"

sensor:
  name: "sensor.batteries_stan_pojemnosci"  # ID twojego czujnika

time:
  history_minutes: 90  # Okres danych historycznych

forecast:
  threshold_percent: 5  # Próg alertu
```

## Konfiguracja

### Konfiguracja Home Assistant

1. Przejdź do swojego profilu Home Assistant
2. Przewiń w dół do "Long-Lived Access Tokens" (Tokeny długoterminowego dostępu)
3. Kliknij "Create Token" (Utwórz token)
4. Skopiuj token i dodaj go do `config.yaml`

### Konfiguracja czujnika

Nazwa czujnika powinna być pełnym ID encji z Home Assistant (np. `sensor.batteries_stan_pojemnosci`). Możesz to znaleźć w:
- Home Assistant → Developer Tools → States (Narzędzia programisty → Stany)
- Poszukaj swojego czujnika baterii na liście encji

### Okres czasu

Parametr `history_minutes` określa, ile danych historycznych jest używanych do analizy trendu. Zalecane wartości:
- **30-60 minut**: Dla szybko zmieniających się baterii
- **90 minut**: Domyślnie, dobre dla większości przypadków użycia
- **120-180 minut**: Dla wolno rozładowujących się baterii

### Próg

`threshold_percent` to poziom SOC, który wyzwala alert prognozy. Typowe wartości:
- **5%**: Domyślnie, krytyczny poziom baterii
- **10%**: Wczesne ostrzeżenie
- **20%**: Ostrzeżenie konserwatywne

## Użycie

Uruchom skrypt prognozy:

```bash
python main.py
```

Z szczegółowym wyjściem:
```bash
python main.py --verbose
```

Z własnym plikiem konfiguracyjnym:
```bash
python main.py --config /path/to/config.yaml
```

### Wynik

Skrypt wyświetli:
- Aktualny procent SOC
- Analiza trendu (tempo zmian, korelacja)
- Czy bateria się rozładowuje
- ETA do progu (jeśli się rozładowuje)
- Pozostały czas do progu

Przykładowe wyjście:
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

### Kody wyjścia

- `0`: OK - Bateria jest stabilna lub się ładuje
- `1`: Ostrzeżenie - Bateria osiągnie próg zgodnie z prognozą
- `2`: Krytyczne - Bateria jest już na progu lub poniżej

## Przykładowa integracja

### Zadanie Cron

Uruchamiaj prognozę co 15 minut:
```bash
*/15 * * * * cd /path/to/ha_batteries_forecast_SOC && /usr/bin/python3 main.py >> /var/log/battery_forecast.log 2>&1
```

### Automatyzacja Home Assistant

Możesz wywołać ten skrypt z Home Assistant używając czujnika poleceń powłoki lub automatyzacji.

## Rozwiązywanie problemów

### "No historical data available" (Brak dostępnych danych historycznych)

- Sprawdź, czy nazwa czujnika jest poprawna w `config.yaml`
- Zweryfikuj, czy czujnik istnieje w Home Assistant
- Upewnij się, że czujnik zapisał dane w określonym przedziale czasu
- Sprawdź, czy Home Assistant jest dostępny pod skonfigurowanym adresem URL

### "Failed to fetch sensor history" (Nie udało się pobrać historii czujnika)

- Zweryfikuj, czy adres URL Home Assistant jest poprawny
- Sprawdź, czy token dostępu jest prawidłowy
- Upewnij się, że API Home Assistant jest dostępne z twojej sieci

### "Not enough data points for trend analysis" (Za mało punktów danych do analizy trendu)

- Zwiększ wartość `history_minutes`
- Poczekaj, aż czujnik zapisze więcej punktów danych
- Sprawdź, czy czujnik regularnie się aktualizuje

## Licencja

Licencja MIT - Zobacz plik [LICENSE](LICENSE) dla szczegółów

## Autor

Utworzone przez enclude

## Współpraca

Wkład jest mile widziany! Śmiało przesyłaj Pull Request.