import csv
import requests
from t212.client import (
    AUTH,
    BASE_URL,
    DEFAULT_PORTFOLIO_OUTPUT,
    get_ticker_mapping,
    handle_request_error,
    validate_credentials,
)


def export_portfolio_to_csv(output_filename=None):
    """Fetches open holdings from Trading 212 and exports them to a Qualtrim-compatible CSV."""
    validate_credentials()
    filename = output_filename or DEFAULT_PORTFOLIO_OUTPUT
    ticker_map = get_ticker_mapping()

    positions_url = f"{BASE_URL}/equity/positions"
    print("Fetching active portfolio holdings...")

    try:
        response = requests.get(positions_url, auth=AUTH)
        response.raise_for_status()
        positions = response.json()

        if not positions:
            print("No active open positions found in your account.")
            return False

        # Exact column headers required by Qualtrim template
        fieldnames = ["symbol", "shares", "avgPricePaid"]

        with open(filename, mode="w", newline="", encoding="utf-8") as csv_file:
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

        print(f"\n[Success] Generated '{filename}' containing {len(positions)} holdings.")
        print("You can now drop this file directly into your Qualtrim dashboard.")
        return True

    except requests.exceptions.RequestException as e:
        handle_request_error(e, context="portfolio holdings export")
        return False
