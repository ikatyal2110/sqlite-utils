# Market-Lens

A full-stack market analysis MVP: a FastAPI backend and a Next.js frontend for stock quotes, screening, news, alerts, and AI-assisted single-stock analysis. I built it as a self-contained demonstration of a complete product slice — API, data layer, and UI wired together — rather than a single isolated script, covering the backend services (quotes, screener, news, alerts, and a weighted recommendation engine combining technicals, sentiment, and risk) plus the Next.js pages that consume them.

<!-- VERIFY: add a LICENSE file (MIT suggested — see META.md) and a badge here once it exists. No CI is currently configured, so no CI badge is included. -->

## Key features

**Core MVP (backend + frontend):**
- `GET /api/quote/{symbol}` — stock quote lookup
- `POST /api/screener/run` — screener over a small seed ticker universe (kept small deliberately to limit external API calls — see [Design decisions](#design-decisions--tradeoffs))
- `GET /api/news` — financial news retrieval
- `POST /api/alerts`, `GET /api/alerts` — alert management, persisted to a local SQLite database (`finmvp.db`)
- Next.js frontend pages: `/` (dashboard), `/screener`, `/news`, `/alerts`

**Extended analysis engine** (per `IMPLEMENTATION_SUMMARY.md` / `FEATURES_SUMMARY.md` in this repo):
- `POST /api/analyze` and `GET /api/analyze/{symbol}` — combines technical indicators (40% weight), news sentiment via VaderSentiment (30%), and a risk assessment — volatility, max drawdown, beta vs. SPY (30%) — into a single BUY/HOLD/SELL recommendation with a confidence score and stated rationale.
- Financial metrics (valuation, profitability, growth, financial health), pattern recognition (support/resistance, double top/bottom, trend/breakout detection), and correlation analysis against major indices (SPY/QQQ/DIA/IWM).
- `POST /api/trade/simulate` and `POST /api/trade/risk-reward` — trade P&L simulation and risk/reward calculators.
- `GET /api/market/regime` — bull/bear/sideways market regime detection with a confidence score.
- In-memory response caching (default 10-minute TTL, configurable) to reduce calls to the underlying market-data API.
- Frontend: a tabbed `/analyze` page (Overview / Financials / Patterns / Correlations / Catalysts) built on an "Obsidian Glass" dark theme.

<!-- VERIFY: the underlying market-data provider for quotes/screener/analysis isn't stated explicitly in the repo's own docs (unlike the stock-charts repo, which names yfinance directly). Confirm and name it here — this matters for anyone evaluating rate limits or data licensing. -->

## Screenshot / Demo

<!-- VERIFY / TODO(owner): The repo currently ships a placeholder mockup at frontend/public/obsidian_mock.png rather than a real screenshot of the running app — replace it. Capture: (1) the dashboard at localhost:3000 with a real quote loaded, and (2) the /analyze page's Overview tab showing the recommendation card (BUY/HOLD/SELL + confidence), sentiment card, and risk card together, since that combined view is this project's most distinctive feature. -->

## Quickstart (development)

**1. Backend**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**2. Frontend**
```bash
cd frontend
npm install
npm run dev
# open http://localhost:3000
```

**Optional backend environment variables** (create `backend/.env`):
```
DATABASE_URL=sqlite:///./finmvp.db
CACHE_TTL_SECONDS=600
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
```

**Try the analysis endpoint directly:**
```bash
curl -X POST http://localhost:8000/api/analyze -H "Content-Type: application/json" -d '{"symbol": "AAPL"}'
```

A `docker-compose.yml` is included in the repo root for containerized setup. <!-- VERIFY: confirm the exact services/ports it wires up and document the one-command `docker compose up` flow here once verified. -->

## Design decisions & tradeoffs

*(My reasoning, in my own words.)*

- **Small seed ticker universe for the screener**, rather than scanning the whole market. This was a deliberate MVP tradeoff to avoid hammering the market-data API with unbounded requests — see `screener_service.SEED_TICKERS`. It means the screener demonstrates the mechanism, not full market coverage.
- **SQLite for alerts, not Postgres.** For a single-developer MVP, a local file database was the fastest path to "alerts persist across restarts" without standing up separate infrastructure. Explicitly not meant to be the production answer — see known limits below.
- **In-memory caching with a TTL instead of Redis.** Same reasoning as SQLite: the goal was to cut down on redundant market-data calls without adding an external dependency for a demo-scale project.
- **Weighted-average recommendation engine, not a trained model.** BUY/HOLD/SELL is computed from fixed weights across technical/sentiment/risk (and, in the extended engine, financial health/historical performance/valuation/catalysts/trend) signals. This keeps the recommendation logic transparent and inspectable — you can see exactly which factor moved the score — at the cost of not adapting the weights from data.
- **Parallel data fetching in the analyze endpoint.** Technical, sentiment, and risk data are fetched concurrently rather than sequentially, since the analyze endpoint touches multiple external calls and users are waiting synchronously for the response.

<!-- VERIFY: this repo is a single commit — I don't have visibility into design discussions or discarded alternatives beyond what's captured in IMPLEMENTATION_SUMMARY.md and FEATURES_SUMMARY.md. Treat the above as reconstructed intent, and correct anything that doesn't match how the code actually works. -->

## Status, roadmap & known limits

**Status:** MVP / single-commit prototype. No releases, no CI configured yet, no LICENSE file yet.

**Explicitly noted as needed for production** (from the project's own notes): caching hardening, rate limiting, secrets management, and a proper worker system (e.g., Celery/Redis) in place of the current in-memory cache and synchronous request handling.

**Backlog / future ideas** (not yet built — from `FEATURES_SUMMARY.md`'s own "Future Enhancement Ideas," listed here as roadmap, not shipped features): portfolio tracker, watchlist with alert integration, options-flow / put-call-ratio analysis, earnings calendar, insider-trading alerts, sector rotation analysis, a backtesting engine, and social sentiment (Reddit/Twitter) signals.

**Known limits today:** SQLite/in-memory cache won't hold up under concurrent multi-user load; no automated tests or CI visible in the repo; screener is bounded to a small seed ticker list rather than the full market.

## License

<!-- VERIFY: no LICENSE file present in the repo. MIT is suggested in META.md — add a LICENSE file and update this section once chosen. -->
