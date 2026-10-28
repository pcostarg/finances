import csv
import os
import sys
import requests


def load_env_file(filepath=".env"):
    """Loads key-value pairs from a .env file into os.environ if present."""
    if not os.path.exists(filepath):
        return
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("\"'")
            os.environ.setdefault(key, val)


load_env_file()

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
API_KEY = os.getenv("T212_API_KEY")
API_SECRET = os.getenv("T212_API_SECRET")

# Base URL (Live: 'live', Paper Trading: 'demo')
BASE_URL = os.getenv("T212_BASE_URL", "https://live.trading212.com/api/v0")
OUTPUT_FILENAME = os.getenv("OUTPUT_FILENAME", "qualtrim_import.csv")

# Basic auth tuple used for all requests
AUTH = (API_KEY, API_SECRET)


def validate_credentials():
    if not API_KEY or not API_SECRET:
        print(
            "Error: Missing credentials.\n"
            "Please set 'T212_API_KEY' and 'T212_API_SECRET' in your environment or in a .env file.\n"
            "See .env.example for reference.",
            file=sys.stderr,
        )
        sys.exit(1)


def get_ticker_mapping():
    """Fetches instrument metadata from Trading 212 to map internal IDs
    (e.g., 'AAPL_US_EQ') to standard symbols (e.g., 'AAPL').
    """
    print("Fetching Trading 212 instrument metadata for ticker mapping...")
    url = f"{BASE_URL}/equity/metadata/instruments"
    try:
        response = requests.get(url, auth=AUTH)
        response.raise_for_status()
        instruments = response.json()

        mapping = {}
        for inst in instruments:
            internal_ticker = inst.get("ticker")
            short_name = inst.get("shortName")
            if internal_ticker:
                standard_symbol = short_name if short_name else internal_ticker.split("_")[0]
                mapping[internal_ticker] = standard_symbol
        return mapping
    except Exception as e:
        print(f"Notice: Metadata lookup ({e}). Falling back to internal ticker parsing.")
        return {}


def export_to_qualtrim_csv():
    validate_credentials()
    ticker_map = get_ticker_mapping()

    positions_url = f"{BASE_URL}/equity/positions"
    print("Fetching active portfolio holdings...")

    try:
        response = requests.get(positions_url, auth=AUTH)
        response.raise_for_status()
        positions = response.json()

        if not positions:
            print("No active open positions found in your account.")
            return

        # Exact column headers required by your Qualtrim template
        fieldnames = ["symbol", "shares", "avgPricePaid"]

        with open(OUTPUT_FILENAME, mode="w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()

            for pos in positions:
                # 1. Resolve ticker (nested under 'instrument' in T212 API)
                inst = pos.get("instrument") if isinstance(pos.get("instrument"), dict) else {}
                t212_ticker = inst.get("ticker") or pos.get("ticker")

                clean_symbol = ticker_map.get(t212_ticker)
                if not clean_symbol and t212_ticker:
                    clean_symbol = t212_ticker.split("_")[0]

                # 2. Extract average price ('averagePricePaid' in T212 API)
                avg_price = (
                    pos.get("averagePricePaid")
                    if pos.get("averagePricePaid") is not None
                    else (pos.get("averagePrice") or pos.get("average_price"))
                )

                row = {
                    "symbol": clean_symbol,
                    "shares": pos.get("quantity"),
                    "avgPricePaid": avg_price,
                }
                writer.writerow(row)

        print(f"\nSuccess! Generated '{OUTPUT_FILENAME}' containing {len(positions)} holdings.")
        print("You can now drop this file directly into your Qualtrim dashboard.")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while communicating with the Trading 212 API: {e}")


if __name__ == "__main__":
    export_to_qualtrim_csv()
