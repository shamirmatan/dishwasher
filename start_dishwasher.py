#!/usr/bin/env python3
"""Start a Bosch dishwasher via Home Connect API with retry logic."""

import requests

from homeconnect import (
    BASE_URL,
    CONTENT_TYPE,
    load_env,
    log,
    refresh_access_token,
    run_with_retries,
)


def start_program(access_token: str, ha_id: str) -> requests.Response:
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
                }
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


def main() -> None:
    client_id, client_secret, refresh_token, ha_id = load_env()

    log("Refreshing access token...")
    access_token = refresh_access_token(client_id, client_secret, refresh_token)
    log("Token refreshed successfully.")

    run_with_retries(
        action=lambda: start_program(access_token, ha_id),
        success_msg="Dishwasher program started!",
        check_remote_start=True,
    )


if __name__ == "__main__":
    main()
