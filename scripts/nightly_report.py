import json

import requests

from gateway.auth import GATEWAY, MCP_PATH, get_gateway_token


def parse_sse_response(text: str) -> dict:
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            return json.loads(line[len("data:") :].strip())
    raise ValueError(f"No data: line found in SSE response: {text!r}")


def run_nightly_report():
    token = get_gateway_token(
        client_id="agent-nightly-report",
        client_secret_env="AGENT_NIGHTLY_REPORT_SECRET",
        scope="github:read",
    )

    resp = requests.post(
        f"{GATEWAY}{MCP_PATH}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "search_repositories", "arguments": {"query": "user:kushwanth22"}},
        },
    )
    resp.raise_for_status()
    result = parse_sse_response(resp.text)

    if "error" in result:
        print("Gateway returned an error:")
        print(json.dumps(result["error"], indent=2))
        return

    content = result["result"]["content"][0]["text"]
    data = json.loads(content)

    print(f"Found {data['total_count']} repositories:\n")
    for repo in data["items"]:
        visibility = "private" if repo["private"] else "public"
        print(f"  - {repo['full_name']} ({visibility}) — pushed {repo['pushed_at']}")


if __name__ == "__main__":
    run_nightly_report()
