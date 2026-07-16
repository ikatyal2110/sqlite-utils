# Stock Chart Analysis Telegram Bot

A Python Telegram bot that performs automated technical analysis on stock tickers. I built it so that getting a technical read on a stock is as easy as sending a message: send a ticker symbol (e.g. `TSLA`) and get back a candlestick chart with Fibonacci retracement/extension levels, swing points, a projected continuation path, and a short text summary of the setup — no charting software or manual level-drawing required.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)

## Key features

- **Market data**: fetches recent historical OHLCV data via `yfinance`.
- **Swing detection**: identifies significant swing highs and swing lows.
- **Fibonacci analysis**: retracement levels (0.382, 0.5, 0.618) and extension targets (1.272, 1.618), computed deterministically from detected swings — not machine-learned.
- **Trend projection**: a projected continuation path based on the detected trend.
- **Chart rendering**: a light-themed candlestick chart with all levels and projections overlaid.
- **Text summary**: a short analysis describing the setup and likely scenarios.
- **Configurable lookback**: append a period to the ticker (`TSLA 6m`, `AAPL 1y`, `MSFT 5y`) — supports `1d` through `max`, with a default set via `.env`.

## Screenshot / Demo

<!-- VERIFY / TODO(owner): This is the single highest-value addition for this repo — a bot is invisible until you see the conversation. Capture a screenshot of an actual Telegram chat: the user sending a ticker like `TSLA` or `TSLA 6m`, and the bot's reply showing the rendered candlestick chart (with Fibonacci levels and swing points visible) plus the text analysis summary underneath. Embed it here as the first thing after this section header. -->

## Project structure

```
stock-charts/
├── config.py              # Configuration from env
├── main.py                # Entry point
├── requirements.txt
├── .env.example
├── Procfile                # Railway process definition
├── railway.toml             # Railway deployment config
├── runtime.txt
├── charts_output/         # Temporary chart images (auto-created)
└── src/
    ├── bot/               # Telegram bot interface
    ├── data/              # Market data retrieval
    ├── analysis/          # Swing detection, Fibonacci, trend projection
    ├── chart/             # Chart rendering
    └── report/            # Text analysis generator
```

## Setup

**Requirements:** Python 3.9+

```bash
# 1. Create a virtual environment
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
```

**3. Configure the Telegram bot token**

1. Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, and follow the prompts to get a token.
2. Copy the env template and fill in the token:
   ```bash
   cp .env.example .env
   ```
   ```
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHI...
   ```
   Optional: set `CHART_PERIOD=1y` (or `6mo`, `5y`, etc.) as the default lookback when a user doesn't specify one.

**4. Run the bot**
```bash
python main.py
```

Then open your bot in Telegram and send a ticker symbol (e.g. `TSLA`, `AAPL`).

## Usage

- Send a stock ticker (e.g. `TSLA`, `AAPL`, `MSFT`) for a **1-year** chart by default.
- Add a period after the ticker for a custom window: `TSLA 6m`, `AAPL 1y`, `MSFT 5y`. Supported: `1d`, `5d`, `1m`, `3m`, `6m`, `1y`, `2y`, `5y`, `10y`, `ytd`, `max`.
- Invalid or unknown tickers return an error message.

## Deploy to Railway (24/7 hosting)

The bot is set up for [Railway](https://railway.app):

1. Push this repo to GitHub.
2. On [railway.app](https://railway.app), sign in with GitHub, **New Project** → **Deploy from GitHub repo** → select this repo.
3. Railway detects Python and builds from `requirements.txt`.
4. Under your service → **Variables**, add `TELEGRAM_BOT_TOKEN` (and optionally `CHART_PERIOD`).
5. Under **Settings**, set **Deploy** as a **Worker** (not Web Service) so it runs `python main.py` continuously rather than expecting an HTTP server.

## Design decisions & tradeoffs

*(My reasoning, in my own words.)*

- **`yfinance` for market data, not a paid API.** This keeps the bot free to run and easy for anyone to fork and use with their own bot token, at the cost of `yfinance`'s known tradeoffs: it's an unofficial Yahoo Finance wrapper, so data can lag and is subject to rate limiting/breakage if Yahoo changes its endpoints upstream.
- **Rule-based swing detection and Fibonacci levels, not a trained model.** Swing highs/lows and the resulting Fib levels are computed with deterministic logic in `src/analysis/`. This makes the output explainable — the same price history always produces the same levels — rather than a black-box prediction, which matters for a tool meant to support a trader's own judgment rather than replace it.
- **Worker process on Railway, not a webhook-based serverless deploy.** <!-- VERIFY: confirm whether src/bot uses long-polling or webhooks — the Railway "deploy as a Worker" instruction suggests long-polling (continuous process), which is simpler to run but means the bot is only responsive while the worker process is up. --> A continuously-running worker was the simplest deployment model to get right for a single-bot-token, single-instance setup.
- **Light-themed chart output.** <!-- VERIFY: confirm this was chosen for chat-bubble legibility on both Telegram's light and dark themes, versus a dark theme matching typical trading-terminal aesthetics — worth stating the actual reason here. -->
- **One ticker per message, synchronous reply.** Keeps the bot's interaction model dead simple (send symbol, get chart) rather than building a multi-step conversation or watchlist system — see roadmap for where that could go next.

## Status, roadmap & known limits

**Status:** early-stage, single-commit repo. No automated tests or CI currently in the repo.

**Known limits:**
- No persistence — the bot doesn't remember tickers between messages or support a watchlist.
- No rate limiting on requests, so a bot with many simultaneous users could hit `yfinance` rate limits.
- Single-ticker-per-message interaction only; no batch or comparison charts.
- <!-- VERIFY: confirm whether intraday periods (1d/5d) return meaningfully different granularity than daily bars, or whether all periods use daily OHLCV bars — this affects what the "1d" option actually shows the user. -->

## Extending the system

- **New indicators**: add logic in `src/analysis/` and optionally plot in `src/chart/chart_renderer.py`.
- **New data sources**: implement a similar interface in `src/data/` and swap in `main.py` or via config.
- **New bot commands**: extend `src/bot/telegram_bot.py` (e.g. `/help`, `/settings`).

## License

MIT.
