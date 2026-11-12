# Trading 212 API & Environment Setup

This guide explains how to generate a read-only Trading 212 API key with the exact permissions needed by this project, configure `.env`, and understand how the exporter handles rate limits and multi-year histories.

---

## 1. Generate a Trading 212 API Key

1. Open Trading 212 (web app or mobile app).
2. Go to **Menu (`☰`) → Settings → API (Beta)**.
3. Click **Generate API key**.
4. Configure **Permissions** using the principle of least privilege (100% read-only):

### Required permissions (for current scripts)

| Permission | Required? | Endpoint / Usage in This Repo |
| :--- | :--- | :--- |
| **`History`** | **Yes** | [`t212/history.py`](../t212/history.py) (`GET` / `POST /equity/history/exports`) |
| **`Portfolio`** | **Yes** | [`t212/portfolio.py`](../t212/portfolio.py) (`GET /equity/positions`) |
| **`Metadata`** | **Yes** | [`t212/client.py`](../t212/client.py) (`GET /equity/metadata/instruments`) for ticker mapping |

### Safe read-only extras

| Permission | Recommendation | Purpose |
| :--- | :--- | :--- |
| **`History - Dividends`** | Keep checked | Read-only dividend log access; useful for future incremental sync scripts/addons |
| **`History - Orders`** | Keep checked | Read-only historical order log access; useful for future incremental sync scripts/addons |
| **`History - Transactions`** | Keep checked | Read-only cash transaction log access; useful for future incremental sync scripts/addons |
| **`Account data`** | Optional (leave unchecked for current scripts) | Only needed if a future sync tool reads live cash balances / account currency directly |

### Permissions to keep **unchecked**

- **`Orders - Execute`** — **Leave unchecked.** Allows placing/canceling real trades.
- **`Pies - Write`** — **Leave unchecked.** Allows modifying your AutoInvest Pies.
- **`Orders - Read` / `Pies - Read`** — Not used by these export scripts (only needed if a future tool inspects active pending orders or pie weights).

> [!TIP]
> Trading 212 displays your **API Key** and **API Secret** only once when created. Copy both immediately into your local `.env` file. You can also restrict the key by IP address in Trading 212 if you run exports from a fixed machine.

---

## 2. Configure `.env`

Create a `.env` file from the template in the repository root:

**PowerShell (Windows):**
```powershell
Copy-Item .env.example .env
```

**macOS / Linux / Git Bash:**
```bash
cp .env.example .env
```

Open `.env` and fill in your credentials:

```env
# Required: HTTP Basic Auth credentials generated in Trading 212 Settings > API (Beta)
T212_API_KEY=your_api_key_here
T212_API_SECRET=your_api_secret_here

# Optional: Live vs Demo environment
# Live (default): https://live.trading212.com/api/v0
# Demo:           https://demo.trading212.com/api/v0
# T212_BASE_URL=https://live.trading212.com/api/v0

# Optional: Default output filenames
# OUTPUT_FILENAME=qualtrim_import.csv
# HISTORY_OUTPUT_FILENAME=trading212-history.csv

# Optional: Default start date/timestamp when --from is omitted
# HISTORY_TIME_FROM=2019-01-01T00:00:00Z
```

### Environment Variables Reference

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `T212_API_KEY` | **Yes** | — | Trading 212 API Key (Basic Auth username). |
| `T212_API_SECRET` | **Yes** | — | Trading 212 API Secret (Basic Auth password). |
| `T212_BASE_URL` | No | `https://live.trading212.com/api/v0` | Base API URL (`live` or `demo`). |
| `OUTPUT_FILENAME` | No | `qualtrim_import.csv` | Output filename for open holdings (`--portfolio` or `csv-T212-portfolio.py`). |
| `HISTORY_OUTPUT_FILENAME` | No | `trading212-history.csv` | Output filename for history CSV (`--history` or `csv-T212-history.py`). |
| `HISTORY_TIME_FROM` | No | `2019-01-01T00:00:00Z` | Default start date/time for history exports when `--from` is not passed. |

> [!CAUTION]
> Keep `.env` out of version control. It is already listed in `.gitignore`. Never commit API keys or secrets.

---

## 3. How the History Exporter Works Under the Hood

Trading 212 exposes granular endpoints (`/equity/history/orders`, `/equity/history/dividends`, `/equity/history/transactions`), as well as the official CSV report endpoint (`/equity/history/exports`).

This project intentionally uses **`/equity/history/exports`** in [`t212/history.py`](../t212/history.py) because:
- **Complete ledger coverage:** The official export CSV includes AutoInvest Pie buys/sells, limit/market trades, dividends (plus withholding taxes and dividend adjustments), Spending Pot debit card purchases (`Card debit`, `Card credit`, `Spending cashback`), cash interest, share lending interest, deposits/withdrawals, and currency conversions.
- **Automatic multi-year chunking:** Trading 212 caps each `/equity/history/exports` request at 1 year. `t212/history.py` automatically splits `[timeFrom, timeTo]` into `364`-day chunks (`MAX_CHUNK_DAYS = 364`).
- **Rate-limit handling & report reuse:** Respects Trading 212's cooldowns (`31s` between `POST` export creation calls, `61s` between `GET` polling calls, with `Retry-After` / `TooManyRequests` backoff), reuses matching already-generated reports in your export queue, downloads each finished CSV cleanly, deduplicates chunk boundaries, and sorts rows newest-first.

### Tip for faster exports
Pass `--from` with the year you actually opened your Trading 212 account (or set `HISTORY_TIME_FROM` in `.env`) to avoid queueing empty 1-year chunks starting from `2019-01-01`:

```bash
python main.py --history --from 2025-07-24
```
