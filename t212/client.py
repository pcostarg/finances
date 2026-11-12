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

# Base URL (Live: 'https://live.trading212.com/api/v0', Demo: 'https://demo.trading212.com/api/v0')
BASE_URL = os.getenv("T212_BASE_URL", "https://live.trading212.com/api/v0").rstrip("/")

DEFAULT_PORTFOLIO_OUTPUT = os.getenv("OUTPUT_FILENAME", "qualtrim_import.csv")
DEFAULT_HISTORY_OUTPUT = os.getenv("HISTORY_OUTPUT_FILENAME", "trading212-history.csv")
DEFAULT_HISTORY_TIME_FROM = os.getenv("HISTORY_TIME_FROM", "2019-01-01T00:00:00Z")

AUTH = (API_KEY, API_SECRET)


def validate_credentials():
    """Ensures API_KEY and API_SECRET are set."""
    if not API_KEY or not API_SECRET:
        print(
            "Error: Missing credentials.\n"
            "Please set 'T212_API_KEY' and 'T212_API_SECRET' in your environment or in a .env file.\n"
            "See .env.example for reference.",
            file=sys.stderr,
        )
        sys.exit(1)


def handle_request_error(e: requests.exceptions.RequestException, context: str = ""):
    """Provides user-friendly error diagnostics for common API failure modes."""
    prefix = f"Error during {context}: " if context else "Error: "
    if e.response is not None:
        status_code = e.response.status_code
        if status_code == 403:
            print(
                f"\n{prefix}403 Forbidden.\n"
                "This usually indicates your API key lacks the required permission scope.\n"
                "Please verify in Trading 212 (Settings > API) that the key has:\n"
                "  - 'History' (and 'History - Orders/Dividends/Transactions') for historical exports\n"
                "  - 'Portfolio' and 'Metadata' for open holdings\n"
                f"API Response Details: {e.response.text}",
                file=sys.stderr,
            )
            return
        elif status_code == 401:
            print(
                f"\n{prefix}401 Unauthorized.\n"
                "Your API key or secret may be incorrect, expired, or revoked.\n"
                f"API Response Details: {e.response.text}",
                file=sys.stderr,
            )
            return
        elif status_code == 429:
            print(
                f"\n{prefix}429 Too Many Requests.\n"
                "You have hit Trading 212's rate limit. Please wait a minute before retrying.",
                file=sys.stderr,
            )
            return
        elif status_code == 400:
            print(
                f"\n{prefix}400 Bad Request.\n"
                f"API Response Details: {e.response.text}",
                file=sys.stderr,
            )
            return
    print(f"\n{prefix}{e}", file=sys.stderr)


def get_ticker_mapping():
    """Fetches instrument metadata from Trading 212 to map internal IDs
    (e.g., 'AAPL_US_EQ') to standard symbols (e.g., 'AAPL').
    """
    validate_credentials()
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
