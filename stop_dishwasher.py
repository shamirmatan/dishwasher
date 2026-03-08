#!/usr/bin/env python3
"""Stop a Bosch dishwasher via Home Connect API."""

import requests

from homeconnect import (
    BASE_URL,
    CONTENT_TYPE,
    load_env,
    log,
    refresh_access_token,
    run_with_retries,
)


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


def main() -> None:
    client_id, client_secret, refresh_token, ha_id = load_env()

    log("Refreshing access token...")
    access_token = refresh_access_token(client_id, client_secret, refresh_token)
    log("Token refreshed successfully.")

    run_with_retries(
        action=lambda: stop_program(access_token, ha_id),
        success_msg="Dishwasher program stopped!",
    )


if __name__ == "__main__":
    main()
