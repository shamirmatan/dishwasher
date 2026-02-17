#!/usr/bin/env python3
"""Stop a Bosch dishwasher via Home Connect API."""

import os
import sys
import time

import requests

BASE_URL = "https://api.home-connect.com"
TOKEN_URL = f"{BASE_URL}/security/oauth/token"
CONTENT_TYPE = "application/vnd.bsh.sdk.v1+json"

RETRY_DELAYS = [30, 60, 120, 240, 480]
RETRYABLE_STATUS_CODES = {409, 504}
NO_RETRY_STATUS_CODES = {401, 403, 404}


def log(msg: str) -> None:
    print(f"[dishwasher] {msg}", flush=True)


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
        sys.exit(1)

    return resp.json()["access_token"]


def stop_program(access_token: str, ha_id: str) -> requests.Response:
    url = f"{BASE_URL}/api/homeappliances/{ha_id}/programs/active"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": CONTENT_TYPE,
    }
    log(f"DELETE {url}")
    resp = requests.delete(url, headers=headers)
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


def main() -> None:
    client_id = os.environ.get("HC_CLIENT_ID", "")
    client_secret = os.environ.get("HC_CLIENT_SECRET", "")
    refresh_token = os.environ.get("HC_REFRESH_TOKEN", "")
    ha_id = os.environ.get("HC_HAID", "")

    missing = [name for name, val in [
        ("HC_CLIENT_ID", client_id), ("HC_CLIENT_SECRET", client_secret),
        ("HC_REFRESH_TOKEN", refresh_token), ("HC_HAID", ha_id),
    ] if not val]

    if missing:
        log(f"FATAL: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    log("Refreshing access token...")
    access_token = refresh_access_token(client_id, client_secret, refresh_token)
    log("Token refreshed successfully.")

    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            resp = stop_program(access_token, ha_id)
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
            log("SUCCESS: Dishwasher program stopped!")
            sys.exit(0)

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
