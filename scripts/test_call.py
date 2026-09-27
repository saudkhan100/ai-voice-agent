"""Place a test call and print the result when it finishes.

    .venv\\Scripts\\python.exe scripts\\test_call.py scripts\\sample_call.json
    .venv\\Scripts\\python.exe scripts\\test_call.py scripts\\sample_call.json --phone +14165550123

The app must be running (uvicorn) and reachable by Twilio at PUBLIC_BASE_URL.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings

FINAL_STATUSES = {"completed", "no-answer", "busy", "failed", "canceled"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="JSON file with phone, first_name and vehicle")
    parser.add_argument("--phone", help="override the phone number in the file")
    parser.add_argument("--api", default="http://localhost:8000", help="local app URL")
    args = parser.parse_args()

    body = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if args.phone:
        body["phone"] = args.phone
    headers = {"X-API-Key": get_settings().lead_api_key}

    with httpx.Client(base_url=args.api, headers=headers, timeout=30) as client:
        resp = client.post("/api/calls", json=body)
        if resp.status_code != 201:
            sys.exit(f"Could not start call ({resp.status_code}): {resp.text}")
        call_id = resp.json()["call_id"]
        print(f"Calling {body['phone']} (call {call_id})... answer your phone.")

        last = None
        while True:
            time.sleep(3)
            data = client.get(f"/api/calls/{call_id}").json()
            if data["telephony_status"] != last:
                last = data["telephony_status"]
                print(f"  status: {last}")
            done = data["telephony_status"] in FINAL_STATUSES
            analysed = (
                data["outcome"] is not None
                or data["error"]
                or data["lead"]["status"] in ("failed", "follow_up", "closed", "appointment_booked")
            )
            if done and analysed:
                break

    print("\n=== Transcript ===")
    for turn in data["transcript"]:
        print(f"{'AI' if turn['role'] == 'assistant' else 'Customer'}: {turn['text']}")
    print("\n=== Result ===")
    print(json.dumps({k: data[k] for k in ("outcome", "error", "recording_url")}, indent=2))
    print(json.dumps(data["lead"], indent=2, default=str))


if __name__ == "__main__":
    main()
