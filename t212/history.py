import csv
import datetime
import io
import time
import requests
from t212.client import (
    AUTH,
    BASE_URL,
    DEFAULT_HISTORY_OUTPUT,
    DEFAULT_HISTORY_TIME_FROM,
    handle_request_error,
    validate_credentials,
)

# Trading 212 restricts /equity/history/exports to <= 1 year per request.
# Use 364 days per chunk to stay safely under the 1-year cap (including leap years).
MAX_CHUNK_DAYS = 364

# Official endpoint rate limits: POST = 1 req / 30s, GET = 1 req / 60s
POST_COOLDOWN_SEC = 31
GET_COOLDOWN_SEC = 61


def parse_iso_datetime(ts_str: str, end_of_day: bool = False) -> datetime.datetime:
    """Parses a date or ISO-8601 timestamp string into a UTC-aware datetime."""
    ts = ts_str.strip()
    if len(ts) == 10 and "-" in ts:
        suffix = "T23:59:59+00:00" if end_of_day else "T00:00:00+00:00"
        ts = f"{ts}{suffix}"
    else:
        ts = ts.replace(" ", "T").replace("Z", "+00:00")
        if "+" not in ts and "-" not in ts[10:]:
            ts = f"{ts}+00:00"
    return datetime.datetime.fromisoformat(ts).astimezone(datetime.timezone.utc)


def format_iso_utc(dt: datetime.datetime) -> str:
    """Formats a UTC datetime as YYYY-MM-DDTHH:MM:SSZ."""
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_yearly_chunks(start_dt: datetime.datetime, end_dt: datetime.datetime) -> list:
    """Splits [start_dt, end_dt] into chunks no larger than MAX_CHUNK_DAYS."""
    if start_dt >= end_dt:
        return [(start_dt, end_dt)]

    chunks = []
    cursor = start_dt
    delta = datetime.timedelta(days=MAX_CHUNK_DAYS)
    while cursor < end_dt:
        chunk_end = min(cursor + delta, end_dt)
        chunks.append((cursor, chunk_end))
        if chunk_end >= end_dt:
            break
        # Overlap by 1 second to avoid missing sub-second events; merged output is deduplicated.
        cursor = chunk_end
    return chunks


def is_rate_limit_response(response: requests.Response) -> bool:
    """Detects Trading 212 rate limits across both HTTP 429 and JSON BusinessException."""
    if response.status_code == 429:
        return True
    try:
        data = response.json()
        if isinstance(data, dict):
            ctx = data.get("context") or {}
            if ctx.get("type") == "TooManyRequests":
                return True
    except ValueError:
        pass
    return False


def request_with_cooldown(
    method: str,
    url: str,
    last_call_ts: dict,
    cooldown: int,
    **kwargs,
) -> requests.Response:
    """Executes an HTTP request while respecting endpoint cooldowns and retrying rate limits."""
    for attempt in range(5):
        elapsed = time.time() - last_call_ts.get(method, 0.0)
        if last_call_ts.get(method, 0.0) > 0 and elapsed < cooldown:
            wait_sec = int(cooldown - elapsed) + 1
            print(f"  Waiting {wait_sec}s to respect Trading 212 {method} rate limit...")
            time.sleep(wait_sec)

        response = requests.request(method, url, auth=AUTH, **kwargs)
        last_call_ts[method] = time.time()

        if is_rate_limit_response(response):
            retry_after = int(response.headers.get("Retry-After", cooldown))
            wait_sec = max(retry_after, cooldown)
            print(f"  Rate limit reached on {method}; waiting {wait_sec}s before retry...")
            time.sleep(wait_sec)
            last_call_ts[method] = time.time()
            continue

        response.raise_for_status()
        return response

    response.raise_for_status()
    return response


def find_matching_report(reports: list, time_from: str, time_to: str) -> dict | None:
    """Finds an existing report matching the requested range and full data flags."""
    if not isinstance(reports, list):
        return None
    target_from = parse_iso_datetime(time_from)
    target_to = parse_iso_datetime(time_to)

    for rep in reports:
        inc = rep.get("dataIncluded") or {}
        if not (
            inc.get("includeOrders")
            and inc.get("includeTransactions")
            and inc.get("includeDividends")
            and inc.get("includeInterest")
        ):
            continue
        try:
            rep_from = parse_iso_datetime(rep.get("timeFrom", ""))
            rep_to = parse_iso_datetime(rep.get("timeTo", ""))
        except Exception:
            continue
        if abs((rep_from - target_from).total_seconds()) <= 5 and abs((rep_to - target_to).total_seconds()) <= 5:
            if rep.get("status") not in ("Failed", "Canceled"):
                return rep
    return None


def download_csv_text(download_link: str) -> str:
    """Downloads a pre-signed Trading 212 S3 report CSV without leaking Basic Auth headers."""
    res = requests.get(download_link)
    if res.status_code in (401, 403):
        res = requests.get(download_link, auth=AUTH)
    res.raise_for_status()
    res.encoding = "utf-8"
    return res.text


def merge_csv_reports(csv_texts: list) -> tuple[list, list]:
    """Merges multiple Trading 212 CSV strings, deduplicating boundary rows and sorting newest-first."""
    headers = []
    seen_headers = set()
    rows = []
    seen_keys = set()

    for text in csv_texts:
        if not text.strip():
            continue
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
        for col in reader.fieldnames or []:
            if col not in seen_headers:
                seen_headers.add(col)
                headers.append(col)

        for row in reader:
            row_id = row.get("ID") or ""
            dedup_key = (
                row.get("Action", ""),
                row.get("Time (UTC)", ""),
                row_id,
                row.get("Ticker", ""),
                row.get("Total", ""),
                row.get("No. of shares", ""),
            )
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            rows.append(row)

    rows.sort(key=lambda r: r.get("Time (UTC)") or "", reverse=True)
    return headers, rows


def export_history_to_csv(
    output_filename: str = None,
    time_from: str = None,
    time_to: str = None,
    poll_interval: int = GET_COOLDOWN_SEC,
    timeout: int = 900,
) -> bool:
    """Exports complete Trading 212 account history via the official /equity/history/exports API.

    Automatically splits multi-year ranges into <= 1-year chunks, polls for completion,
    downloads each official CSV, and merges them into a single deduplicated file.
    """
    validate_credentials()
    filename = output_filename or DEFAULT_HISTORY_OUTPUT

    start_dt = parse_iso_datetime(time_from or DEFAULT_HISTORY_TIME_FROM, end_of_day=False)
    end_dt = (
        parse_iso_datetime(time_to, end_of_day=True)
        if time_to
        else datetime.datetime.now(datetime.timezone.utc)
    )
    chunks = build_yearly_chunks(start_dt, end_dt)

    print("\nStarting official Trading 212 CSV history export...")
    print(f"  • Date range: {format_iso_utc(start_dt)} -> {format_iso_utc(end_dt)}")
    print(f"  • 1-year chunks required: {len(chunks)}")
    print(f"  • Destination file: '{filename}'\n")

    exports_url = f"{BASE_URL}/equity/history/exports"
    last_call_ts = {"GET": 0.0, "POST": 0.0}

    try:
        # 1. Check existing reports once to reuse any already-generated chunks
        print("Checking existing Trading 212 export queue...")
        init_res = request_with_cooldown("GET", exports_url, last_call_ts, GET_COOLDOWN_SEC)
        existing_reports = init_res.json() if isinstance(init_res.json(), list) else []

        chunk_report_ids = []
        for idx, (c_start, c_end) in enumerate(chunks, start=1):
            c_from = format_iso_utc(c_start)
            c_to = format_iso_utc(c_end)
            existing = find_matching_report(existing_reports, c_from, c_to)

            if existing:
                rep_id = existing.get("reportId")
                print(
                    f"Chunk {idx}/{len(chunks)} ({c_from[:10]} -> {c_to[:10]}): "
                    f"reusing report #{rep_id} (status: {existing.get('status')})."
                )
                chunk_report_ids.append(rep_id)
                continue

            print(f"Chunk {idx}/{len(chunks)}: requesting export ({c_from[:10]} -> {c_to[:10]})...")
            payload = {
                "dataIncluded": {
                    "includeDividends": True,
                    "includeInterest": True,
                    "includeOrders": True,
                    "includeTransactions": True,
                },
                "timeFrom": c_from,
                "timeTo": c_to,
            }
            post_res = request_with_cooldown(
                "POST", exports_url, last_call_ts, POST_COOLDOWN_SEC, json=payload
            )
            data = post_res.json()
            rep_id = data.get("reportId") if isinstance(data, dict) else data
            if not rep_id:
                print(f"Error: API did not return a reportId for chunk {idx}: {data}")
                return False
            print(f"  -> Queued report #{rep_id}.")
            chunk_report_ids.append(rep_id)

        # 2. Poll until every chunk report is Finished
        start_wait = time.time()
        download_links = {}

        while len(download_links) < len(chunk_report_ids):
            if time.time() - start_wait >= timeout:
                print(f"Error: Export generation timed out after {timeout} seconds.")
                return False

            # Check if we already have all links from existing_reports before polling
            reports_by_id = {
                str(r.get("reportId")): r
                for r in existing_reports
                if isinstance(r, dict) and r.get("reportId") is not None
            }

            all_known_finished = True
            for rep_id in chunk_report_ids:
                rep = reports_by_id.get(str(rep_id))
                if not rep or rep.get("status") != "Finished":
                    all_known_finished = False
                    break

            if not all_known_finished:
                print("Polling report generation status...")
                poll_res = request_with_cooldown(
                    "GET", exports_url, last_call_ts, max(GET_COOLDOWN_SEC, poll_interval)
                )
                existing_reports = poll_res.json() if isinstance(poll_res.json(), list) else []
                reports_by_id = {
                    str(r.get("reportId")): r
                    for r in existing_reports
                    if isinstance(r, dict) and r.get("reportId") is not None
                }

            for rep_id in chunk_report_ids:
                if rep_id in download_links:
                    continue
                rep = reports_by_id.get(str(rep_id))
                if not rep:
                    continue
                status = rep.get("status")
                if status == "Finished":
                    link = rep.get("downloadLink")
                    if not link:
                        print(f"Error: Report #{rep_id} finished without a downloadLink.")
                        return False
                    download_links[rep_id] = link
                    print(f"  • Report #{rep_id}: Finished")
                elif status in ("Failed", "Canceled"):
                    print(f"Error: Report #{rep_id} ended with status '{status}'.")
                    return False
                else:
                    print(f"  • Report #{rep_id}: {status}")

        # 3. Download and merge all CSVs
        print(f"\nDownloading {len(chunk_report_ids)} CSV report(s)...")
        csv_texts = []
        for rep_id in chunk_report_ids:
            csv_texts.append(download_csv_text(download_links[rep_id]))

        headers, rows = merge_csv_reports(csv_texts)
        if not headers:
            print("Warning: Downloaded export reports contained no rows.")
            return False

        with open(filename, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

        print(f"\n[Success] Merged and saved {len(rows)} records to '{filename}'.")
        return True

    except requests.exceptions.RequestException as e:
        handle_request_error(e, context="transaction history export")
        return False
