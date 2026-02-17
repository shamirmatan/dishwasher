#!/usr/bin/env python3
"""One-time OAuth2 Device Flow setup for Home Connect API."""

import sys
import time

import requests

BASE_URL = "https://api.home-connect.com"
DEVICE_AUTH_URL = f"{BASE_URL}/security/oauth/device_authorization"
TOKEN_URL = f"{BASE_URL}/security/oauth/token"
APPLIANCES_URL = f"{BASE_URL}/api/homeappliances"
SCOPES = "IdentifyAppliance Dishwasher"


def log(msg: str) -> None:
    print(f"[setup] {msg}")


def device_authorization(client_id: str) -> dict:
    log(f"POST {DEVICE_AUTH_URL}")
    resp = requests.post(
        DEVICE_AUTH_URL,
        data={"client_id": client_id, "scope": SCOPES},
    )
    log(f"Response {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()


def poll_for_token(client_id: str, device_code: str, interval: int) -> dict:
    log("Polling for authorization...")
    while True:
        time.sleep(interval)
        log(f"POST {TOKEN_URL} (polling)")
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": client_id,
            },
        )
        log(f"Response {resp.status_code}: {resp.text}")

        if resp.status_code == 200:
            return resp.json()

        error = resp.json().get("error", "")
        if error == "authorization_pending":
            log("Still waiting for user authorization...")
            continue
        if error == "slow_down":
            interval += 5
            log(f"Slowing down, new interval: {interval}s")
            continue

        resp.raise_for_status()


def list_appliances(access_token: str) -> list:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.bsh.sdk.v1+json",
    }
    log(f"GET {APPLIANCES_URL}")
    resp = requests.get(APPLIANCES_URL, headers=headers)
    log(f"Response {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json().get("data", {}).get("homeappliances", [])


def main() -> None:
    client_id = input("Enter your Home Connect Client ID: ").strip()
    if not client_id:
        print("Client ID is required.")
        sys.exit(1)

    # Step 1: Device authorization
    log("Starting Device Authorization Flow...")
    auth_data = device_authorization(client_id)

    verification_uri = auth_data["verification_uri_complete"]
    user_code = auth_data["user_code"]
    device_code = auth_data["device_code"]
    interval = auth_data.get("interval", 5)

    print("\n" + "=" * 60)
    print("AUTHORIZATION REQUIRED")
    print("=" * 60)
    print(f"1. Open this URL: {verification_uri}")
    print(f"2. Enter this code if prompted: {user_code}")
    print("3. Log in and authorize the application")
    print("=" * 60 + "\n")

    # Step 2: Poll for token
    token_data = poll_for_token(client_id, device_code, interval)
    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]

    log("Authorization successful!")

    # Step 3: List appliances
    log("Fetching appliances...")
    appliances = list_appliances(access_token)

    if not appliances:
        print("\nNo appliances found. Make sure your dishwasher is paired in the Home Connect app.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("APPLIANCES FOUND")
    print("=" * 60)
    for app in appliances:
        print(f"  Name: {app.get('name', 'N/A')}")
        print(f"  Type: {app.get('type', 'N/A')}")
        print(f"  haId: {app.get('haId', 'N/A')}")
        print(f"  Brand: {app.get('brand', 'N/A')}")
        print(f"  Connected: {app.get('connected', 'N/A')}")
        print()

    print("=" * 60)
    print("GITHUB SECRETS TO CONFIGURE")
    print("=" * 60)
    print(f"  HC_CLIENT_ID     = {client_id}")
    print(f"  HC_REFRESH_TOKEN = {refresh_token}")
    for app in appliances:
        if "Dishwasher" in app.get("type", ""):
            print(f"  HC_HAID          = {app['haId']}")
            break
    else:
        print(f"  HC_HAID          = <pick haId from above>")
    print("\nNote: You also need HC_CLIENT_SECRET from the developer portal.")
    print("=" * 60)


if __name__ == "__main__":
    main()
