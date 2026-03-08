#!/usr/bin/env python3
"""Start a Bosch dishwasher via Home Connect API, set to finish tomorrow at 06:00 Israel time."""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

BASE_URL = "https://api.home-connect.com"
TOKEN_URL = f"{BASE_URL}/security/oauth/token"
CONTENT_TYPE = "application/vnd.bsh.sdk.v1+json"

RETRY_DELAYS = [30, 60, 120, 240, 480]
RETRYABLE_STATUS_CODES = {409, 504}
NO_RETRY_STATUS_CODES = {401, 403, 404}

# Israel Standard Time (UTC+2) / Israel Daylight Time (UTC+3)
# We use a fixed offset here; adjust if needed for DST transitions.
ISRAEL_TZ = timezone(timedelta(hours=2))
ISRAEL_DST_TZ = timezone(timedelta(hours=3))

FINISH_HOUR = 6  # 06:00 AM Israel time


def log(msg: str) -> None:
    print(f"[dishwasher] {msg}", flush=True)


def get_israel_tz() -> timezone:
    """Return the current Israel timezone offset (IST or IDT).

    Israel observes DST roughly from the last Friday before April 1
    until the last Sunday of October. This is a simplified check.
    """
    now = datetime.now(timezone.utc)
    year = now.year
    # Last Friday before April 1
    april1 = datetime(year, 4, 1, tzinfo=timezone.utc)
    days_since_friday = (april1.weekday() - 4) % 7
    dst_start = april1 - timedelta(days=days_since_friday)
    # Last Sunday of October
    oct31 = datetime(year, 10, 31, tzinfo=timezone.utc)
    days_since_sunday = (oct31.weekday() - 6) % 7
    dst_end = oct31 - timedelta(days=days_since_sunday)
    if dst_start <= now < dst_end:
        return ISRAEL_DST_TZ
    return ISRAEL_TZ


def compute_finish_in_seconds() -> int:
    """Compute seconds from now until tomorrow 06:00 Israel time."""
    tz = get_israel_tz()
    now_israel = datetime.now(tz)
    tomorrow_finish = now_israel.replace(
        hour=FINISH_HOUR, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    delta = tomorrow_finish - now_israel
    seconds = int(delta.total_seconds())
    log(f"Now (Israel): {now_israel.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log(f"Finish target: {tomorrow_finish.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log(f"FinishInRelative: {seconds}s ({seconds // 3600}h {(seconds % 3600) // 60}m)")
    return seconds


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    log(f"POST {TOKEN_URL} (refreshing token)")
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    log(f"Token refresh response {resp.status_code}: {resp.text}")
    if resp.status_code != 200:
        log(f"FATAL: Token refresh failed with status {resp.status_code}")
        log("Check that HC_CLIENT_ID, HC_CLIENT_SECRET, and HC_REFRESH_TOKEN are correct.")
        sys.exit(1)

    return resp.json()["access_token"]


def start_program(access_token: str, ha_id: str, finish_in_seconds: int) -> requests.Response:
    url = f"{BASE_URL}/api/homeappliances/{ha_id}/programs/active"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": CONTENT_TYPE,
        "Content-Type": CONTENT_TYPE,
    }
    body = {
        "data": {
            "key": "Dishcare.Dishwasher.Program.Auto2",
            "options": [
                {
                    "key": "Dishcare.Dishwasher.Option.ExtraDry",
                    "value": True,
                },
                {
                    "key": "BSH.Common.Option.FinishInRelative",
                    "value": finish_in_seconds,
                    "unit": "seconds",
                },
            ],
        }
    }
    log(f"PUT {url}")
    log(f"Request body: {body}")
    resp = requests.put(url, json=body, headers=headers)
    log(f"Response {resp.status_code}")
    log(f"Response headers: {dict(resp.headers)}")
    log(f"Response body: {resp.text}")
    return resp


def should_retry(status_code: int) -> bool:
    if status_code in NO_RETRY_STATUS_CODES:
        return False
    if status_code in RETRYABLE_STATUS_CODES or status_code >= 500:
        return True
    return False


def detect_remote_start_error(resp: requests.Response) -> bool:
    try:
        data = resp.json()
        error_key = data.get("error", {}).get("key", "")
        if "RemoteStartNotEnabled" in error_key or "SDK.Error.HomeAppliance.Connection.Initialization.Failed" in error_key:
            return True
    except Exception:
        pass
    return "remote" in resp.text.lower() and "start" in resp.text.lower()


def main() -> None:
    client_id = os.environ.get("HC_CLIENT_ID", "")
    client_secret = os.environ.get("HC_CLIENT_SECRET", "")
    refresh_token = os.environ.get("HC_REFRESH_TOKEN", "")
    ha_id = os.environ.get("HC_HAID", "")

    missing = []
    if not client_id:
        missing.append("HC_CLIENT_ID")
    if not client_secret:
        missing.append("HC_CLIENT_SECRET")
    if not refresh_token:
        missing.append("HC_REFRESH_TOKEN")
    if not ha_id:
        missing.append("HC_HAID")

    if missing:
        log(f"FATAL: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    # Compute finish time
    finish_in_seconds = compute_finish_in_seconds()

    # Refresh token
    log("Refreshing access token...")
    access_token = refresh_access_token(client_id, client_secret, refresh_token)
    log("Token refreshed successfully.")

    # Start dishwasher with retries
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            resp = start_program(access_token, ha_id, finish_in_seconds)
        except requests.ConnectionError as e:
            log(f"Connection error: {e}")
            if attempt < len(RETRY_DELAYS):
                delay = RETRY_DELAYS[attempt]
                log(f"Retry {attempt + 1}/{len(RETRY_DELAYS)} in {delay}s (connection error)")
                time.sleep(delay)
                continue
            log("FATAL: All retries exhausted due to connection errors.")
            sys.exit(1)

        if resp.status_code in (200, 204):
            log("SUCCESS: Dishwasher program started (delayed finish)!")
            sys.exit(0)

        if detect_remote_start_error(resp):
            log("FATAL: Remote Start is not enabled on the dishwasher.")
            log("Please enable Remote Start on the dishwasher's physical controls and try again.")
            sys.exit(1)

        if not should_retry(resp.status_code):
            log(f"FATAL: Non-retryable error (HTTP {resp.status_code}). Aborting.")
            sys.exit(1)

        if attempt < len(RETRY_DELAYS):
            delay = RETRY_DELAYS[attempt]
            log(f"Retry {attempt + 1}/{len(RETRY_DELAYS)} in {delay}s (HTTP {resp.status_code})")
            time.sleep(delay)
        else:
            log(f"FATAL: All retries exhausted. Last status: {resp.status_code}")
            sys.exit(1)


if __name__ == "__main__":
    main()
