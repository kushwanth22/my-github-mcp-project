import json

import requests

from gateway.auth import GATEWAY, MCP_PATH, get_gateway_token


def parse_sse_response(text: str) -> dict:
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            return json.loads(line[len("data:") :].strip())
    raise ValueError(f"No data: line found in SSE response: {text!r}")


def _call_tool(token: str, tool_name: str, arguments: dict) -> dict:
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
            "params": {"name": tool_name, "arguments": arguments},
        },
    )
    resp.raise_for_status()
    return parse_sse_response(resp.text)


def get_triager_token() -> str:
    return get_gateway_token(
        client_id="agent-issue-triager",
        client_secret_env="AGENT_ISSUE_TRIAGER_SECRET",
        scope="github:read github:issues:write",
    )


def triage_issue(issue_number: int, label: str):
    token = get_triager_token()
    result = _call_tool(
        token,
        "update_issue",
        {
            "owner": "kushwanth22",
            "repo": "fundready-ai",
            "issue_number": issue_number,
            "labels": [label],
        },
    )

    if "error" in result:
        print("Gateway returned an error:")
        print(json.dumps(result["error"], indent=2))
        return

    payload = json.loads(result["result"]["content"][0]["text"])
    print(
        f"Issue #{issue_number} updated — labels now: {[label['name'] for label in payload['labels']]}"
    )
    print(f"  {payload['html_url']}")


def test_scope_boundary():
    token = get_triager_token()
    result = _call_tool(
        token,
        "create_or_update_file",
        {
            "owner": "kushwanth22",
            "repo": "fundready-ai",
            "path": "should_fail.md",
            "content": "x",
            "message": "scope boundary test - should be rejected",
            "branch": "main",
        },
    )

    mcp_result = result.get("result", {})
    if "error" in result or mcp_result.get("isError"):
        msg = result.get("error") or mcp_result["content"][0]["text"]
        print(f"Correctly rejected (expected): {msg}")
    else:
        print("⚠️  UNEXPECTED SUCCESS — scope enforcement is not working:")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    print("=== Positive test: update_issue (should succeed) ===")
    triage_issue(issue_number=1, label="triaged")

    print("\n=== Negative test: create_or_update_file (should be rejected) ===")
    test_scope_boundary()
