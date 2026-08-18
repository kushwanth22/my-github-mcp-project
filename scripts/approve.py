import sys

import requests

GATEWAY = "http://localhost:8000"  # runs via docker exec, inside the same container as server.py

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[2] not in ("approve", "reject"):
        print("Usage: python3 approve.py <thread_id> approve|reject")
        sys.exit(1)

    thread_id, decision = sys.argv[1], sys.argv[2]

    resp = requests.post(f"{GATEWAY}/approve/{thread_id}", data={"decision": decision})
    if resp.status_code == 404:
        print(f"No pending approval found for thread_id={thread_id}")
        print("Check /pending on the running server for currently valid thread_ids.")
        sys.exit(1)
    resp.raise_for_status()

    result = resp.json()
    print("Done. Final state context:")
    print(result.get("context", "(no context)"))
