#!/usr/bin/env python3
"""Start a Bosch dishwasher via Home Connect API, set to finish tomorrow at 06:00 Israel time."""

from datetime import datetime, timedelta, timezone

import requests

from homeconnect import (
    BASE_URL,
    CONTENT_TYPE,
    load_env,
    log,
    refresh_access_token,
    run_with_retries,
)

# Israel Standard Time (UTC+2) / Israel Daylight Time (UTC+3)
ISRAEL_TZ = timezone(timedelta(hours=2))
ISRAEL_DST_TZ = timezone(timedelta(hours=3))

FINISH_HOUR = 6  # 06:00 AM Israel time
PROGRAM_KEY = "Dishcare.Dishwasher.Program.Auto2"


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


def get_program_duration(access_token: str, ha_id: str) -> int:
    """Query the estimated duration for the program in seconds."""
    url = f"{BASE_URL}/api/homeappliances/{ha_id}/programs/available/{PROGRAM_KEY}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": CONTENT_TYPE,
    }
    log(f"GET {url}")
    resp = requests.get(url, headers=headers)
    log(f"Response {resp.status_code}")
    log(f"Response body: {resp.text}")
    if resp.status_code != 200:
        log("FATAL: Could not fetch program details to determine duration.")
        raise SystemExit(1)
    data = resp.json()
    for option in data.get("data", {}).get("options", []):
        if option.get("key") == "BSH.Common.Option.EstimatedTotalProgramTime":
            duration = option["value"]
            log(f"Estimated program duration: {duration}s ({duration // 3600}h {(duration % 3600) // 60}m)")
            return duration
    log("FATAL: EstimatedTotalProgramTime not found in program options.")
    raise SystemExit(1)


def compute_start_in_seconds(program_duration: int) -> int:
    """Compute seconds from now until the dishwasher should start, so it finishes at 06:00 Israel time tomorrow."""
    tz = get_israel_tz()
    now_israel = datetime.now(tz)
    tomorrow_finish = now_israel.replace(
        hour=FINISH_HOUR, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    start_time = tomorrow_finish - timedelta(seconds=program_duration)
    delta = start_time - now_israel
    seconds = int(delta.total_seconds())
    log(f"Now (Israel): {now_israel.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log(f"Finish target: {tomorrow_finish.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log(f"Program duration: {program_duration}s → Start at: {start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log(f"StartInRelative: {seconds}s ({seconds // 3600}h {(seconds % 3600) // 60}m)")
    if seconds < 0:
        log("FATAL: Computed start time is in the past. The program would not finish by the target time.")
        raise SystemExit(1)
    return seconds


def start_program(access_token: str, ha_id: str, start_in_seconds: int) -> requests.Response:
    url = f"{BASE_URL}/api/homeappliances/{ha_id}/programs/active"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": CONTENT_TYPE,
        "Content-Type": CONTENT_TYPE,
    }
    body = {
        "data": {
            "key": PROGRAM_KEY,
            "options": [
                {
                    "key": "Dishcare.Dishwasher.Option.ExtraDry",
                    "value": True,
                },
                {
                    "key": "BSH.Common.Option.StartInRelative",
                    "value": start_in_seconds,
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


def main() -> None:
    client_id, client_secret, refresh_token, ha_id = load_env()

    log("Refreshing access token...")
    access_token = refresh_access_token(client_id, client_secret, refresh_token)
    log("Token refreshed successfully.")

    program_duration = get_program_duration(access_token, ha_id)
    start_in_seconds = compute_start_in_seconds(program_duration)

    run_with_retries(
        action=lambda: start_program(access_token, ha_id, start_in_seconds),
        success_msg="Dishwasher program scheduled (delayed start)!",
        check_remote_start=True,
    )


if __name__ == "__main__":
    main()
