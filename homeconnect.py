"""Shared helpers for Bosch Home Connect API scripts."""

import os
import sys
import time
from typing import Callable

import requests

BASE_URL = "https://api.home-connect.com"
TOKEN_URL = f"{BASE_URL}/security/oauth/token"
CONTENT_TYPE = "application/vnd.bsh.sdk.v1+json"

RETRY_DELAYS = [30, 60, 120, 240, 480]
RETRYABLE_STATUS_CODES = {409, 504}
NO_RETRY_STATUS_CODES = {401, 403, 404}


def log(msg: str) -> None:
    print(f"[dishwasher] {msg}", flush=True)


def load_env() -> tuple[str, str, str, str]:
    """Load and validate required environment variables.

    Returns (client_id, client_secret, refresh_token, ha_id) or exits on error.
    """
    names = ("HC_CLIENT_ID", "HC_CLIENT_SECRET", "HC_REFRESH_TOKEN", "HC_HAID")
    values = tuple(os.environ.get(n, "") for n in names)
    missing = [n for n, v in zip(names, values) if not v]
    if missing:
        log(f"FATAL: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)
    return values  # type: ignore[return-value]


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


def run_with_retries(
    action: Callable[[], requests.Response],
    success_msg: str,
    check_remote_start: bool = False,
) -> None:
    """Execute *action* with retry logic, exiting on success or fatal error."""
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            resp = action()
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
            log(f"SUCCESS: {success_msg}")
            sys.exit(0)

        if check_remote_start and detect_remote_start_error(resp):
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
