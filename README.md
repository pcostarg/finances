# Trading 212 Data Export Tools

Python utilities to export open portfolio holdings and complete account transaction history from **Trading 212** via its Public API, with guides for importing cleanly into **Qualtrim** and **[Wealthfolio](https://github.com/wealthfolio/wealthfolio)**.

---

## Features

1. **Portfolio Holdings Export (`--portfolio` / `csv-T212-portfolio.py`)**
   - Queries `GET /equity/positions` and maps internal tickers via `GET /equity/metadata/instruments`.
   - Extracts share counts and `averagePricePaid` into a 3-column CSV (`symbol,shares,avgPricePaid`) ready for [Qualtrim](https://qualtrim.com).

2. **Full Transaction History Export (`--history` / `csv-T212-history.py`)**
   - Uses Trading 212's official asynchronous CSV export endpoint (`/equity/history/exports`).
   - Automatically splits multi-year ranges into `<= 364`-day chunks (`MAX_CHUNK_DAYS = 364`), handles endpoint cooldowns (`31s` `POST`, `61s` `GET`) and `429` / `TooManyRequests` retries, reuses matching queued reports, and merges/deduplicates all chunks newest-first.
   - Captures **all** account activity: Market & Limit trades (including AutoInvest Pie purchases), dividends & withholding taxes, cash interest, share lending interest, deposits/withdrawals, debit card purchases & cashback, and currency conversions.

3. **Unified CLI & Interactive Menu (`main.py`)**
   - Interactive menu when launched without flags, or non-interactive CLI flags (`--portfolio`, `--history`, `--all`, `--from`, `--to`, `--output`) for scripting.

---

## Project Structure

```text
finances/
├── main.py                      # Unified interactive menu & CLI entrypoint
├── csv-T212-portfolio.py        # Standalone portfolio holdings exporter
├── csv-T212-history.py          # Standalone full history exporter
├── t212/
│   ├── __init__.py
│   ├── client.py                # Credentials (.env), auth, error diagnostics & ticker mapping
│   ├── portfolio.py             # Open positions export (/equity/positions)
│   └── history.py               # Chunked /equity/history/exports downloader & merger
├── doc/
│   ├── trading212-api-setup.md  # Detailed Trading 212 API permissions, .env & rate-limit guide
│   └── wealthfolio-import.md    # Complete Wealthfolio import mapping, troubleshooting & addon blueprint
├── .env.example                 # Environment variable template
└── README.md
```

---

## Quick Start

### 1. Install Dependencies
Requires Python 3.9+ and `requests`:
```bash
pip install requests
```

### 2. Configure Trading 212 API & `.env`
1. In Trading 212, go to **Menu (`☰`) → Settings → API (Beta)** and generate a read-only key with:
   - **Required:** `History`, `Portfolio`, `Metadata`
   - **Safe read-only extras:** `History - Dividends`, `History - Orders`, `History - Transactions`
   - **Leave unchecked:** `Orders - Execute`, `Pies - Write`
2. Copy `.env.example` to `.env` and add your credentials:
   ```powershell
   Copy-Item .env.example .env
   ```
   ```env
   T212_API_KEY=your_api_key_here
   T212_API_SECRET=your_api_secret_here
   ```

> See **[Trading 212 API & `.env` Setup Guide](doc/trading212-api-setup.md)** for full permission details, optional `.env` variables (`T212_BASE_URL`, `HISTORY_TIME_FROM`, custom output filenames), and rate-limit internals.

---

## Usage

### Interactive Menu
```bash
python main.py
```

### CLI Commands (Automated / Scripted)
```bash
# Export only open portfolio holdings (Qualtrim CSV)
python main.py --portfolio

# Export full transaction history
python main.py --history

# Export history for a specific date range
python main.py --history --from 2025-07-24 --to 2026-11-12

# Export history to a custom CSV filename
python main.py --history --output my_trades.csv

# Export both holdings and transaction history
python main.py --all
```

### Standalone Scripts
```bash
python csv-T212-portfolio.py
python csv-T212-history.py
```

---

## Getting Your Data into Wealthfolio

**[Wealthfolio](https://github.com/wealthfolio/wealthfolio)** is a local-first portfolio tracker, and its built-in Trading 212 CSV template has a few quirks with modern Trading 212 exports (such as mapping `Card debit` to `Fee`, double-counting `Currency conversion fee`, leaving `Currency conversion` as `Transfer Out`, or resolving bare tickers like `LTC` to Crypto / `XETR`).

Follow the dedicated guide for exact working mappings and fixes:
- **[Wealthfolio Import & Troubleshooting Guide](doc/wealthfolio-import.md)** — Covers column mapping (`fee -> Ignore`), activity mapping (`Card debit -> Withdrawal`, `Currency conversion -> Fee`, `Spending cashback / Card credit / Dividend adjustment -> Credit`), ticker disambiguation (`LTC`, US vs `XETR`), cash/pot reconciliation, fixing `Partial data` warnings, and an automated Addon sync blueprint.
