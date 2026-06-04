# Twelve Data Setup

## Purpose

Twelve Data is the current Stage 0 data provider for XAUUSD research.

It is not a broker feed. It is a data provider. Therefore, Stage 0 can test candles and baseline feasibility, but final execution realism must later be validated with an MT5/broker feed.

## Key definitions

- API key: a private token that lets our code access the data service.
- Endpoint: a specific API path, such as `/time_series`.
- Query string: URL parameters such as `symbol`, `interval`, `outputsize`, and `apikey`.
- OHLCV: open, high, low, close, volume.
- Spread: ask minus bid. Twelve Data Stage 0 pipeline does not give broker spread, so costs must be assumed conservatively.

## How to get the key

1. Open Twelve Data registration page.
2. Create an account using email/password, Google, or Apple.
3. Log in.
4. Open your dashboard.
5. Copy the API key.
6. Never paste it into Git or any project file.

## Local setup

Run this in terminal:

```bash
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
```

Then smoke test:

```bash
cd ~/Desktop/xauusd-trader
python3 -m pip install -r requirements.txt
python3 -m app.xauusd_collect --interval 1min --outputsize 100
python3 -m app.xauusd_normalize
python3 -m app.xauusd_data_quality
```

## GitHub setup

Add this repository secret:

```text
TWELVEDATA_API_KEY
```

Then run workflow manually:

```text
XAUUSD Stage 0 Twelve Data Check
```

## Strict warning

Do not buy a paid plan before the free/basic access confirms that `XAU/USD` and the required intervals work for our project.
